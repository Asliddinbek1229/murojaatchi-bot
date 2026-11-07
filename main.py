import sys

if sys.version_info < (3, 10):
    sys.exit("Python 3.10 yoki undan yangi versiya kerak (hozirgi: %s)" % sys.version.split()[0])

import asyncio
import logging
import signal
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from bot import ui
from bot.backup import create_backup
from bot.config import config
from bot.db import Database
from bot.handlers import admin, categories, common, emoji, main_user, report, student, superadmin, system
from bot.logs import setup_logging
from bot.manager import BotManager, make_bot
from bot.middlewares import ContextMiddleware
from bot.storage import SQLiteStorage

log = logging.getLogger("main")


def build_dispatcher(db: Database) -> Dispatcher:
    # FSM holati har bir bot uchun alohida, bazada saqlanadi — qayta ishga tushganda yo'qolmaydi
    dp = Dispatcher(storage=SQLiteStorage(db))
    mw = ContextMiddleware(db)
    dp.message.outer_middleware(mw)
    dp.callback_query.outer_middleware(mw)
    # Tartib muhim: asosiy botdagi begonalar (to'siq) -> umumiy -> bloklash -> superadmin/emoji (asosiy bot)
    #               -> admin (bo'lim boti) -> talaba (bo'lim boti)
    dp.include_routers(
        main_user.router, common.router, system.router, superadmin.block_router, categories.router,
        superadmin.router,
        report.main_router,
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
                    BotCommand(command="status", description="Tizim holati"),
                    BotCommand(command="backup", description="Baza nusxasini olish"),
                    BotCommand(command="cancel", description="Amalni bekor qilish"),
                ],
                scope=BotCommandScopeChat(chat_id=uid),
            )
        except Exception:  # superadmin hali botni ochmagan bo'lishi mumkin
            pass


async def backup_loop(manager: BotManager):
    """Har kuni BACKUP_HOUR da bazaning nusxasi (data/backups). Xato bo'lsa superadminga xabar."""
    while True:
        now = datetime.now()
        nxt = now.replace(hour=config.backup_hour, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        await asyncio.sleep((nxt - now).total_seconds())
        try:
            path = await asyncio.to_thread(create_backup, config.db_path, config.backup_dir, config.backup_keep)
            log.info("Avto-backup: %s", path)
        except Exception as ex:
            log.exception("Avto-backup xatosi")
            await manager.notify_superadmins(f"⚠️ <b>Avto-backup bajarilmadi:</b> <code>{ex}</code>")


async def main():
    setup_logging(config.log_level, config.log_file)
    log.info("Ishga tushirilmoqda... baza: %s", config.db_path)
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
    log.info("Asosiy bot @%s va %d ta bo'lim boti ishlayapti", manager.main_username, len(manager.bots))
    stopper = asyncio.create_task(stop_event.wait())
    backups = asyncio.create_task(backup_loop(manager)) if config.backup_hour >= 0 else None
    try:
        await asyncio.wait([manager.wait_task(), stopper], return_when=asyncio.FIRST_COMPLETED)
    finally:
        stopper.cancel()
        if backups:
            backups.cancel()
        log.info("Tizim to'xtatilmoqda...")
        await manager.shutdown()  # superadminga «to'xtadi» xabarlari shu yerda yuboriladi
        await db.close()
        log.info("Tizim to'xtadi.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
