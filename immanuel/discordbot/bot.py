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
               publish_queue=None) -> commands.Bot:
    intents = discord.Intents.default()
    intents.members = True  # required for join/leave logging (enable in dev portal)

    bot = commands.Bot(command_prefix="!", intents=intents)
    tree = bot.tree
    publisher = Publisher(bot, db, config) if publish_queue is not None else None
    bot._immanuel_publisher_started = False

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
        await interaction.response.send_message(embed=emb)

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
