"""VPS entry point and Vercel-compatible Telegram webhook application."""

import asyncio
import hmac
import json
import logging
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import ValidationError

from config import Settings, get_settings
from db.database import close_database, initialize_database
from db.postgres_storage import PostgresStorage
from handlers.location import router as location_router
from handlers.rules import router as rules_router
from handlers.start import router as start_router
from services.location_provider import TelegramLiveLocationProvider

logger = logging.getLogger(__name__)


def create_dispatcher(storage: BaseStorage | None = None) -> Dispatcher:
    """Create a dispatcher with all bot handlers and location services."""
    dispatcher = Dispatcher(storage=storage or MemoryStorage())
    dispatcher["location_provider"] = TelegramLiveLocationProvider()
    dispatcher.include_routers(start_router, rules_router, location_router)
    return dispatcher


@asynccontextmanager
async def vercel_lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Initialize durable storage and register Telegram's webhook."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    if not settings.vercel_runtime or not settings.database_url:
        raise RuntimeError("The Vercel ASGI app requires Vercel and DATABASE_URL")
    if (
        not settings.use_webhook
        or settings.webhook_url is None
        or settings.webhook_secret is None
    ):
        raise RuntimeError("Vercel requires WEBHOOK_URL, WEBHOOK_SECRET, and USE_WEBHOOK=true")

    await initialize_database()
    bot = Bot(token=settings.bot_token)
    dispatcher = create_dispatcher(PostgresStorage())
    application.state.bot = bot
    application.state.dispatcher = dispatcher
    application.state.webhook_secret = settings.webhook_secret

    try:
        await bot.set_webhook(
            url=f"{settings.webhook_url}{settings.webhook_path}",
            secret_token=settings.webhook_secret,
            drop_pending_updates=False,
        )
        yield
    finally:
        await bot.session.close()
        await dispatcher.storage.close()
        await close_database()


app = FastAPI(lifespan=vercel_lifespan)


@app.get("/", include_in_schema=False)
async def health_check() -> dict[str, str]:
    """Return a minimal health response."""
    return {"status": "ok"}


@app.post("/api/webhook", include_in_schema=False)
async def telegram_webhook(request: Request) -> Response:
    """Validate a Telegram webhook request and dispatch its update."""
    bot: Bot | None = getattr(request.app.state, "bot", None)
    dispatcher: Dispatcher | None = getattr(
        request.app.state, "dispatcher", None
    )
    secret: str | None = getattr(request.app.state, "webhook_secret", None)
    provided_secret = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token", ""
    )
    if bot is None or dispatcher is None or secret is None:
        raise HTTPException(status_code=503, detail="Webhook is not initialized")
    if not hmac.compare_digest(provided_secret, secret):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        payload = await request.json()
        update = Update.model_validate(payload, context={"bot": bot})
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError):
        raise HTTPException(status_code=400, detail="Invalid Telegram update") from None

    await dispatcher.feed_update(bot, update)
    return Response(status_code=200)


def _create_dispatcher_for_settings(settings: Settings) -> Dispatcher:
    """Create a dispatcher with durable FSM when PostgreSQL is configured."""
    if settings.database_url:
        return create_dispatcher(PostgresStorage())
    return create_dispatcher()


async def main() -> None:
    """Start long polling or a standalone HTTPS webhook server on a VPS."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    if settings.vercel_runtime:
        raise RuntimeError("On Vercel, serve the exported ASGI app instead of calling main()")
    await initialize_database(settings.database_path)

    bot = Bot(token=settings.bot_token)
    dispatcher = _create_dispatcher_for_settings(settings)
    try:
        if settings.use_webhook:
            if (
                settings.webhook_url is None
                or settings.webhook_secret is None
                or settings.webhook_cert_file is None
                or settings.webhook_key_file is None
            ):
                raise ValueError("Webhook configuration is incomplete")

            webhook_app = web.Application()
            SimpleRequestHandler(
                dispatcher=dispatcher,
                bot=bot,
                secret_token=settings.webhook_secret,
            ).register(webhook_app, path=settings.webhook_path)
            setup_application(webhook_app, dispatcher, bot=bot)
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(
                settings.webhook_cert_file, settings.webhook_key_file
            )
            runner = web.AppRunner(webhook_app, access_log=None)
            await runner.setup()
            site = web.TCPSite(
                runner,
                host=settings.webhook_host,
                port=settings.webhook_port,
                ssl_context=ssl_context,
            )
            try:
                await site.start()
                await bot.set_webhook(
                    url=f"{settings.webhook_url}{settings.webhook_path}",
                    secret_token=settings.webhook_secret,
                )
                logger.info("Webhook listener started")
                await asyncio.Event().wait()
            finally:
                await runner.cleanup()
        else:
            await bot.delete_webhook(drop_pending_updates=False)
            await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await dispatcher.storage.close()
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
