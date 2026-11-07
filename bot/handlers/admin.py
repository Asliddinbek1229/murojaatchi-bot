"""Bo'lim botidagi admin: murojaatni qabul qilish / rad etish, javob yozish, yopish.

Holat o'zgarishlari atomar (ikki admin bir vaqtda bossa — faqat bittasi o'tadi) va
har bir o'zgarishdan keyin barcha adminlardagi murojaat kartalari bir vaqtda yangilanadi.
"""
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db import STATUSES, Database
from bot.filters import IsAdmin, IsDeptBot
from bot.keyboards import (
    RB_MYSTATS,
    RB_OPEN,
    RB_SEND,
    admin_menu,
    appeals_list_kb,
    collect_kb,
    reject_kb,
)
from bot.states import RejectSG, ReplySG
from bot.ui import R, match, status_label
from bot.utils import (
    MAX_ITEMS,
    can_access_appeal,
    collect,
    drop_ack,
    esc,
    preview,
    refresh_cards,
    send_appeal,
    send_content,
    undo_last,
    user_lock,
)

log = logging.getLogger(__name__)

router = Router(name="admin")
router.message.filter(IsDeptBot(), IsAdmin())
router.callback_query.filter(IsDeptBot(), IsAdmin())


# ---------- yordamchilar ----------
async def _get_accessible(call: CallbackQuery, db: Database, appeal_id: int, bot_id: int):
    appeal = await db.get_appeal(appeal_id)
    if not appeal:
        await call.answer("Murojaat topilmadi", show_alert=True)
        return None
    if not await can_access_appeal(db, call.from_user.id, appeal, bot_id):
        await call.answer("Bu murojaat boshqa botga tegishli yoki sizda ruxsat yo'q", show_alert=True)
        return None
    return appeal


def _aid(call: CallbackQuery) -> int:
    return int(call.data.split(":")[2])


async def _notify_student(bot: Bot, user_id: int, text: str) -> bool:
    try:
        await bot.send_message(user_id, text)
        return True
    except TelegramAPIError as ex:
        log.info("Talabaga xabar yuborilmadi (%s): %s", user_id, ex)
        return False


async def _stale(call: CallbackQuery, bot: Bot, db: Database, appeal_id: int):
    """Holat boshqa admin tomonidan allaqachon o'zgartirilgan — kartani yangilab, tushuntiramiz."""
    appeal = await db.get_appeal(appeal_id)
    who = f" ({appeal['admin_name']})" if appeal and appeal.get("admin_name") else ""
    st = STATUSES.get(appeal["status"], ("", appeal["status"]))[1] if appeal else "?"
    await refresh_cards(bot, db, appeal_id)
    await call.answer(f"Bu amalni bajarib bo'lmaydi: murojaat holati allaqachon «{st}»{who}.", show_alert=True)


# ---------- ro'yxat va statistika ----------
@router.message(match(RB_OPEN))
async def open_appeals(message: Message, state: FSMContext, db: Database, bot_id: int):
    if await state.get_state() == RejectSG.reason.state:
        await state.clear()  # rad etish sababi kutilayotgan bo'lsa — bekor qilamiz
    appeals = await db.open_queue(bot_id)
    if not appeals:
        await message.answer(R(
            "[[party]] <b>Ochiq murojaatlar yo'q.</b>\n"
            "<blockquote>Barcha murojaatlarga javob berilgan yoki ular yopilgan.</blockquote>"
        ))
        return
    new = sum(1 for a in appeals if a["status"] == "new")
    await message.answer(
        R(
            f"[[inbox]] <b>Ochiq murojaatlar</b> — {len(appeals)} ta\n"
            f"<blockquote>[[st_new]] Yangi (qabul qilinmagan): <b>{new}</b>\n"
            f"[[st_progress]] Qabul qilingan, javob kutmoqda: <b>{len(appeals) - new}</b>\n\n"
            "Eng eskisi birinchi turibdi. Ochish uchun tanlang.</blockquote>\n"
            "[[tip]] Javob yuborilgan yoki yopilgan murojaatlar bu ro'yxatda ko'rinmaydi."
        ),
        reply_markup=appeals_list_kb(appeals),
    )


