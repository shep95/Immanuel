"""Discord bot: control commands, channel management, admin logging, API keys."""
from __future__ import annotations

import asyncio
import io
import json
import time

import discord
from discord import app_commands
from discord.ext import commands

from ..classifier import CATEGORIES, DISPLAY
from ..config import Config
from ..db import Database
from ..engine import Engine
from ..keys import generate_api_key
from .publisher import Publisher

DISCORD_FILE_LIMIT = 7_800_000  # keep under the 8 MB non-nitro upload cap


def _is_admin(interaction: discord.Interaction, config: Config) -> bool:
    uid = interaction.user.id
    if uid in config.master_admin_ids:
        return True
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and perms.administrator)


def create_bot(db: Database, engine: Engine, config: Config,
               publish_queue=None, forge=None, scout=None,
               hack=None) -> commands.Bot:
    intents = discord.Intents.default()
    intents.members = True  # required for join/leave logging (enable in dev portal)
    # Privileged: only request it when explicitly enabled, so a deployment that
    # hasn't toggled "Message Content Intent" in the dev portal still boots.
    intents.message_content = bool(getattr(config, "discord_message_content", False))

    bot = commands.Bot(command_prefix="!", intents=intents)
    tree = bot.tree
    publisher = Publisher(bot, db, config) if publish_queue is not None else None
    bot._immanuel_publisher_started = False
    # /hack bring-your-own-key state (in-memory only — keys are never persisted)
    bot._hack_pending: dict[int, dict] = {}   # channel_id -> pending request
    bot._hack_keys: dict[int, tuple] = {}      # user_id -> (model, key)

    async def admin_only(interaction: discord.Interaction) -> bool:
        if _is_admin(interaction, config):
            return True
        await interaction.response.send_message(
            "⛔ You need to be an Immanuel admin to use this command.",
            ephemeral=True,
        )
        return False

    async def post_admin_log(guild: discord.Guild | None, message: str) -> None:
        chan_id = await asyncio.to_thread(db.get_state, "admin_channel_id")
        if not chan_id:
            return
        channel = bot.get_channel(int(chan_id))
        if channel is not None:
            try:
                await channel.send(message)
            except Exception:
                pass

    # ---------------------------------------------------------- lifecycle
    @bot.event
    async def on_ready() -> None:
        try:
            if config.discord_guild_id:
                guild = discord.Object(id=config.discord_guild_id)
                tree.copy_global_to(guild=guild)
                await tree.sync(guild=guild)
            else:
                await tree.sync()
        except Exception as e:  # pragma: no cover
            print(f"[immanuel] command sync failed: {e}")
        # start the data publisher consumer once
        if publisher is not None and publish_queue is not None and not bot._immanuel_publisher_started:
            bot._immanuel_publisher_started = True
            bot.loop.create_task(publisher.run(publish_queue))
            try:
                await publisher.ensure_channels()
            except Exception as e:  # pragma: no cover
                print(f"[immanuel] channel setup deferred: {e}")
        print(f"[immanuel] logged in as {bot.user} — commands ready")

    @bot.event
    async def on_member_join(member: discord.Member) -> None:
        await asyncio.to_thread(
            db.log_member_event, str(member.guild.id), str(member.id),
            str(member), "join",
        )
        await post_admin_log(
            member.guild,
            f"🟢 **JOIN** {member.mention} (`{member}` id=`{member.id}`) "
            f"joined at <t:{int(time.time())}:F>",
        )

    @bot.event
    async def on_member_remove(member: discord.Member) -> None:
        await asyncio.to_thread(
            db.log_member_event, str(member.guild.id), str(member.id),
            str(member), "leave",
        )
        await post_admin_log(
            member.guild,
            f"🔴 **LEAVE** `{member}` (id=`{member.id}`) "
            f"left at <t:{int(time.time())}:F>",
        )

    # ---------------------------------------------------- control commands
    @tree.command(name="start", description="Start / resume the 24/7 data collection engine.")
    async def start(interaction: discord.Interaction) -> None:
        if not await admin_only(interaction):
            return
        msg = engine.start()
        await interaction.response.send_message(f"▶️ Engine {msg}.")

    @tree.command(name="pause", description="Pause data collection (keeps state).")
    async def pause(interaction: discord.Interaction) -> None:
        if not await admin_only(interaction):
            return
        msg = engine.pause()
        await interaction.response.send_message(f"⏸️ Engine {msg}.")

    @tree.command(name="stop", description="Stop data collection.")
    async def stop(interaction: discord.Interaction) -> None:
        if not await admin_only(interaction):
            return
        msg = engine.stop()
        await interaction.response.send_message(f"⏹️ Engine {msg}.")

    @tree.command(name="updates", description="Show live engine stats and collection totals.")
    async def updates(interaction: discord.Interaction) -> None:
        snap = await asyncio.to_thread(engine.snapshot)
        emb = discord.Embed(title="📊 Immanuel — status",
                            color=0x2ecc71 if snap["state"] == "running" else 0x95a5a6)
        emb.add_field(name="Engine", value=f'{snap["state"]} ({snap.get("mode","-")})', inline=True)
        emb.add_field(name="Uptime (s)", value=int(snap["uptime_seconds"]), inline=True)
        emb.add_field(name="Items", value=snap["items_total"], inline=True)
        sw = snap.get("swarm")
        if sw:
            emb.add_field(name="Agents (active/peak)",
                          value=f'{sw["agents_active"]}/{sw["peak_agents"]}', inline=True)
            emb.add_field(name="Frontier", value=sw["frontier_size"], inline=True)
            emb.add_field(name="Agents spawned", value=sw["agents_spawned"], inline=True)
        emb.add_field(name="Sources", value=f'{snap["sources_active"]}/{snap["sources_total"]} active', inline=True)
        emb.add_field(name="Domains", value=snap.get("domains_total", 0), inline=True)
        emb.add_field(name="Max hops", value=snap.get("max_hops", "-"), inline=True)
        emb.add_field(name="Workers", value=snap["workers"], inline=True)
        emb.add_field(name="Versions/Updates",
                      value=f'{snap["versions_total"]}/{snap["updates_total"]}', inline=True)
        s = snap["stats"]
        emb.add_field(name="Cycles", value=s["cycles"], inline=True)
        emb.add_field(name="New/Updated", value=f'{s["new_pages"]}/{s["updated"]}', inline=True)
        cats = snap["by_category"]
        if cats:
            lines = [f'• {DISPLAY.get(k, k)}: {v}' for k, v in sorted(cats.items())]
            emb.add_field(name="By category", value="\n".join(lines), inline=False)
        # deep-acquisition + pattern-forge extras
        emb.add_field(name="Secrets found", value=db.count_secrets(), inline=True)
        emb.add_field(name="Intel reports", value=db.count_intel(), inline=True)
        emb.add_field(name="Media saved", value=db.count_media_assets(), inline=True)
        if forge is not None:
            fs = forge.snapshot()
            emb.add_field(
                name="Pattern Forge",
                value=f'{fs["patterns_total"]} patterns '
                      f'(✅ {fs["validated"]} validated, {fs["active"]} active) '
                      f'· {fs["passes"]} passes',
                inline=False)
        if scout is not None:
            gs = scout.snapshot()
            by = gs.get("by_category") or {}
            top = ", ".join(f'{k}:{v}' for k, v in sorted(by.items())) or "—"
            emb.add_field(
                name="GitHub tool scout",
                value=f'{gs["repos_total"]} tools · {gs["passes"]} passes\n{top}',
                inline=False)
        await interaction.response.send_message(embed=emb)

    # -------------------------------------------------- asherin.eng search
    @tree.command(name="search",
                  description="Search the collected knowledge (asherin.eng search engine).")
    @app_commands.describe(query="what to search for",
                           category="optional category filter",
                           company="optional company filter",
                           topic="optional topic filter")
    async def search_cmd(interaction: discord.Interaction, query: str,
                         category: str | None = None, company: str | None = None,
                         topic: str | None = None) -> None:
        await interaction.response.defer(thinking=True)
        rows = await asyncio.to_thread(
            db.search_items, query, category, None, company, topic, 10, 0)
        if not rows:
            await interaction.followup.send(f"🔍 No results for **{query}**.")
            return
        emb = discord.Embed(title=f"🔍 asherin.eng — {query}", color=0x1abc9c)
        for r in rows[:10]:
            meta = []
            if r.get("company"):
                meta.append(r["company"])
            if r.get("topic"):
                meta.append(r["topic"])
            meta.append(DISPLAY.get(r.get("category") or "unknown", "unknown"))
            emb.add_field(
                name=(r.get("title") or r["url"])[:200],
                value=f'{r["url"][:120]}\n_{" · ".join(meta)}_',
                inline=False)
        emb.set_footer(text=f"{len(rows)} result(s) • use the API /v1/search for more")
        await interaction.followup.send(embed=emb)

    @tree.command(name="setup_asherin_eng",
                  description="Create the asherin-eng search channel.")
    async def setup_asherin_eng(interaction: discord.Interaction) -> None:
        if not await admin_only(interaction):
            return
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        chan = discord.utils.get(guild.text_channels, name="asherin-eng")
        if chan is None:
            try:
                chan = await guild.create_text_channel("asherin-eng")
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ I need **Manage Channels**.", ephemeral=True)
                return
        await asyncio.to_thread(db.set_state, "asherin_eng_channel_id", str(chan.id))
        await interaction.response.send_message(
            f"✅ {chan.mention} is ready. Use `/search <query>` here (or anywhere) "
            "to query everything collected — like a working search engine.")

    # ---------------------------------------------------- pattern forge
    @tree.command(name="patterns",
                  description="[admin] Show the Pattern Forge library (learned patterns).")
    async def patterns_cmd(interaction: discord.Interaction) -> None:
        if not await admin_only(interaction):
            return
        rows = await asyncio.to_thread(db.list_patterns, None, 10)
        fs = forge.snapshot() if forge is not None else {
            "patterns_total": len(rows), "validated": 0, "active": 0, "passes": 0}
        emb = discord.Embed(
            title="🧠 Pattern Forge — learned patterns",
            description=f'{fs["patterns_total"]} patterns · '
                        f'✅ {fs["validated"]} validated · {fs["active"]} active · '
                        f'{fs["passes"]} passes',
            color=0x9b59b6)
        for p in rows[:10]:
            emb.add_field(
                name=f'[{p["status"]}] {p["name"]}'[:230],
                value=f'{p.get("mechanism","")[:180]}\n'
                      f'_confidence {p.get("confidence",0):.2f} · '
                      f'evidence {p.get("evidence_count",0)}_',
                inline=False)
        if not rows:
            emb.add_field(name="—",
                          value="no patterns yet; the forge learns as data arrives.",
                          inline=False)
        await interaction.response.send_message(embed=emb, ephemeral=True)

    @tree.command(name="skills-download",
                  description="[admin] Download all learned pattern skills as a .txt file.")
    @app_commands.describe(only_validated="only export validated/active patterns")
    async def skills_download(interaction: discord.Interaction,
                              only_validated: bool = False) -> None:
        if not await admin_only(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        from ..patternforge.skills import render_skills
        text = await asyncio.to_thread(render_skills, db, only_validated=only_validated)
        data = text.encode("utf-8")
        if len(data) <= DISCORD_FILE_LIMIT:
            file = discord.File(io.BytesIO(data), filename="asherin_skills.txt")
            await interaction.followup.send(
                f"🧠 Exported the Pattern Forge skill library "
                f"({db.count_patterns()} patterns).", file=file, ephemeral=True)
        else:
            file = discord.File(io.BytesIO(data[:DISCORD_FILE_LIMIT]),
                                filename="asherin_skills_partial.txt")
            await interaction.followup.send(
                "🧠 Skill library is large — sending a partial file. "
                "Full export: `GET /v1/patterns/export` with your ADMIN API key.",
                file=file, ephemeral=True)

    # ---------------------------------------------------- intel reports
    @tree.command(name="intel",
                  description="Show the most recent intel data-reports.")
    async def intel_cmd(interaction: discord.Interaction) -> None:
        rows = await asyncio.to_thread(db.recent_intel, 10)
        if not rows:
            await interaction.response.send_message("No intel reports yet.")
            return
        lines = []
        for r in rows:
            lines.append(
                f'• {r["url"][:80]} — {r["links_count"]} links, '
                f'{r["media_count"]} media, ⚠️ {r["secrets_count"]} secrets')
        await interaction.response.send_message(
            "**Recent intel reports:**\n" + "\n".join(lines)[:1900])

    @tree.command(name="setup_secrets_channel",
                  description="Create the PRIVATE admin api-key/secrets channel.")
    async def setup_secrets_channel(interaction: discord.Interaction) -> None:
        if not await admin_only(interaction):
            return
        if publisher is None:
            await interaction.response.send_message(
                "Publishing is disabled for this deployment.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        chan = await publisher.ensure_secrets_channel()
        if chan is None:
            await interaction.followup.send(
                "❌ Could not create it — I need **Manage Channels**.")
            return
        await interaction.followup.send(
            f"✅ Private api-key channel ready: {chan.mention}. "
            "Exposed API keys / secrets found on public pages are reported here "
            "(admins only; values masked).")

    @tree.command(name="secrets",
                  description="[admin] List exposed secrets: secret -> company -> data.")
    @app_commands.describe(by_company="group by company instead of listing findings")
    async def secrets_cmd(interaction: discord.Interaction,
                          by_company: bool = False) -> None:
        if not await admin_only(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        if by_company:
            rows = await asyncio.to_thread(db.secrets_by_company, 25)
            if not rows:
                await interaction.followup.send("No exposed secrets found yet.",
                                                ephemeral=True)
                return
            lines = [f'• **{r["company"]}** — {r["c"]} secret(s), '
                     f'{r["types"]} type(s)' for r in rows]
            await interaction.followup.send(
                "**Exposed secrets by company:**\n" + "\n".join(lines)[:1900],
                ephemeral=True)
            return
        rows = await asyncio.to_thread(db.recent_secrets, 15)
        if not rows:
            await interaction.followup.send("No exposed secrets found yet.",
                                            ephemeral=True)
            return
        emb = discord.Embed(
            title="🔐 Exposed secrets (admin only)",
            description=f"{db.count_secrets()} total • values masked",
            color=0xc0392b)
        for r in rows[:15]:
            emb.add_field(
                name=f'{r["secret_type"]} — {r.get("company") or r.get("domain") or "?"}',
                value=f'secret: `{r["masked"]}`\n'
                      f'data: {(r.get("context") or "n/a")[:150]}\n'
                      f'{r["url"][:120]}',
                inline=False)
        await interaction.followup.send(embed=emb, ephemeral=True)

    @tree.command(name="adminkey",
                  description="Generate an ADMIN API key (access exposed-secret endpoints).")
    async def adminkey(interaction: discord.Interaction) -> None:
        if not await admin_only(interaction):
            return
        owner = f"{interaction.user} ({interaction.user.id})"
        raw = await asyncio.to_thread(generate_api_key, db, owner, "read admin")
        base = config.public_base_url or "http://<your-deployment>"
        await interaction.response.send_message(
            "🔑 **Your ADMIN API key (shown once):**\n"
            f"```{raw}```\n"
            f"Admin-only: `GET {base}/v1/secrets` (exposed keys, masked).",
            ephemeral=True)

    # ---------------------------------------- media + transcript channels
    @tree.command(
        name="setup_media_channels",
        description="Create public per-file-type media channels + a transcripts channel.")
    async def setup_media_channels(interaction: discord.Interaction) -> None:
        if not await admin_only(interaction):
            return
        if publisher is None:
            await interaction.response.send_message(
                "Publishing is disabled for this deployment.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        mapping = await publisher.ensure_media_channels()
        if not mapping:
            await interaction.followup.send(
                "❌ Could not create channels — I need **Manage Channels**.")
            return
        names = ", ".join(f"#{n}" for n in mapping)
        await interaction.followup.send(
            f"✅ Media channels ready under **📁 asherin media** + "
            f"**🎬 asherin youtube**: {names}\n"
            "Images, audio, video, documents, archives, other files, and YouTube "
            "transcripts get sorted into these as pages are collected.")

    # ------------------------------------------------ github tool scout
    @tree.command(
        name="setup_github_channel",
        description="Create the PRIVATE owner-only channel for found GitHub tools.")
    async def setup_github_channel(interaction: discord.Interaction) -> None:
        if not await admin_only(interaction):
            return
        if publisher is None:
            await interaction.response.send_message(
                "Publishing is disabled for this deployment.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        chan = await publisher.ensure_github_channel()
        if chan is None:
            await interaction.followup.send(
                "❌ Could not create it — I need **Manage Channels**.")
            return
        await interaction.followup.send(
            f"✅ Private tool channel ready: {chan.mention} (server owner + bot only). "
            "The scout drops useful osint / cyber-security / hacking / surveillance / "
            "red-team repos here 24/7 — link, name, description, and how it's useful.")

    @tree.command(name="github_tools",
                  description="Show recently discovered useful GitHub tools.")
    @app_commands.describe(
        category="optional: osint | cyber-security | hacking | surveillance | red-team")
    async def github_tools(interaction: discord.Interaction,
                           category: str | None = None) -> None:
        rows = await asyncio.to_thread(db.list_github_repos, category, 10)
        if not rows:
            await interaction.response.send_message(
                "No tools found yet — the scout is still hunting.")
            return
        gs = scout.snapshot() if scout is not None else {"repos_total": len(rows)}
        emb = discord.Embed(
            title="🛠️ GitHub tools" + (f" — {category}" if category else ""),
            description=f'{gs["repos_total"]} total discovered',
            color=0x2ecc71)
        for r in rows[:10]:
            emb.add_field(
                name=f'{r["full_name"]}'[:230],
                value=f'{r["html_url"]}\n_{r.get("category","?")} · '
                      f'{(r.get("description") or "")[:100]}_',
                inline=False)
        await interaction.response.send_message(embed=emb)

    # ------------------------------------------------------ /hack pentest
    def _hack_embed(result: dict, target: str) -> discord.Embed:
        status = result.get("status", "?")
        color = {"completed": 0x2ecc71, "failed": 0xe74c3c,
                 "timeout": 0xe67e22, "unavailable": 0x95a5a6}.get(status, 0x3498db)
        findings = result.get("findings") or []
        emb = discord.Embed(
            title=f"🛡️ /hack — {target}"[:250],
            description=(f"engine: **{result.get('engine','?')}** · status: "
                         f"**{status}** · run #{result.get('run_id','?')}"),
            color=color)
        emb.add_field(name="summary", value=(result.get("summary") or "—")[:1000],
                      inline=False)
        sev_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        for f in sorted(findings, key=lambda x: sev_order.get(
                str(x.get("severity", "info")).lower(), 3))[:10]:
            sev = str(f.get("severity", "info")).upper()
            val = (f.get("detail") or f.get("masked") or "")[:200] or "—"
            emb.add_field(name=f"[{sev}] {str(f.get('title',''))[:200]}",
                          value=val, inline=False)
        if len(findings) > 10:
            emb.set_footer(text=f"+{len(findings) - 10} more findings — see report")
        return emb

    async def _run_hack_to_channel(channel, user, target, instruction, engine,
                                   api_key=None, model=None) -> None:
        """Run a /hack job and post the report into the user's private channel."""
        try:
            await channel.send(f"⏳ running /hack on `{target}` "
                               f"({engine or config.hack_engine})…")
        except Exception:
            pass
        try:
            result = await hack.run(target, instruction, engine=engine,
                                    requested_by=str(user), api_key=api_key,
                                    model=model)
        except Exception as exc:  # pragma: no cover - safety net
            try:
                await channel.send(f"❌ /hack `{target}` crashed: {exc}")
            except Exception:
                pass
            return
        emb = _hack_embed(result, target)
        rp = result.get("report_path")
        file = None
        if rp:
            try:
                file = discord.File(rp)
            except Exception:
                file = None
        try:
            await channel.send(embed=emb, file=file)
        except Exception:
            pass

    @tree.command(
        name="hack",
        description="Run an AI pentest (Strix) or deterministic recon in your private channel.")
    @app_commands.describe(
        target="URL, domain, IP, or repo to test",
        instruction="optional focus, e.g. 'check auth and IDOR'",
        engine="auto (default) | strix | recon")
    async def hack_cmd(interaction: discord.Interaction, target: str,
                       instruction: str | None = None,
                       engine: str | None = None) -> None:
        if hack is None or not config.enable_hack:
            await interaction.response.send_message(
                "⛔ /hack is disabled for this deployment.", ephemeral=True)
            return
        if interaction.guild is None or publisher is None:
            await interaction.response.send_message(
                "❌ Use /hack inside a server (it opens a private channel for you).",
                ephemeral=True)
            return
        target = (target or "").strip()
        if not target:
            await interaction.response.send_message(
                "❌ Give me a target (URL, domain, IP, or repo).", ephemeral=True)
            return
        engine = (engine or "").strip().lower() or None
        if engine and engine not in ("auto", "strix", "recon"):
            await interaction.response.send_message(
                "❌ engine must be auto, strix, or recon.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        chan = await publisher.ensure_user_hack_channel(interaction.user)
        if chan is None:
            await interaction.followup.send(
                "❌ Could not open your private channel — I need **Manage Channels**.")
            return
        await interaction.followup.send(
            f"🔒 opened your private hack channel: {chan.mention} — continue there.")

        picked = engine or config.hack_engine
        stored = bot._hack_keys.get(interaction.user.id)

        # recon needs no key — run it right away
        if picked == "recon":
            asyncio.create_task(_run_hack_to_channel(
                chan, interaction.user, target, instruction, "recon"))
            return

        # strix / auto: reuse a key already brought this session, else ask for one
        if stored:
            model, key = stored
            asyncio.create_task(_run_hack_to_channel(
                chan, interaction.user, target, instruction, engine,
                api_key=key, model=model))
            return

        bot._hack_pending[chan.id] = {
            "user_id": interaction.user.id, "target": target,
            "instruction": instruction, "engine": engine}
        model_hint = config.strix_llm or "openrouter/z-ai/glm-5.3"
        if getattr(config, "discord_message_content", False):
            how = (f"**paste your key here** in one of these forms:\n"
                   f"• `your-api-key` (uses model `{model_hint}`)\n"
                   f"• `provider/model | your-api-key` (choose the model)\n\n"
                   f"…or type **recon** to run the keyless deterministic engine.")
        else:
            how = (f"run **`/hackkey`** to set your key (private/ephemeral), then "
                   f"**`/hack {target}`** again.\n"
                   f"default model is `{model_hint}` unless you pass one to /hackkey.\n\n"
                   f"…or run **`/hack {target} engine:recon`** for the keyless engine.")
        await chan.send(
            f"🛡️ **/hack `{target}`** — bring your own LLM key to run the Strix AI "
            f"agents.\n\n{how}\n"
            f"_your key is used only for your runs, never stored to disk._")

    @tree.command(
        name="hackkey",
        description="Set your own LLM key for /hack (private, ephemeral, never stored to disk).")
    @app_commands.describe(
        api_key="your LLM api key (used only for your runs)",
        model="optional model, e.g. openrouter/z-ai/glm-5.3")
    async def hackkey_cmd(interaction: discord.Interaction, api_key: str,
                          model: str | None = None) -> None:
        if hack is None or not config.enable_hack:
            await interaction.response.send_message(
                "⛔ /hack is disabled for this deployment.", ephemeral=True)
            return
        key = (api_key or "").strip()
        if not key:
            await interaction.response.send_message(
                "❌ paste your api key.", ephemeral=True)
            return
        mdl = (model or config.strix_llm or "openrouter/z-ai/glm-5.3").strip()
        bot._hack_keys[interaction.user.id] = (mdl, key)
        await interaction.response.send_message(
            f"✅ key stored in memory for this session (model `{mdl}`). "
            f"it's never written to disk. now run `/hack <target>`.", ephemeral=True)

    @bot.event
    async def on_message(message: discord.Message) -> None:
        # capture a bring-your-own-key reply in a private hack channel (only
        # meaningful when the Message Content Intent is enabled; otherwise
        # message.content is empty and this simply passes through)
        pending = bot._hack_pending.get(getattr(message.channel, "id", 0))
        if (pending and not message.author.bot
                and message.author.id == pending["user_id"] and hack is not None):
            content = (message.content or "").strip()
            bot._hack_pending.pop(message.channel.id, None)
            if content.lower() in ("recon", "skip", "keyless", "no", "no key"):
                asyncio.create_task(_run_hack_to_channel(
                    message.channel, message.author, pending["target"],
                    pending["instruction"], "recon"))
                return
            # parse "model | key" | "model key" | "key"
            model = config.strix_llm or ""
            key = content
            if "|" in content:
                left, _, right = content.partition("|")
                model, key = left.strip(), right.strip()
            elif " " in content and "/" in content.split(" ", 1)[0]:
                left, _, right = content.partition(" ")
                model, key = left.strip(), right.strip()
            if not model:
                model = "openrouter/z-ai/glm-5.3"
            bot._hack_keys[message.author.id] = (model, key)
            try:
                await message.delete()
            except Exception:
                pass
            await message.channel.send(
                f"✅ key received (model `{model}`) — starting the run. "
                "future /hack runs this session reuse it automatically.")
            asyncio.create_task(_run_hack_to_channel(
                message.channel, message.author, pending["target"],
                pending["instruction"], pending["engine"],
                api_key=key, model=model))
            return
        await bot.process_commands(message)

    @tree.command(
        name="setup_hack_channel",
        description="Create the PRIVATE owner-only channel for /hack results.")
    async def setup_hack_channel(interaction: discord.Interaction) -> None:
        if not await admin_only(interaction):
            return
        if publisher is None:
            await interaction.response.send_message(
                "Publishing is disabled for this deployment.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        chan = await publisher.ensure_hack_channel()
        if chan is None:
            await interaction.followup.send(
                "❌ Could not create it — I need **Manage Channels**.")
            return
        await interaction.followup.send(
            f"✅ Private hack channel ready: {chan.mention} (server owner + bot only).")

    @tree.command(name="hack_runs", description="List recent /hack runs (admin).")
    async def hack_runs(interaction: discord.Interaction) -> None:
        if not await admin_only(interaction):
            return
        rows = await asyncio.to_thread(db.recent_hack_runs, 15)
        if not rows:
            await interaction.response.send_message(
                "No /hack runs yet. Start one with /hack.", ephemeral=True)
            return
        emb = discord.Embed(title="🛡️ recent /hack runs", color=0x3498db)
        for r in rows[:15]:
            emb.add_field(
                name=f"#{r['id']} · {r['engine']} · {r['status']}"[:230],
                value=f"{r['target'][:80]} — {r['findings_count']} finding(s)",
                inline=False)
        await interaction.response.send_message(embed=emb, ephemeral=True)

    # ------------------------------------------------------ source commands
    @tree.command(name="addsource", description="Add a seed URL for the crawler to collect.")
    @app_commands.describe(url="A public http(s) URL")
    async def addsource(interaction: discord.Interaction, url: str) -> None:
        if not await admin_only(interaction):
            return
        if not url.startswith(("http://", "https://")):
            await interaction.response.send_message("❌ URL must start with http:// or https://", ephemeral=True)
            return
        added = await asyncio.to_thread(db.add_source, url, "seed", str(interaction.user))
        if added:
            engine.start() if engine.state == "running" else None
            await interaction.response.send_message(f"✅ Added source: {url}")
        else:
            await interaction.response.send_message("ℹ️ That source already exists.", ephemeral=True)

    @tree.command(name="sources", description="List the most recent sources.")
    async def sources(interaction: discord.Interaction) -> None:
        rows = await asyncio.to_thread(db.list_sources, None, 15)
        if not rows:
            await interaction.response.send_message("No sources yet. Add one with /addsource.")
            return
        lines = [f'• [{r["status"]}] {r["url"]} ({r["kind"]})' for r in rows]
        await interaction.response.send_message("**Sources:**\n" + "\n".join(lines)[:1900])

    # -------------------------------------------------------- data commands
    @tree.command(name="download", description="Download ALL collected data as a file.")
    async def download(interaction: discord.Interaction) -> None:
        if not await admin_only(interaction):
            return
        await interaction.response.defer(thinking=True)
        items = await asyncio.to_thread(lambda: list(db.iter_all_items()))
        payload = {
            "service": "immanuel",
            "exported_at": time.time(),
            "count": len(items),
            "items": items,
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        if len(data) <= DISCORD_FILE_LIMIT:
            file = discord.File(io.BytesIO(data), filename="immanuel_export.json")
            await interaction.followup.send(
                f"📦 Exported **{len(items)}** items.", file=file)
        else:
            # too big for a Discord upload — send a trimmed sample + point to API
            trimmed = {**payload, "items": items[:200], "note": "trimmed; use API /v1/export for full data"}
            tdata = json.dumps(trimmed, ensure_ascii=False, indent=2, default=str).encode("utf-8")
            file = discord.File(io.BytesIO(tdata), filename="immanuel_export_sample.json")
            base = config.public_base_url or "http://<your-deployment>"
            await interaction.followup.send(
                f"📦 Export is large ({len(data)//1024} KB, {len(items)} items) — "
                f"sending a 200-item sample. Full export: `GET {base}/v1/export` "
                f"with your API key (see /apikey).",
                file=file,
            )

    @tree.command(name="apikey", description="Generate a personal API key to connect your platform/LLM.")
    @app_commands.describe(name="Optional label for this key")
    async def apikey(interaction: discord.Interaction, name: str | None = None) -> None:
        owner = f"{interaction.user} ({interaction.user.id})"
        raw = await asyncio.to_thread(generate_api_key, db, owner, "read")
        base = config.public_base_url or "http://<your-deployment>"
        await interaction.response.send_message(
            "🔑 **Your Immanuel API key (shown once — save it now):**\n"
            f"```{raw}```\n"
            "Use it as a header:\n"
            f"`X-API-Key: {raw[:12]}…`  or  `Authorization: Bearer {raw[:12]}…`\n\n"
            "**Examples:**\n"
            f"```bash\ncurl -H \"X-API-Key: {raw[:8]}...\" \"{base}/v1/search?q=climate\"\n```\n"
            f"Full data: `GET {base}/v1/export` · Docs: `{base}/docs`",
            ephemeral=True,
        )

    @tree.command(name="categories", description="Show the classification categories and counts.")
    async def categories_cmd(interaction: discord.Interaction) -> None:
        counts = await asyncio.to_thread(db.counts_by_category)
        lines = [f'• **{DISPLAY[c]}** (`{c}`): {counts.get(c, 0)}' for c in CATEGORIES]
        lines.append(f'• unknown: {counts.get("unknown", 0)}')
        await interaction.response.send_message(
            "**Immanuel classifies public content into:**\n" + "\n".join(lines)
            + "\n\n_Note: 'private' labels describe the claim's subject matter in "
            "publicly-posted content — Immanuel never accesses private systems._")

    @tree.command(name="setup_data_channels",
                  description="Create the data category + channels where collected data is hosted.")
    async def setup_data_channels(interaction: discord.Interaction) -> None:
        if not await admin_only(interaction):
            return
        if publisher is None:
            await interaction.response.send_message(
                "Publishing is disabled for this deployment.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        mapping = await publisher.ensure_channels()
        if not mapping:
            await interaction.followup.send(
                "❌ Could not create channels — I need **Manage Channels**.")
            return
        names = ", ".join(f"#{n}" for n in mapping)
        await interaction.followup.send(
            f"✅ Data channels ready under **📚 Immanuel Data**: {names}\n"
            "New items and page updates will be posted here as they're collected.")

    @tree.command(name="recent_updates", description="Show the most recent page updates (with timestamps).")
    async def recent_updates(interaction: discord.Interaction) -> None:
        rows = await asyncio.to_thread(db.recent_updates, 10)
        if not rows:
            await interaction.response.send_message("No page updates recorded yet.")
            return
        lines = []
        for r in rows:
            lines.append(
                f'• <t:{int(r["fetched_at"])}:R> **v{r["version_no"]}** '
                f'{r["diff_summary"]} — {r["url"][:80]}'
            )
        await interaction.response.send_message(
            "**Recent page updates:**\n" + "\n".join(lines)[:1900])

    # -------------------------------------------------- channel management
    @tree.command(name="setup_admin_channel",
                  description="Create/designate the admin log channel (member join/leave logs).")
    @app_commands.describe(channel="Existing channel to use (optional; a new one is created if omitted)")
    async def setup_admin_channel(interaction: discord.Interaction,
                                  channel: discord.TextChannel | None = None) -> None:
        if not await admin_only(interaction):
            return
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        if channel is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            }
            try:
                channel = await guild.create_text_channel("immanuel-admin-log", overwrites=overwrites)
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ I need the **Manage Channels** permission.", ephemeral=True)
                return
        await asyncio.to_thread(db.set_state, "admin_channel_id", str(channel.id))
        await interaction.response.send_message(
            f"✅ Admin log channel set to {channel.mention}. Member joins/leaves will be logged here.")

    @tree.command(name="create_channel", description="Create a new text channel.")
    @app_commands.describe(name="Channel name", category="Optional category name")
    async def create_channel(interaction: discord.Interaction, name: str,
                             category: str | None = None) -> None:
        if not await admin_only(interaction):
            return
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Run this in a server.", ephemeral=True)
            return
        cat_obj = None
        if category:
            cat_obj = discord.utils.get(guild.categories, name=category)
            if cat_obj is None:
                try:
                    cat_obj = await guild.create_category(category)
                except discord.Forbidden:
                    await interaction.response.send_message("❌ Missing **Manage Channels**.", ephemeral=True)
                    return
        try:
            ch = await guild.create_text_channel(name, category=cat_obj)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Missing **Manage Channels**.", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ Created {ch.mention}.")

    @tree.command(name="rename_channel", description="Rename a channel.")
    @app_commands.describe(channel="Channel to rename", new_name="New name")
    async def rename_channel(interaction: discord.Interaction,
                             channel: discord.abc.GuildChannel, new_name: str) -> None:
        if not await admin_only(interaction):
            return
        try:
            await channel.edit(name=new_name)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Missing **Manage Channels**.", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ Renamed to **{new_name}**.")

    @tree.command(name="set_channel_perms",
                  description="Allow or deny a role from viewing a channel.")
    @app_commands.describe(channel="Target channel", role="Role to change", can_view="Allow viewing?")
    async def set_channel_perms(interaction: discord.Interaction,
                                channel: discord.abc.GuildChannel,
                                role: discord.Role, can_view: bool) -> None:
        if not await admin_only(interaction):
            return
        try:
            await channel.set_permissions(role, view_channel=can_view)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Missing **Manage Roles/Channels**.", ephemeral=True)
            return
        verb = "can now view" if can_view else "can no longer view"
        await interaction.response.send_message(
            f"✅ **{role.name}** {verb} {getattr(channel, 'mention', channel.name)}.")

    return bot
