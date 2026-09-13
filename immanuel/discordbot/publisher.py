"""Publish collected data into the Discord server (Discord = the data host).

Consumes new-item / update events from the engine's publish queue and posts them
into a dedicated category with one channel per classification category, plus an
`immanuel-updates` channel for page changes. Channels are auto-created on demand;
their IDs are persisted so restarts reuse them.

Posting is throttled to stay within Discord's rate limits.
"""
from __future__ import annotations

import asyncio
import datetime as dt

import discord

from ..classifier import DISPLAY
from ..config import Config
from ..db import Database

CATEGORY_NAME = "📚 Immanuel Data"
DATA_CHANNELS = [
    "public-facts", "public-rumors", "private-facts",
    "private-rumors", "conspiracies",
]
UPDATES_CHANNEL = "immanuel-updates"
# Private admin channel where exposed API keys / secrets are reported.
SECRETS_CHANNEL = "asherin-api-keys"
# Private OWNER-ONLY channel where useful GitHub tools are dropped.
GITHUB_CHANNEL = "asherin-github-tools"
# Private channel for /hack pentest runs (owner + bot only).
HACK_CHANNEL = "asherin-hack"
# Category holding one private per-user hack channel each.
HACK_CATEGORY = "🔒 asherin hack"
# Category that holds the dynamic per-topic / per-company channels.
ORGANIZED_CATEGORY = "🗂️ asherin channels"
# Public media category + one channel per file-type bucket.
MEDIA_CATEGORY = "📁 asherin media"
MEDIA_BUCKET_CHANNELS = {
    "image": "media-images",
    "audio": "media-audio",
    "video": "media-video",
    "document": "media-documents",
    "archive": "media-archives",
    "other": "media-files",
}
# YouTube transcripts channel (+ its category).
YOUTUBE_CATEGORY = "🎬 asherin youtube"
TRANSCRIPTS_CHANNEL = "asherin-transcripts"

MEDIA_COLORS = {
    "image": 0x16a085, "audio": 0x8e44ad, "video": 0x2980b9,
    "document": 0xd35400, "archive": 0x7f8c8d, "other": 0x95a5a6,
}

# Colors per GitHub tool family.
GITHUB_COLORS = {
    "osint": 0x1abc9c,
    "cyber-security": 0x3498db,
    "hacking": 0xe74c3c,
    "surveillance": 0x9b59b6,
    "red-team": 0xe67e22,
}

CATEGORY_COLORS = {
    "public_fact": 0x2ecc71,
    "public_rumor": 0xf1c40f,
    "private_fact": 0x3498db,
    "private_rumor": 0xe67e22,
    "conspiracy": 0xe74c3c,
    "unknown": 0x95a5a6,
}