@router.message(match(RB_MYSTATS))
async def my_stats(message: Message, state: FSMContext, db: Database, bot_id: int, bot_rec: dict):
    if await state.get_state() == RejectSG.reason.state:
        await state.clear()
    s = await db.admin_stats(message.from_user.id, bot_id)
    await message.answer(R(
        "[[stats]] <b>Sizning statistikangiz</b>\n\n"
        f"<blockquote>[[robot]] Bo'lim: <b>{esc(bot_rec['title'])}</b>\n"
        f"[[st_progress]] Hozir ishingizda: <b>{s['in_work']}</b>\n"
        f"[[st_answered]] Javob berilgan murojaatlar: <b>{s['answered']}</b>\n"
        f"[[mail]] Yuborilgan javob xabarlari: <b>{s['replies']}</b>\n"
        f"[[st_closed]] Yopilgan: <b>{s['closed']}</b>\n"
        f"[[st_rejected]] Rad etilgan: <b>{s['rejected']}</b></blockquote>"
    ))


@router.callback_query(F.data.startswith("ap:open:"))
async def open_appeal(call: CallbackQuery, bot_id: int, db: Database, bot: Bot):
    appeal = await _get_accessible(call, db, _aid(call), bot_id)
    if not appeal:
        return
    await call.answer()
    await send_appeal(bot, call.from_user.id, db, appeal)


@router.callback_query(F.data.startswith("ap:history:"))
async def appeal_history(call: CallbackQuery, bot_id: int, db: Database, bot: Bot):
    appeal = await _get_accessible(call, db, _aid(call), bot_id)
    if not appeal:
        return
    await call.answer()
    await send_appeal(bot, call.from_user.id, db, appeal, history=True)


# ---------- qabul qilish ----------
@router.callback_query(F.data.startswith("ap:accept:"))
async def accept(call: CallbackQuery, bot_id: int, db: Database, bot: Bot):
    appeal = await _get_accessible(call, db, _aid(call), bot_id)
    if not appeal:
        return
    if not await db.transition(appeal["id"], ["new"], "in_progress", call.from_user.id):
        return await _stale(call, bot, db, appeal["id"])
    await call.answer(f"Murojaat #{appeal['id']} qabul qilindi. Endi javob yozishingiz mumkin.")
    await _notify_student(bot, appeal["user_id"], R(
        f"[[accept]] <b>Murojaatingiz #{appeal['id']} qabul qilindi!</b>\n\n"
        "<blockquote>Mas'ul xodim murojaatingizni ko'rib chiqmoqda. "
        "Tez orada javobini shu bot orqali yetkazamiz.</blockquote>"
    ))
    await refresh_cards(bot, db, appeal["id"])


# ---------- rad etish ----------
@router.callback_query(F.data.startswith("ap:reject:"))
async def reject_start(call: CallbackQuery, bot_id: int, state: FSMContext, db: Database):
    appeal = await _get_accessible(call, db, _aid(call), bot_id)
    if not appeal:
        return
    if appeal["status"] != "new":
        return await call.answer("Faqat yangi (hali qabul qilinmagan) murojaatni rad etish mumkin.", show_alert=True)
    await state.set_state(RejectSG.reason)
    await state.update_data(appeal_id=appeal["id"])
    await call.answer()
    await call.message.answer(
        R(
            f"[[reject]] <b>Murojaat #{appeal['id']} ni rad etish</b>\n\n"
            "<blockquote>Rad etish <b>sababini</b> bitta xabar qilib yozing — u murojaatchiga yuboriladi.\n"
            "Masalan: «Murojaat bu bo'limga tegishli emas, Yotoqxona botiga murojaat qiling».</blockquote>\n"
            "Yoki sababsiz rad eting:"
        ),
        reply_markup=reject_kb(appeal["id"]),
    )


async def _do_reject(bot: Bot, db: Database, appeal_id: int, admin_id: int, reason: str | None) -> bool:
    if not await db.transition(appeal_id, ["new"], "rejected", admin_id, reject_reason=reason):
        return False
    appeal = await db.get_appeal(appeal_id)
    reason_text = (
        f"<blockquote>[[st_rejected]] <b>Sabab:</b> {esc(reason)}</blockquote>\n" if reason else ""
    )
    await _notify_student(bot, appeal["user_id"], R(
        f"[[reject]] <b>Murojaatingiz #{appeal_id} rad etildi.</b>\n\n"
        + reason_text
        + "[[tip]] Agar masala hali dolzarb bo'lsa, ma'lumotlarni aniqlashtirib, yangi murojaat yuborishingiz mumkin."
    ))
    await refresh_cards(bot, db, appeal_id)
    return True


