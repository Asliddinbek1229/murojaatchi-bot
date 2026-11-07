from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import config
from bot.db import MAIN_BOT_ID, Database
from bot.ui import R


class ContextMiddleware(BaseMiddleware):
    """Har bir yangilanishga kontekst qo'shadi:
    db, bot_rec (bo'lim boti yozuvi yoki None), bot_id, is_main, is_super, is_admin.
    Foydalanuvchini ro'yxatga oladi va bloklanganlarni to'xtatadi."""

    def __init__(self, db: Database):
        self.db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        manager = data["manager"]
        rec = manager.record_for(data["bot"])
        bot_id = rec["id"] if rec else MAIN_BOT_ID
        data.update(db=self.db, bot_rec=rec, bot_id=bot_id, is_main=rec is None)

        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        is_super = user.id in config.superadmin_ids
        if rec is None:
            is_admin = is_super
        else:
            is_admin = is_super or await self.db.is_active_admin(bot_id, user.id)
        data["is_super"] = is_super
        data["is_admin"] = is_admin

        if isinstance(event, (Message, CallbackQuery)):
            await self.db.upsert_user(user.id, user.full_name, user.username, bot_id)
            if rec is not None and not is_admin and await self.db.is_blocked(user.id):
                if isinstance(event, CallbackQuery):
                    await event.answer("Siz bloklangansiz.", show_alert=True)
                else:
                    await event.answer(R(
                        "[[stop]] <b>Siz botdan foydalanish huquqidan mahrum qilingansiz.</b>\n"
                        "<blockquote>Bu qaror qoidabuzarlik sababli qabul qilingan.</blockquote>"
                    ))
                return None
        return await handler(event, data)
