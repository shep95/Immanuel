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
        else:
            await self._publish_new(event)

    async def _publish_new(self, event: dict) -> None:
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
