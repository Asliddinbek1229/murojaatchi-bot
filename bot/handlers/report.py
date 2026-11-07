"""Excel hisobotlarni yuklab olish.

- Bo'lim botida: shu botning adminlari (va superadmin) — «Hisobot» tugmasi → davr → .xlsx
- Asosiy botda: superadmin — Admin panel → Excel hisobotlar → bo'lim (yoki hammasi) → davr → .xlsx
"""
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.db import Database
from bot.filters import IsAdmin, IsDeptBot, IsMainBot, IsSuperAdmin
from bot.keyboards import RB_REPORT, bot_choice_kb, period_kb
from bot.reports import PERIODS, make_report
from bot.ui import R, match
from bot.utils import esc, user_lock

log = logging.getLogger(__name__)

dept_router = Router(name="report_dept")
dept_router.message.filter(IsDeptBot(), IsAdmin())
dept_router.callback_query.filter(IsDeptBot(), IsAdmin())

main_router = Router(name="report_main")
main_router.message.filter(IsMainBot(), IsSuperAdmin())
main_router.callback_query.filter(IsMainBot(), IsSuperAdmin())

PERIOD_HELP = (
    "<blockquote>[[calendar]] <b>Haftalik</b> — dushanbadan yakshanbagacha\n"
    "[[calendar]] <b>Oylik</b> — oyning 1-kunidan oxirigacha\n"
    "[[calendar]] <b>Yillik</b> — 1-yanvardan 31-dekabrgacha (oylar kesimida)</blockquote>\n"
    "Hisobot davr ichida <b>kelgan</b> murojaatlar bo'yicha tuziladi. "
    "Faylda: umumiy ko'rsatkichlar va diagrammalar, adminlar faoliyati, murojaatlar ro'yxati."
)


def _caption(scope: str, period_text: str, s: dict) -> str:
    pct = f" ({s['answered'] / s['total'] * 100:.0f}%)" if s["total"] else ""
    avg = f"{s['avg_answer']} soat" if s["avg_answer"] is not None else "—"
    return R(
        f"[[excel]] <b>{esc(scope)}</b>\n"
        f"<blockquote>[[calendar]] {esc(period_text)}\n"
        f"[[envelope]] Jami murojaatlar: <b>{s['total']}</b>\n"
        f"[[st_answered]] Javob olgan: <b>{s['answered']}</b>{pct}\n"
        f"[[st_progress]] Javob kutmoqda: <b>{s['open']}</b>\n"
        f"[[st_rejected]] Rad etilgan: <b>{s['rejected']}</b>\n"
        f"[[clock]] O'rtacha javob muddati: <b>{avg}</b></blockquote>"
    )


async def _generate(call: CallbackQuery, bot: Bot, db: Database, code: str, bot_id: int | None, scope: str):
    if code not in PERIODS:
        return await call.answer("Noma'lum davr", show_alert=True)
    lock = user_lock(call.from_user.id)
    if lock.locked():
        return await call.answer("Oldingi hisobot hali tayyorlanmoqda, biroz kuting.", show_alert=True)
    async with lock:
        await call.answer("Hisobot tayyorlanmoqda...")
        await call.message.edit_text(R(f"[[st_progress]] <b>{esc(scope)}</b> — «{PERIODS[code]}» hisoboti tayyorlanmoqda..."))
        try:
            content, filename, summary, period_text = await make_report(db, code, bot_id, scope)
            await bot.send_document(
                call.message.chat.id,
                BufferedInputFile(content, filename=filename),
                caption=_caption(scope, period_text, summary),
            )
            await call.message.edit_text(R(
                f"[[send]] Hisobot tayyor: <b>{esc(scope)}</b> — «{PERIODS[code]}».\n"
                "Boshqa davr kerak bo'lsa, «Hisobot» tugmasini qayta bosing."
            ))
        except TelegramAPIError as ex:
            log.exception("Hisobotni yuborib bo'lmadi")
            await call.message.edit_text(R(f"[[stop]] Hisobotni yuborib bo'lmadi: <code>{esc(ex)}</code>"))
        except Exception as ex:
            log.exception("Hisobot tayyorlashda xato")
            await call.message.edit_text(R(f"[[stop]] Hisobot tayyorlashda xato: <code>{esc(ex)}</code>"))


# ================= Bo'lim boti =================
@dept_router.message(match(RB_REPORT))
async def dept_report_menu(message: Message, bot_rec: dict):
    await message.answer(
        R(f"[[report]] <b>Excel hisobot — {esc(bot_rec['title'])}</b>\n\nDavrni tanlang:\n") + R(PERIOD_HELP),
        reply_markup=period_kb("rep:d"),
    )


@dept_router.callback_query(F.data.startswith("rep:d:"))
async def dept_report(call: CallbackQuery, bot: Bot, db: Database, bot_id: int, bot_rec: dict):
    await _generate(call, bot, db, call.data.split(":")[2], bot_id, bot_rec["title"])


@dept_router.callback_query(F.data == "rep:cancel")
async def dept_cancel(call: CallbackQuery):
    await call.message.edit_text(R("[[cancel]] Hisobot bekor qilindi."))
    await call.answer()


# ================= Asosiy bot (superadmin) =================
@main_router.callback_query(F.data == "sa:reports")
async def main_reports(call: CallbackQuery, db: Database):
    bots = await db.bots()
    await call.message.edit_text(
        R(
            "[[report]] <b>Excel hisobotlar</b>\n\n"
            "<blockquote>Qaysi bo'lim hisoboti kerak? «Barcha bo'limlar» — umumiy hisobot: "
            "unda qo'shimcha «Bo'limlar» varag'ida har bir bo'lim alohida ko'rsatiladi.</blockquote>"
        ),
        reply_markup=bot_choice_kb(bots, "sa:rpb", "Barcha bo'limlar (umumiy)"),
    )
    await call.answer()


async def _scope(db: Database, scope: str) -> tuple[int | None, str] | None:
    if scope == "a":
        return None, "Barcha bo'limlar"
    b = await db.get_bot(int(scope))
    return (b["id"], b["title"]) if b else None


@main_router.callback_query(F.data.startswith("sa:rpb:"))
async def main_report_period(call: CallbackQuery, db: Database):
    scope = call.data.split(":")[2]
    res = await _scope(db, scope)
    if not res:
        return await call.answer("Bot topilmadi", show_alert=True)
    await call.message.edit_text(
        R(f"[[report]] <b>Excel hisobot — {esc(res[1])}</b>\n\nDavrni tanlang:\n") + R(PERIOD_HELP),
        reply_markup=period_kb(f"sa:rpp:{scope}", back="sa:reports"),
    )
    await call.answer()


@main_router.callback_query(F.data.startswith("sa:rpp:"))
async def main_report(call: CallbackQuery, bot: Bot, db: Database):
    _, _, scope, code = call.data.split(":")
    res = await _scope(db, scope)
    if not res:
        return await call.answer("Bot topilmadi", show_alert=True)
    await _generate(call, bot, db, code, res[0], res[1])
