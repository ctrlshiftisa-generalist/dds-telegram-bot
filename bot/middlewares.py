import asyncio
import logging
import time
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from bot.config import settings

logger = logging.getLogger(__name__)

# Simple in-memory cache
CACHE_ALLOWED_IDS = []
CACHE_TIMESTAMP = 0.0
CACHE_TTL = 300  # 5 minutes

class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user:
            # 1. Hardcoded allow (developers and owner)
            if user.id in settings.developer_ids or user.id == settings.owner_id:
                return await handler(event, data)
                
            # 2. Check cache for Google Sheets whitelist
            global CACHE_ALLOWED_IDS, CACHE_TIMESTAMP
            now = time.time()
            if now - CACHE_TIMESTAMP > CACHE_TTL or not CACHE_ALLOWED_IDS:
                try:
                    sheets = data.get("sheets")
                    if sheets:
                        # Run sync call in a separate thread so it doesn't block the async loop
                        allowed_ids = await asyncio.to_thread(sheets.get_allowed_ids)
                        CACHE_ALLOWED_IDS = allowed_ids
                        CACHE_TIMESTAMP = now
                except Exception as e:
                    logger.error("Failed to update allowed IDs cache: %s", e)
            
            # 3. Check if user is in whitelist
            if str(user.id) not in CACHE_ALLOWED_IDS:
                logger.warning("Blocked unauthorized request from user %s", user.id)
                if isinstance(event, Message):
                    await event.answer("❌ У вас нет доступа к боту. Обратитесь к администратору.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("❌ У вас нет доступа к боту.", show_alert=True)
                return # Drop the update
                
        return await handler(event, data)