@router.message(RejectSG.reason, F.text)
async def reject_with_reason(message: Message, state: FSMContext, db: Database, bot: Bot):
    appeal_id = (await state.get_data())["appeal_id"]
    await state.clear()
    ok = await _do_reject(bot, db, appeal_id, message.from_user.id, message.text.strip()[:500])
    await message.answer(
        R(f"[[st_rejected]] Murojaat #{appeal_id} rad etildi, murojaatchiga sabab bilan xabar yuborildi.") if ok
        else R("[[warn]] Rad etib bo'lmadi: murojaat holati allaqachon o'zgargan (boshqa admin ishlagan)."),
        reply_markup=admin_menu(),
    )


@router.message(RejectSG.reason)
async def reject_reason_not_text(message: Message):
    await message.answer(R("[[warn]] Sababni <b>matn</b> ko'rinishida yozing yoki «Sababsiz rad etish» ni bosing."))


@router.callback_query(F.data.startswith("ap:rejnr:"))
async def reject_no_reason(call: CallbackQuery, state: FSMContext, bot_id: int, db: Database, bot: Bot):
    appeal = await _get_accessible(call, db, _aid(call), bot_id)
    if not appeal:
        return
    await state.clear()
    if not await _do_reject(bot, db, appeal["id"], call.from_user.id, None):
        return await _stale(call, bot, db, appeal["id"])
    await call.message.edit_text(R(f"[[st_rejected]] Murojaat #{appeal['id']} rad etildi."))
    await call.message.answer(R("[[back]] Bosh menyu"), reply_markup=admin_menu())
    await call.answer()


@router.callback_query(F.data == "ap:rejcancel")
async def reject_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(R("[[back]] Rad etish bekor qilindi — murojaat o'zgarishsiz qoldi."))
    await call.message.answer(R("[[back]] Bosh menyu"), reply_markup=admin_menu())
    await call.answer()


# ---------- javob yozish ----------
@router.callback_query(F.data.startswith("ap:reply:"))
async def start_reply(call: CallbackQuery, bot_id: int, state: FSMContext, db: Database, bot: Bot):
    appeal = await _get_accessible(call, db, _aid(call), bot_id)
    if not appeal:
        return
    if appeal["status"] == "new":
        return await call.answer("Avval murojaatni «Qabul qilish» tugmasi bilan qabul qiling.", show_alert=True)
    if appeal["status"] not in ("in_progress", "answered"):
        return await _stale(call, bot, db, appeal["id"])
    await drop_ack(bot, call.message.chat.id, state)
    await state.set_state(ReplySG.content)
    await state.set_data({"appeal_id": appeal["id"], "items": [], "ack_id": None})
    await call.answer()
    await call.message.answer(
        R(
            f"[[reply]] <b>Murojaat #{appeal['id']} ga javob yozing</b>\n\n"
            "<blockquote>[[one]] Javob matnini yozing.\n"
            "[[two]] Kerak bo'lsa rasm, video yoki hujjat qo'shing "
            f"(ko'pi bilan {MAX_ITEMS} ta xabar).\n"
            "[[three]] Tayyor bo'lgach <b>«Yuborish»</b> ni bosing.</blockquote>\n\n"
            "[[warn]] «Yuborish» bosilmaguncha talabaga hech narsa bormaydi.\n"
            "[[lock]] Talaba sizning kimligingizni ko'rmaydi."
        ),
        reply_markup=collect_kb("Javob matnini yozing..."),
    )


