"""Tizim buyruqlari (asosiy bot, faqat superadmin): /backup — bazaning nusxasi, /status — holat."""
import asyncio
import logging
import os
import platform
import sys
import time

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from bot.backup import create_backup
from bot.config import config
from bot.db import Database
from bot.filters import IsMainBot, IsSuperAdmin
from bot.manager import BotManager
from bot.ui import R
from bot.utils import esc

log = logging.getLogger(__name__)

router = Router(name="system")
router.message.filter(IsMainBot(), IsSuperAdmin())

STARTED = time.monotonic()
_lock = asyncio.Lock()


def _uptime() -> str:
    s = int(time.monotonic() - STARTED)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    return (f"{d} kun " if d else "") + f"{h} soat {m} daqiqa"


@router.message(Command("backup"))
async def backup_cmd(message: Message):
    if _lock.locked():
        return await message.answer("Nusxa olinmoqda, biroz kuting...")
    async with _lock:
        wait = await message.answer(R("[[st_progress]] Bazaning zaxira nusxasi olinmoqda..."))
        try:
            path = await asyncio.to_thread(create_backup, config.db_path, config.backup_dir, config.backup_keep)
        except Exception as ex:
            log.exception("Backup xatosi")
            return await wait.edit_text(R(f"[[stop]] Nusxa olinmadi: <code>{esc(ex)}</code>"))
        await message.answer_document(
            FSInputFile(path),
            caption=R(
                "[[lock]] <b>Baza nusxasi</b>\n"
                f"<blockquote>Serverda ham saqlandi: <code>{esc(path)}</code>\n"
                "Bo'lim botlari tokenlari shifrlangan — tiklash uchun SECRET_KEY "
                "(yoki data/.secret.key) ham kerak bo'ladi.</blockquote>"
            ),
        )
        await wait.delete()


@router.message(Command("status"))
async def status_cmd(message: Message, db: Database, manager: BotManager):
    bots = await db.bots()
    running = sum(1 for b in bots if manager.is_running(b["id"]))
    size = os.path.getsize(config.db_path) / 1024 / 1024 if os.path.exists(config.db_path) else 0
    s = await db.stats()
    auto = f"har kuni {config.backup_hour:02d}:00" if config.backup_hour >= 0 else "o'chirilgan"
    await message.answer(R(
        "[[panel]] <b>Tizim holati</b>\n"
        f"<blockquote>[[active]] Ishlash vaqti: <b>{_uptime()}</b>\n"
        f"[[robot]] Bo'lim botlari: <b>{running}</b> / {len(bots)} ishlayapti\n"
        f"[[envelope]] Murojaatlar: <b>{s.get('total', 0)}</b>\n"
        f"[[folder]] Baza hajmi: <b>{size:.1f} MB</b>\n"
        f"[[clock]] Avto-backup: <b>{auto}</b>"
        f" (oxirgi {config.backup_keep} ta saqlanadi)\n"
        f"[[id]] Python {platform.python_version()} · {esc(sys.platform)}</blockquote>"
    ))
