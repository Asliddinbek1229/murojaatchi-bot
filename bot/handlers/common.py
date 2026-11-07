from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db import Database
from bot.keyboards import (
    RB_CANCEL,
    admin_menu,
    student_menu,
    super_menu,
)
from bot.texts import student_welcome
from bot.ui import R, match
from bot.utils import can_access_appeal, drop_ack, esc, send_appeal

router = Router(name="common")


def menu_for(is_main: bool, is_admin: bool, is_super: bool):
    if is_main:
        return super_menu()
    return admin_menu() if is_admin else student_menu()


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, bot: Bot, db: Database,
                    bot_rec: dict | None, bot_id: int, is_main: bool, is_admin: bool, is_super: bool):
    await drop_ack(bot, message.chat.id, state)
    await state.clear()
    name = esc(message.from_user.full_name)
    menu = menu_for(is_main, is_admin, is_super)

    # ----- asosiy bot -----
    if is_main:  # oddiy foydalanuvchilarni main_user routeri ushlaydi — bu yerga faqat superadmin keladi
        if is_super:
            await message.answer(R(
                f"[[wave]] Assalomu alaykum, <b>{name}</b>!\n\n"
                "<blockquote>[[panel]] Siz <b>superadmin</b>siz.\n"
                "[[robot]] «Admin panel» → «Bo'lim botlari» — bo'lim botlarini qo'shish, adminlar tayinlash.\n"
                "Shuningdek: statistika, murojaatlar, bloklar, e'lonlar va premium emojilar.\n\n"
                "Bo'lim botlarida siz avtomatik ravishda admin hisoblanasiz.</blockquote>"
            ), reply_markup=menu)
            return
    # ----- bo'lim boti -----
    title = bot_rec["title"]
    args = command.args or ""
    if is_admin:
        await message.answer(R(
            f"[[wave]] Assalomu alaykum, <b>{name}</b>!\n\n"
            f"<blockquote>[[admins]] Siz <b>{esc(title)}</b> botining {'superadmini' if is_super else 'admini'}siz.\n"
            "[[bell]] Yangi murojaatlar shu yerga avtomatik keladi.\n"
            "[[inbox]] «Ochiq murojaatlar» — javob kutayotganlar ro'yxati.\n"
            "[[reply]] Murojaat ostidagi «Javob yozish» orqali javob qaytarasiz.</blockquote>\n"
            + ("[[lock]] Bu botda murojaatchilar anonim — ularning kimligi sizga ko'rsatilmaydi."
               if bot_rec.get("anonymous", 1) else
               "[[user]] Bu botda murojaatlar anonim emas — murojaatchi ismi, username va ID si kartada ko'rinadi, "
               "«Murojaatchi bilan bog'lanish» tugmasi orqali unga yozishingiz mumkin.")
        ), reply_markup=menu)
        if args.startswith("ap_") and args[3:].isdigit():
            appeal = await db.get_appeal(int(args[3:]))
            if appeal and await can_access_appeal(db, message.from_user.id, appeal, bot_id):
                await send_appeal(bot, message.chat.id, db, appeal, history=True)
        return
    if args == "admin":
        await message.answer(R(
            "[[stop]] Siz bu botda admin emassiz yoki adminligingiz to'xtatilgan.\n"
            "Superadmin bilan bog'laning."
        ))
    await message.answer(student_welcome(title, bool(bot_rec.get("anonymous", 1))), reply_markup=menu)


@router.message(Command("cancel"))
@router.message(match(RB_CANCEL))
async def cancel(message: Message, state: FSMContext, bot: Bot, is_main: bool, is_admin: bool, is_super: bool):
    await drop_ack(bot, message.chat.id, state)
    await state.clear()
    await message.answer(
        R("[[cancel]] Bekor qilindi. Hech narsa yuborilmadi."),
        reply_markup=menu_for(is_main, is_admin, is_super),
    )


@router.callback_query(F.data == "col:cancel")
async def cancel_cb(call: CallbackQuery, state: FSMContext, is_main: bool, is_admin: bool, is_super: bool):
    await state.clear()
    await call.message.edit_text(R("[[cancel]] Bekor qilindi. Hech narsa yuborilmadi."))
    await call.message.answer(R("[[back]] Bosh menyu"), reply_markup=menu_for(is_main, is_admin, is_super))
    await call.answer()


@router.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(R(f"[[id]] Sizning Telegram ID: <code>{message.from_user.id}</code>"))