class Publisher:
    def __init__(self, bot, db: Database, config: Config):
        self.bot = bot
        self.db = db
        self.config = config
        self._chan_cache: dict[str, int] = {}
        self._throttle = max(0.4, 1.0)  # seconds between posts (rate-limit safe)

    # ------------------------------------------------------------- channels
    def _guild(self) -> discord.Guild | None:
        if self.config.discord_guild_id:
            g = self.bot.get_guild(self.config.discord_guild_id)
            if g:
                return g
        return self.bot.guilds[0] if self.bot.guilds else None

    async def ensure_channels(self) -> dict[str, int]:
        """Create the data category + channels if missing; return name→id."""
        guild = self._guild()
        if guild is None:
            return {}
        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if category is None:
            try:
                category = await guild.create_category(CATEGORY_NAME)
            except discord.Forbidden:
                return {}
        mapping: dict[str, int] = {}
        for name in DATA_CHANNELS + [UPDATES_CHANNEL]:
            existing = discord.utils.get(guild.text_channels, name=name)
            if existing is None:
                try:
                    existing = await guild.create_text_channel(name, category=category)
                except discord.Forbidden:
                    continue
            mapping[name] = existing.id
            self.db.set_state(f"chan_{name}", str(existing.id))
        self._chan_cache.update(mapping)
        return mapping

    def _channel_id(self, name: str) -> int | None:
        if name in self._chan_cache:
            return self._chan_cache[name]
        stored = self.db.get_state(f"chan_{name}")
        if stored:
            self._chan_cache[name] = int(stored)
            return int(stored)
        return None

    async def _get_channel(self, name: str):
        cid = self._channel_id(name)
        if cid is None:
            await self.ensure_channels()
            cid = self._channel_id(name)
        if cid is None:
            return None
        return self.bot.get_channel(cid)

    # -------------------------------------------------------------- posting
    def _embed_for(self, event: dict) -> discord.Embed:
        cat = event.get("category") or "unknown"
        color = CATEGORY_COLORS.get(cat, 0x95a5a6)
        ts = dt.datetime.fromtimestamp(event.get("fetched_at") or 0,
                                       tz=dt.timezone.utc)
        title = (event.get("title") or event.get("url") or "item")[:250]
        emb = discord.Embed(title=title, url=event.get("url"), color=color,
                            timestamp=ts)
        emb.add_field(name="Category", value=DISPLAY.get(cat, cat), inline=True)
        emb.add_field(name="Domain", value=event.get("domain") or "-", inline=True)
        emb.add_field(name="Version", value=str(event.get("version_no", 1)), inline=True)
        if event.get("company"):
            emb.add_field(name="Company", value=str(event["company"])[:60], inline=True)
        if event.get("topic"):
            emb.add_field(name="Topic", value=str(event["topic"])[:60], inline=True)
        if event.get("secrets_count"):
            emb.add_field(name="⚠️ Secrets", value=str(event["secrets_count"]),
                          inline=True)
        if event.get("timeline_ts"):
            emb.add_field(name="Source timestamp", value=str(event["timeline_ts"])[:100],
                          inline=False)
        excerpt = (event.get("excerpt") or "").strip()
        if excerpt:
            emb.description = excerpt[:1500]
        emb.set_footer(text="Immanuel • captured")
        return emb

    async def publish(self, event: dict) -> None:
        kind = event.get("kind")
        if kind == "update":
            await self._publish_update(event)
        elif kind == "secrets":
            await self._publish_secrets(event)
        elif kind == "github":
            await self._publish_github(event)
        elif kind == "media":
            await self._publish_media(event)
        elif kind == "transcript":
            await self._publish_transcript(event)
        else:
            await self._publish_new(event)

    # -------------------------------------------------- dynamic organization
    def _organize_by(self) -> str:
        return getattr(self.config, "organize_by", "epistemic") or "epistemic"

    def _dynamic_channel_name(self, event: dict) -> str | None:
        """Channel name for the current organize_by mode (topic/company)."""
        from ..organize import slugify
        mode = self._organize_by()
        if mode == "topic":
            return "topic-" + slugify(event.get("topic") or "general")
        if mode == "company":
            return "co-" + slugify(event.get("company") or "misc")
        return None

    async def _ensure_dynamic_channel(self, name: str):
        """Get-or-create a per-topic/per-company channel (bounded by config)."""
        existing = await self._get_channel(name)
        if existing is not None:
            return existing
        guild = self._guild()
        if guild is None:
            return None
        # guardrail so we never blow past Discord channel limits
        cap = getattr(self.config, "max_dynamic_channels", 180)
        made = int(self.db.get_state("dynamic_channel_count", "0") or "0")
        if made >= cap:
            return await self._get_channel(DATA_CHANNELS[0])  # fall back
        chan = discord.utils.get(guild.text_channels, name=name)
        if chan is None:
            category = discord.utils.get(guild.categories, name=ORGANIZED_CATEGORY)
            if category is None:
                try:
                    category = await guild.create_category(ORGANIZED_CATEGORY)
                except discord.Forbidden:
                    category = None
            try:
                chan = await guild.create_text_channel(name, category=category)
            except discord.Forbidden:
                return None
            self.db.set_state("dynamic_channel_count", str(made + 1))
        self._chan_cache[name] = chan.id
        self.db.set_state(f"chan_{name}", str(chan.id))
        return chan

    async def _publish_new(self, event: dict) -> None:
        if self._organize_by() in ("topic", "company"):
            name = self._dynamic_channel_name(event)
            channel = await self._ensure_dynamic_channel(name) if name else None
        else:
            cat = event.get("category") or "unknown"
            chan_name = DISPLAY.get(cat, "unknown")
            if chan_name not in DATA_CHANNELS:
                return
            channel = await self._get_channel(chan_name)
        if channel is not None:
            try:
                await channel.send(embed=self._embed_for(event))
            except discord.HTTPException:
                await asyncio.sleep(2)

    async def _publish_secrets(self, event: dict) -> None:
        """Post exposed-secret findings into the PRIVATE admin api-key channel."""
        channel = await self._get_channel(SECRETS_CHANNEL)
        if channel is None:
            channel = await self.ensure_secrets_channel()
        if channel is None:
            return
        findings = event.get("secrets") or []
        # company is tagged onto each finding; fall back to a page-level value
        company = event.get("company")
        for s in findings:
            if s.get("company"):
                company = s["company"]
                break
        emb = discord.Embed(
            title=f"🔐 Exposed credentials — {company or event.get('domain') or 'a page'}",
            url=event.get("url"), color=0xc0392b,
        )
        emb.add_field(name="Company", value=str(company or "unknown")[:100], inline=True)
        emb.add_field(name="Host", value=str(event.get("domain") or "-")[:100], inline=True)
        emb.add_field(name="Page", value=(event.get("url") or "-")[:200], inline=False)
        for s in findings[:15]:
            # secret -> what kind -> what data it was sitting in
            emb.add_field(
                name=f"{s.get('severity','?')} · {s.get('type')}",
                value=f"secret: `{s.get('masked')}`\n"
                      f"data: {(s.get('context') or 'n/a')[:180]}",
                inline=False,
            )
        emb.set_footer(text="asherin • admin only • values masked; raw secret never stored")
        try:
            await channel.send(embed=emb)
        except discord.HTTPException:
            await asyncio.sleep(2)

    async def ensure_secrets_channel(self):
        """Create the private admin-only api-key/secrets channel."""
        guild = self._guild()
        if guild is None:
            return None
        chan = discord.utils.get(guild.text_channels, name=SECRETS_CHANNEL)
        if chan is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True,
                                                      send_messages=True),
            }
            try:
                chan = await guild.create_text_channel(
                    SECRETS_CHANNEL, overwrites=overwrites)
            except discord.Forbidden:
                return None
        self._chan_cache[SECRETS_CHANNEL] = chan.id
        self.db.set_state(f"chan_{SECRETS_CHANNEL}", str(chan.id))
        return chan

    # ------------------------------------------------- github tool scout
    async def _publish_github(self, event: dict) -> None:
        """Drop a discovered GitHub tool into the private owner-only channel."""
        channel = await self._get_channel(GITHUB_CHANNEL)
        if channel is None:
            channel = await self.ensure_github_channel()
        if channel is None:
            return
        repo = event.get("repo") or {}
        cat = repo.get("category") or "osint"
        emb = discord.Embed(
            title=f"🛠️ {repo.get('name') or repo.get('full_name') or 'repo'}"[:250],
            url=repo.get("html_url"),
            color=GITHUB_COLORS.get(cat, 0x2ecc71),
        )
        emb.add_field(name="🔗 GitHub", value=repo.get("html_url") or "-", inline=False)
        emb.add_field(name="Software name",
                      value=(repo.get("full_name") or repo.get("name") or "-")[:200],
                      inline=False)
        desc = (repo.get("description") or "no description provided").strip()
        emb.add_field(name="Description", value=desc[:1000], inline=False)
        emb.add_field(name="How it's useful",
                      value=(repo.get("how_useful") or "-")[:1000], inline=False)
        facts = f"`{cat}`"
        if repo.get("language"):
            facts += f" · {repo['language']}"
        if repo.get("stars"):
            facts += f" · {repo['stars']}★"
        emb.add_field(name="Category", value=facts, inline=False)
        emb.set_footer(text="asherin • github tool scout")
        try:
            await channel.send(embed=emb)
            await asyncio.to_thread(self.db.mark_github_published,
                                    repo.get("full_name"))
        except discord.HTTPException:
            await asyncio.sleep(2)

    async def ensure_github_channel(self):
        """Create the PRIVATE channel only the server owner and the bot can see."""
        guild = self._guild()
        if guild is None:
            return None
        chan = discord.utils.get(guild.text_channels, name=GITHUB_CHANNEL)
        if chan is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True,
                                                      send_messages=True),
            }
            if guild.owner is not None:
                overwrites[guild.owner] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True)
            try:
                chan = await guild.create_text_channel(
                    GITHUB_CHANNEL, overwrites=overwrites,
                    topic="Useful osint/cyber/hacking/surveillance/red-team tools "
                          "found across public GitHub — owner only.")
            except discord.Forbidden:
                return None
        self._chan_cache[GITHUB_CHANNEL] = chan.id
        self.db.set_state(f"chan_{GITHUB_CHANNEL}", str(chan.id))
        return chan

    async def ensure_hack_channel(self):
        """Create the PRIVATE channel only the server owner and the bot can see."""
        guild = self._guild()
        if guild is None:
            return None
        existing = await self._get_channel(HACK_CHANNEL)
        if existing is not None:
            return existing
        chan = discord.utils.get(guild.text_channels, name=HACK_CHANNEL)
        if chan is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True,
                                                      send_messages=True),
            }
            if guild.owner is not None:
                overwrites[guild.owner] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True)
            try:
                chan = await guild.create_text_channel(
                    HACK_CHANNEL, overwrites=overwrites,
                    topic="/hack pentest runs (Strix AI + deterministic recon) — "
                          "findings & reports, admin only.")
            except discord.Forbidden:
                return None
        self._chan_cache[HACK_CHANNEL] = chan.id
        self.db.set_state(f"chan_{HACK_CHANNEL}", str(chan.id))
        return chan

    async def ensure_user_hack_channel(self, member):
        """Get-or-create a PRIVATE per-user /hack channel (that user + bot only)."""
        guild = self._guild()
        if guild is None:
            return None
        state_key = f"hackchan_{member.id}"
        stored = self.db.get_state(state_key)
        if stored:
            chan = guild.get_channel(int(stored))
            if chan is not None:
                return chan
        base = "".join(ch if ch.isalnum() else "-"
                       for ch in str(getattr(member, "display_name", "user")).lower())
        base = base.strip("-")[:24] or "user"
        name = f"hack-{base}-{member.id % 100000}"
        chan = discord.utils.get(guild.text_channels, name=name)
        if chan is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True,
                                                      send_messages=True,
                                                      manage_messages=True),
                member: discord.PermissionOverwrite(view_channel=True,
                                                    send_messages=True),
            }
            category = discord.utils.get(guild.categories, name=HACK_CATEGORY)
            if category is None:
                try:
                    category = await guild.create_category(HACK_CATEGORY)
                except discord.Forbidden:
                    category = None
            try:
                chan = await guild.create_text_channel(
                    name, overwrites=overwrites, category=category,
                    topic=f"private /hack workspace for {member} — you + the bot only.")
            except discord.Forbidden:
                return None
        self.db.set_state(state_key, str(chan.id))
        return chan

    # ---------------------------------------------- media + transcripts
    async def _ensure_named_channel(self, name: str, category_name: str):
        """Get-or-create a public channel under a named category."""
        existing = await self._get_channel(name)
        if existing is not None:
            return existing
        guild = self._guild()
        if guild is None:
            return None
        chan = discord.utils.get(guild.text_channels, name=name)
        if chan is None:
            category = discord.utils.get(guild.categories, name=category_name)
            if category is None:
                try:
                    category = await guild.create_category(category_name)
                except discord.Forbidden:
                    category = None
            try:
                chan = await guild.create_text_channel(name, category=category)
            except discord.Forbidden:
                return None
        self._chan_cache[name] = chan.id
        self.db.set_state(f"chan_{name}", str(chan.id))
        return chan

    async def _publish_media(self, event: dict) -> None:
        """Route a page's media into per-file-type channels (image/doc/zip/...)."""
        items = event.get("items") or []
        if not items:
            return
        groups: dict[str, list] = {}
        for it in items:
            groups.setdefault(it.get("type") or "other", []).append(it)
        page = event.get("page_url")
        for bucket, its in groups.items():
            name = MEDIA_BUCKET_CHANNELS.get(bucket, MEDIA_BUCKET_CHANNELS["other"])
            chan = await self._ensure_named_channel(name, MEDIA_CATEGORY)
            if chan is None:
                continue
            emb = discord.Embed(
                title=f"{bucket} · {(event.get('title') or page or 'page')}"[:250],
                url=page, color=MEDIA_COLORS.get(bucket, 0x95a5a6))
            if event.get("company"):
                emb.add_field(name="Company", value=str(event["company"])[:60],
                              inline=True)
            emb.add_field(name="Count", value=str(len(its)), inline=True)
            emb.add_field(name="From page", value=(page or "-")[:200], inline=False)
            lines = []
            for it in its[:15]:
                tag = " ⬇️saved" if it.get("downloaded") else ""
                lines.append(f"• {it['url'][:150]}{tag}")
            if len(its) > 15:
                lines.append(f"…+{len(its) - 15} more")
            emb.description = "\n".join(lines)[:3900]
            emb.set_footer(text=f"asherin • {bucket} files")
            try:
                await chan.send(embed=emb)
            except discord.HTTPException:
                await asyncio.sleep(2)
            await asyncio.sleep(self._throttle)

    async def _publish_transcript(self, event: dict) -> None:
        """Post a YouTube transcript (+ thumbnail) into the transcripts channel."""
        chan = await self._ensure_named_channel(TRANSCRIPTS_CHANNEL, YOUTUBE_CATEGORY)
        if chan is None:
            return
        transcript = (event.get("transcript") or "").strip()
        vid = event.get("video_id")
        url = (f"https://www.youtube.com/watch?v={vid}" if vid
               else event.get("page_url"))
        emb = discord.Embed(
            title=f"🎬 {event.get('title') or vid or 'video'}"[:250],
            url=url, color=0xc0392b)
        if event.get("thumbnail"):
            emb.set_thumbnail(url=event["thumbnail"])
        emb.add_field(name="Video", value=url or "-", inline=False)
        emb.add_field(name="Transcript", value=f"{len(transcript)} chars", inline=True)
        if event.get("lang"):
            emb.add_field(name="Lang", value=str(event["lang"])[:10], inline=True)
        emb.description = transcript[:1500] + ("…" if len(transcript) > 1500 else "")
        try:
            if len(transcript) > 1500:
                import io
                fname = f"transcript_{vid or 'video'}.txt"
                fh = discord.File(io.BytesIO(transcript.encode("utf-8")), filename=fname)
                await chan.send(embed=emb, file=fh)
            else:
                await chan.send(embed=emb)
        except discord.HTTPException:
            await asyncio.sleep(2)

    async def ensure_media_channels(self) -> dict[str, int]:
        """Pre-create the media category + per-type channels + transcripts."""
        mapping: dict[str, int] = {}
        for name in MEDIA_BUCKET_CHANNELS.values():
            chan = await self._ensure_named_channel(name, MEDIA_CATEGORY)
            if chan is not None:
                mapping[name] = chan.id
        tchan = await self._ensure_named_channel(TRANSCRIPTS_CHANNEL, YOUTUBE_CATEGORY)
        if tchan is not None:
            mapping[TRANSCRIPTS_CHANNEL] = tchan.id
        return mapping

    async def _publish_update(self, event: dict) -> None:
        channel = await self._get_channel(UPDATES_CHANNEL)
        if channel is None:
            return
        ts = dt.datetime.fromtimestamp(event.get("fetched_at") or 0,
                                       tz=dt.timezone.utc)
        emb = discord.Embed(
            title=f"🔄 Updated: {(event.get('title') or event.get('url'))[:230]}",
            url=event.get("url"), color=0x9b59b6, timestamp=ts,
        )
        emb.add_field(name="Change", value=event.get("diff_summary") or "changed",
                      inline=True)
        emb.add_field(name="New version", value=f"v{event.get('version_no')}", inline=True)
        added = (event.get("added_text") or "").strip()
        if added:
            emb.add_field(name="🆕 New data", value=("```" + added[:1000] + "```"),
                          inline=False)
        emb.set_footer(text="Immanuel • page update detected")
        try:
            await channel.send(embed=emb)
        except discord.HTTPException:
            await asyncio.sleep(2)

    # ---------------------------------------------------------------- loop
    async def run(self, queue: asyncio.Queue) -> None:
        # wait until the bot is connected & channels can be created
        await self.bot.wait_until_ready()
        await self.ensure_channels()
        while True:
            event = await queue.get()
            try:
                if self.config.publish_to_discord:
                    await self.publish(event)
            except Exception:
                pass
            finally:
                queue.task_done()
            await asyncio.sleep(self._throttle)
