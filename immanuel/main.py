"""Single-process entrypoint.

Runs three things in one asyncio event loop:
  1. FastAPI (uvicorn) bound to $PORT — serves the API + Railway healthcheck.
  2. The crawler Engine's 24/7 control loop.
  3. The Discord bot (if DISCORD_TOKEN is set).

If no Discord token is present, it runs the API + engine only (handy for local
testing or an API-only deployment).
"""
from __future__ import annotations

import asyncio
import contextlib
import signal

import uvicorn

from .api.app import create_app
from .config import Config
from .db import Database
from .engine import Engine
from .patternforge.runner import PatternForge


async def _run() -> None:
    config = Config.from_env()
    db = Database(config.database_path)
    # Bounded queue so a slow/absent Discord never grows memory unboundedly.
    publish_queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
    engine = Engine(db, config, publish_queue=publish_queue)

    # Seed sources (and optional Wayback history) before the loop starts.
    try:
        added = await engine.seed()
        if added:
            print(f"[immanuel] seeded {added} sources")
    except Exception as e:  # pragma: no cover
        print(f"[immanuel] seeding error: {e}")

    # Pattern Forge: the second, non-AI algorithm — learns patterns 24/7.
    forge = PatternForge(db, config)

    app = create_app(db, engine, forge)
    uv_config = uvicorn.Config(app, host=config.api_host, port=config.api_port,
                               log_level="info", loop="asyncio")
    server = uvicorn.Server(uv_config)

    tasks = [
        asyncio.create_task(server.serve(), name="api"),
        asyncio.create_task(engine.run_forever(), name="engine"),
        asyncio.create_task(forge.run_forever(), name="patternforge"),
    ]

    bot = None
    if config.discord_token:
        from .discordbot.bot import create_bot

        bot = create_bot(db, engine, config, publish_queue=publish_queue,
                         forge=forge)
        tasks.append(asyncio.create_task(bot.start(config.discord_token), name="discord"))
    else:
        print("[immanuel] DISCORD_TOKEN not set — running API + engine only.")

    # graceful shutdown
    stop_event = asyncio.Event()

    def _signal() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _signal)

    done, pending = await asyncio.wait(
        [asyncio.create_task(stop_event.wait()), *tasks],
        return_when=asyncio.FIRST_COMPLETED,
    )

    print("[immanuel] shutting down…")
    engine.request_shutdown()
    forge.request_shutdown()
    server.should_exit = True
    if bot is not None:
        with contextlib.suppress(Exception):
            await bot.close()
    for t in tasks:
        t.cancel()
    with contextlib.suppress(Exception):
        await asyncio.gather(*tasks, return_exceptions=True)
    db.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
