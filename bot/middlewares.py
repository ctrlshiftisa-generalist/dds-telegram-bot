import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from bot import database as db

logger = logging.getLogger(__name__)

class BanMiddleware(BaseMiddleware):
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
            db_user = await db.get_user(user.id)
            if db_user and db_user.get("is_banned"):
                logger.warning(f"Blocked request from banned user {user.id}")
                if isinstance(event, Message):
                    await event.answer("❌ У вас нет доступа к боту. Свяжитесь с администратором.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("❌ У вас нет доступа к боту.", show_alert=True)
                return # Drop the update
                
        return await handler(event, data)
