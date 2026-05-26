"""Bot entry point — configures logging, wires up routers, and starts polling."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.database import init_db
from bot.services.sheets import SheetsService
from bot.handlers.common import router as common_router
from bot.handlers.request import router as request_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Starting DDS bot...")

    # Initialize database
    await init_db(settings.database_path)
    logger.info("Database initialized at %s", settings.database_path)

    # Initialize Google Sheets service
    service_account_info = settings.get_service_account_info()
    sheets = SheetsService(
        service_account_info=service_account_info,
        spreadsheet_id=settings.google_sheet_id,
        sheet_name=settings.sheet_name,
    )
    logger.info("Google Sheets service initialized (sheet: %s)", settings.sheet_name)

    # Create bot and dispatcher
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Register routers
    dp.include_router(common_router)
    dp.include_router(request_router)

    # Inject SheetsService into handlers via middleware-like approach
    # (pass as kwarg to dispatcher — aiogram 3 supports this)
    dp["sheets"] = sheets

    logger.info("Bot is running. Polling for updates...")
    try:
        await dp.start_polling(bot, sheets=sheets)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