async def _submit_reply(bot: Bot, db: Database, state: FSMContext, chat_id: int, admin_id: int):
    async with user_lock(admin_id):  # ikki marta bosilsa ham javob bir marta ketadi
        data = await state.get_data()
        items = data.get("items", [])
        if await state.get_state() != ReplySG.content.state:
            return
        if not items:
            await bot.send_message(chat_id, R("[[warn]] Avval javob matnini yoki faylni yuboring."))
            return
        appeal = await db.get_appeal(data["appeal_id"])
        if not appeal or appeal["status"] not in ("in_progress", "answered"):
            await drop_ack(bot, chat_id, state)
            await state.clear()
            st = status_label(appeal["status"]) if appeal else "—"
            await bot.send_message(
                chat_id,
                R(f"[[warn]] Javob yuborilmadi: murojaat holati o'zgargan ({st}). Kerak bo'lsa, uni qayta oching."),
                reply_markup=admin_menu(),
            )
            return
        await drop_ack(bot, chat_id, state)
        await state.clear()
    try:
        await bot.send_message(appeal["user_id"], R(f"[[mail]] <b>Murojaatingiz #{appeal['id']} ga javob:</b>"))
        for item in items:
            await send_content(bot, appeal["user_id"], item)
    except TelegramAPIError as ex:
        await bot.send_message(
            chat_id,
            R(f"[[stop]] Javobni yetkazib bo'lmadi (talaba botni bloklagan bo'lishi mumkin).\n<code>{esc(ex)}</code>"),
            reply_markup=admin_menu(),
        )
        return
    for item in items:
        await db.add_message(appeal["id"], "admin", admin_id, item)
    await db.transition(appeal["id"], ["in_progress", "answered"], "answered", admin_id)
    await refresh_cards(bot, db, appeal["id"])
    await bot.send_message(
        chat_id,
        R(
            f"[[st_answered]] <b>Javob yuborildi!</b>\n"
            f"<blockquote>Murojaat #{appeal['id']} muallifiga {len(items)} ta xabar yetkazildi.\n"
            "Murojaat «Ochiq murojaatlar» ro'yxatidan chiqarildi.\n"
            "Masala to'liq hal bo'lgan bo'lsa — kartadagi «Yopish» tugmasini bosing.</blockquote>"
        ),
        reply_markup=admin_menu(),
    )


@router.message(ReplySG.content, match(RB_SEND))
async def send_reply_btn(message: Message, state: FSMContext, db: Database, bot: Bot):
    await _submit_reply(bot, db, state, message.chat.id, message.from_user.id)


@router.callback_query(ReplySG.content, F.data == "col:send")
async def send_reply_cb(call: CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    await call.answer()
    await _submit_reply(bot, db, state, call.message.chat.id, call.from_user.id)


@router.callback_query(ReplySG.content, F.data == "col:undo")
async def undo_reply(call: CallbackQuery, state: FSMContext, bot: Bot):
    removed = await undo_last(bot, call.message.chat.id, call.from_user.id, state, "admin")
    await call.answer("Oxirgi xabar o'chirildi" if removed else "O'chiradigan xabar yo'q")


@router.callback_query(ReplySG.content, F.data == "col:preview")
async def preview_reply(call: CallbackQuery, state: FSMContext, bot: Bot):
    await call.answer()
    await preview(bot, call.message.chat.id, state, "admin")


@router.message(ReplySG.content)
async def collect_reply(message: Message, state: FSMContext, bot: Bot):
    await collect(message, state, bot, "admin")


# ---------- yopish / qayta ochish ----------
@router.callback_query(F.data.startswith("ap:close:"))
async def close_appeal(call: CallbackQuery, bot_id: int, db: Database, bot: Bot):
    appeal = await _get_accessible(call, db, _aid(call), bot_id)
    if not appeal:
        return
    if not await db.transition(appeal["id"], ["in_progress", "answered"], "closed", call.from_user.id):
        return await _stale(call, bot, db, appeal["id"])
    await call.answer(f"Murojaat #{appeal['id']} yopildi")
    await _notify_student(bot, appeal["user_id"], R(
        f"[[st_closed]] <b>Murojaatingiz #{appeal['id']} yopildi.</b>\n"
        "<blockquote>Murojaatingiz ko'rib chiqildi va yakunlandi. "
        "Yangi savol yoki muammo bo'lsa, yangi murojaat yuborishingiz mumkin.</blockquote>"
    ))
    await refresh_cards(bot, db, appeal["id"])


@router.callback_query(F.data.startswith("ap:reopen:"))
async def reopen_appeal(call: CallbackQuery, bot_id: int, db: Database, bot: Bot):
    appeal = await _get_accessible(call, db, _aid(call), bot_id)
    if not appeal:
        return
    if not await db.transition(appeal["id"], ["closed", "rejected"], "in_progress", call.from_user.id):
        return await _stale(call, bot, db, appeal["id"])
    await call.answer(f"Murojaat #{appeal['id']} qayta ochildi")
    await _notify_student(bot, appeal["user_id"], R(
        f"[[st_progress]] <b>Murojaatingiz #{appeal['id']} qayta ko'rib chiqilmoqda.</b>\n"
        "<blockquote>Javob tayyor bo'lishi bilan shu bot orqali yetkazamiz.</blockquote>"
    ))
    await refresh_cards(bot, db, appeal["id"])


@router.message()
async def admin_fallback(message: Message):
    await message.answer(R("[[tip]] Quyidagi menyudan foydalaning."), reply_markup=admin_menu())
