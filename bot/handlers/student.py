import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db import Database
from bot.filters import IsDeptBot
from bot.keyboards import (
    RB_HELP,
    RB_MY,
    RB_NEW,
    RB_SEND,
    category_pick_kb,
    collect_kb,
    student_menu,
)
from bot.states import AppealSG
from bot.texts import appeal_sent, category_prompt, content_prompt, student_help
from bot.ui import R, e, match, status_label, tg_time
from bot.utils import collect, deliver_new_appeal, drop_ack, esc, preview, undo_last, user_lock

log = logging.getLogger(__name__)

router = Router(name="student")
router.message.filter(IsDeptBot())
router.callback_query.filter(IsDeptBot())

PLACEHOLDER = "Murojaatingizni yozing yoki fayl yuboring..."


def _anon(bot_rec: dict | None) -> bool:
    return bool((bot_rec or {}).get("anonymous", 1))


@router.message(match(RB_NEW))
async def new_appeal(message: Message, state: FSMContext, bot: Bot, db: Database, bot_id: int, bot_rec: dict):
    await drop_ack(bot, message.chat.id, state)
    # Talabaga murojaat boshida aytilgan rejim saqlanadi: yozish davomida superadmin rejimni
    # o'zgartirsa ham, talaba ogohlantirilmagan holda shaxsi ochilib qolmaydi.
    anonymous = _anon(bot_rec)
    cats = await db.categories(bot_id, only_active=True)
    if cats:  # bu botda kategoriyalar bor — avval mavzu tanlanadi
        await state.set_state(AppealSG.category)
        await state.set_data({"anonymous": anonymous})
        await message.answer(category_prompt(), reply_markup=category_pick_kb(cats))
        return
    await _start_content(message, state, None, None, anonymous=anonymous)


async def _start_content(message: Message, state: FSMContext, cat_id: int | None, cat_title: str | None,
                         description: str | None = None, anonymous: bool = True):
    await state.set_state(AppealSG.content)
    await state.set_data({"items": [], "ack_id": None, "category_id": cat_id, "category": cat_title,
                          "anonymous": anonymous})
    await message.answer(content_prompt(cat_title, description, anonymous), reply_markup=collect_kb(PLACEHOLDER))


@router.callback_query(AppealSG.category, F.data.startswith("cat:pick:"))
async def pick_category(call: CallbackQuery, state: FSMContext, db: Database, bot_id: int, bot_rec: dict):
    anonymous = (await state.get_data()).get("anonymous", _anon(bot_rec))
    cat = await db.get_category(int(call.data.split(":")[2]))
    if not cat or cat["bot_id"] != bot_id or not cat["is_active"]:
        cats = await db.categories(bot_id, only_active=True)
        await call.answer("Bu mavzu endi mavjud emas, boshqasini tanlang.", show_alert=True)
        if cats:
            await call.message.edit_reply_markup(reply_markup=category_pick_kb(cats))
        else:
            await call.message.edit_text(R("[[category]] Mavzu tanlash shart emas."))
            await _start_content(call.message, state, None, None, anonymous=anonymous)
        return
    await call.answer()
    await call.message.edit_text(R(f"[[category]] Mavzu: <b>{esc(cat['title'])}</b>"))
    await _start_content(call.message, state, cat["id"], cat["title"], cat.get("description"), anonymous)


@router.message(AppealSG.category)
async def category_expected(message: Message, db: Database, bot_id: int):
    cats = await db.categories(bot_id, only_active=True)
    await message.answer(
        R("[[warn]] Avval murojaat <b>mavzusini</b> tanlang — pastdagi tugmalardan birini bosing.\n"
          "Matn va fayllarni mavzu tanlangandan keyin yuborasiz."),
        reply_markup=category_pick_kb(cats) if cats else None,
    )


