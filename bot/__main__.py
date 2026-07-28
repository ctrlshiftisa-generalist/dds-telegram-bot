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
from bot.handlers.admin import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Starting DDS bot...")

    # Initialize database (creates tables + seeds operation types on first run)
    await init_db(settings.database_path)
    logger.info("Database initialized at %s", settings.database_path)

    # Initialize Google Sheets service
    service_account_info = settings.get_service_account_info()
    sheets = SheetsService(
        service_account_info=service_account_info,
        spreadsheet_id=settings.google_sheet_id,
        sheet_name=settings.sheet_name,
        payments_spreadsheet_id=settings.get_payments_spreadsheet_id(),
        dds_header_row=settings.dds_header_row,
        payments_header_row=settings.payments_header_row,
    )
    logger.info(
        "Google Sheets service initialized (ДДС sheet: %s row %s, Payments spreadsheet: %s row %s)",
        settings.sheet_name,
        settings.dds_header_row,
        settings.get_payments_spreadsheet_id(),
        settings.payments_header_row,
    )

    # Create bot and dispatcher
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    from bot.middlewares import BanMiddleware
    
    # Register routers (order matters: admin first for command priority)
    dp.include_router(admin_router)
    dp.include_router(common_router)
    dp.include_router(request_router)

    # Register middlewares
    dp.message.middleware(BanMiddleware())
    dp.callback_query.middleware(BanMiddleware())

    # Inject SheetsService into all handlers via aiogram 3 dependency injection
    dp["sheets"] = sheets

    logger.info("Bot is running. Polling for updates...")
    try:
        await dp.start_polling(bot, sheets=sheets)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
