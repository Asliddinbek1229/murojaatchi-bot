import asyncio
import logging
import signal
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from bot import ui
from bot.config import config
from bot.db import Database
from bot.handlers import admin, common, emoji, main_user, report, student, superadmin
from bot.manager import BotManager, make_bot
from bot.middlewares import ContextMiddleware


def build_dispatcher(db: Database) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())  # FSM holati har bir bot uchun alohida saqlanadi
    mw = ContextMiddleware(db)
    dp.message.outer_middleware(mw)
    dp.callback_query.outer_middleware(mw)
    # Tartib muhim: asosiy botdagi begonalar (to'siq) -> umumiy -> bloklash -> superadmin/emoji (asosiy bot)
    #               -> admin (bo'lim boti) -> talaba (bo'lim boti)
    dp.include_routers(
        main_user.router, common.router, superadmin.block_router, superadmin.router, report.main_router,
        emoji.router, report.dept_router, admin.router, student.router,
    )
    return dp


async def set_commands(bot: Bot):
    await bot.set_my_commands(
        [BotCommand(command="start", description="Bot haqida")],
        scope=BotCommandScopeDefault(),
    )
    for uid in config.superadmin_ids:
        try:
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Bosh menyu"),
                    BotCommand(command="admin", description="Superadmin panel"),
                    BotCommand(command="cancel", description="Amalni bekor qilish"),
                ],
                scope=BotCommandScopeChat(chat_id=uid),
            )
        except Exception:  # superadmin hali botni ochmagan bo'lishi mumkin
            pass


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    db = Database(config.db_path)
    await db.connect()
    await ui.load(db)

    main_bot = make_bot(config.bot_token)
    dp = build_dispatcher(db)
    manager = BotManager(dp, db, main_bot)
    dp["manager"] = manager

    # To'xtatish signallari (Linux/systemd: SIGTERM, SIGINT). Windows'da Ctrl+C asyncio orqali ushlanadi.
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass

    await set_commands(main_bot)
    await manager.start_all()
    logging.info("Asosiy bot @%s va %d ta bo'lim boti ishlayapti", manager.main_username, len(manager.bots))
    stopper = asyncio.create_task(stop_event.wait())
    try:
        await asyncio.wait([manager.wait_task(), stopper], return_when=asyncio.FIRST_COMPLETED)
    finally:
        stopper.cancel()
        logging.info("Tizim to'xtatilmoqda...")
        await manager.shutdown()  # superadminga «to'xtadi» xabarlari shu yerda yuboriladi
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