async def _submit(bot: Bot, db: Database, manager, state: FSMContext, chat_id: int, user_id: int, bot_id: int):
    async with user_lock(user_id):  # «Yuborish» ikki marta bosilsa ham murojaat bitta bo'ladi
        if await state.get_state() != AppealSG.content.state:
            return
        data = await state.get_data()
        items = data.get("items", [])
        if not items:
            await bot.send_message(chat_id, R(
                "[[warn]] Murojaat hali bo'sh.\n"
                "<blockquote>Avval muammoingizni matn qilib yozing yoki rasm/video/fayl yuboring, "
                "keyin «Yuborish» tugmasini bosing.</blockquote>"
            ))
            return
        await drop_ack(bot, chat_id, state)
        await state.clear()
        cat_id, cat_title = data.get("category_id"), data.get("category")
        if cat_id and not await db.get_category(cat_id):  # yozish paytida o'chirilgan bo'lsa
            cat_id, cat_title = None, None
        anonymous = data.get("anonymous", True)
        appeal_id = await db.create_appeal(bot_id, user_id, cat_id, anonymous)
        for item in items:
            await db.add_message(appeal_id, "student", user_id, item)
    # talabaga darhol javob, adminlarga yetkazish fonda (tez ishlashi uchun)
    await bot.send_message(chat_id, appeal_sent(appeal_id, cat_title, anonymous), reply_markup=student_menu())
    task = asyncio.create_task(deliver_new_appeal(bot, db, manager, appeal_id))
    task.add_done_callback(_log_task_error)


def _log_task_error(task: asyncio.Task):
    if not task.cancelled() and task.exception():
        log.error("Murojaatni adminlarga yetkazishda xato", exc_info=task.exception())


@router.message(AppealSG.content, match(RB_SEND))
async def send_btn(message: Message, state: FSMContext, db: Database, bot: Bot, manager, bot_id: int):
    await _submit(bot, db, manager, state, message.chat.id, message.from_user.id, bot_id)


@router.callback_query(AppealSG.content, F.data == "col:send")
async def send_cb(call: CallbackQuery, state: FSMContext, db: Database, bot: Bot, manager, bot_id: int):
    await call.answer()
    await _submit(bot, db, manager, state, call.message.chat.id, call.from_user.id, bot_id)


@router.callback_query(AppealSG.content, F.data == "col:undo")
async def undo_cb(call: CallbackQuery, state: FSMContext, bot: Bot):
    removed = await undo_last(bot, call.message.chat.id, call.from_user.id, state, "student")
    if removed and not (await state.get_data()).get("items"):
        await call.message.answer(R("[[undo]] O'chirildi. Murojaat hozir bo'sh — yangi xabar yuboring."))
    await call.answer("Oxirgi xabar o'chirildi" if removed else "O'chiradigan xabar yo'q")


@router.callback_query(AppealSG.content, F.data == "col:preview")
async def preview_cb(call: CallbackQuery, state: FSMContext, bot: Bot):
    await call.answer()
    await preview(bot, call.message.chat.id, state, "student")


@router.message(AppealSG.content)
async def collect_content(message: Message, state: FSMContext, bot: Bot):
    await collect(message, state, bot, "student")


@router.message(match(RB_MY))
async def my_appeals(message: Message, db: Database, bot_id: int):
    appeals = await db.user_appeals(bot_id, message.from_user.id)
    if not appeals:
        await message.answer(R(
            "[[list]] Sizda hali murojaatlar yo'q.\n"
            "Yangi murojaat uchun <b>«Murojaat yuborish»</b> tugmasini bosing."
        ))
        return
    blocks = [
        f"<b>#{a['id']}</b> · {tg_time(a['created_at'])}\n"
        + (f"{e('category')} {esc(a['category_title'])}\n" if a.get("category_title") else "")
        + status_label(a["status"])
        for a in appeals
    ]
    await message.answer(
        R("[[list]] <b>Oxirgi murojaatlaringiz:</b>\n\n")
        + "<blockquote expandable>" + "\n\n".join(blocks) + "</blockquote>"
    )


@router.message(match(RB_HELP))
async def help_msg(message: Message, bot_rec: dict):
    await message.answer(student_help(_anon(bot_rec)), reply_markup=student_menu())


@router.message()
async def fallback(message: Message, is_admin: bool):
    if is_admin:
        return
    await message.answer(
        R(
            "[[tip]] Murojaat yuborish uchun avval <b>«Murojaat yuborish»</b> tugmasini bosing.\n"
            "<blockquote>Shundan keyin yozgan xabarlaringiz murojaatga qo'shiladi.</blockquote>"
        ),
        reply_markup=student_menu(),
    )


@router.callback_query()
async def callback_fallback(call: CallbackQuery):
    await call.answer("⛔️ Bu tugma eskirgan yoki siz uchun mavjud emas.", show_alert=True)
