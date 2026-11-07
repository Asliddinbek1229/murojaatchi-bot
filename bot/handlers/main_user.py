"""Asosiy bot faqat superadmin uchun. Boshqalar /start bosganda qisqa ma'lumot oladi, xolos;
boshqa har qanday xabar va tugma e'tiborsiz qoldiriladi."""
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot.filters import IsMainBot, IsNotSuperAdmin
from bot.texts import main_welcome

router = Router(name="main_user")
router.message.filter(IsMainBot(), IsNotSuperAdmin())
router.callback_query.filter(IsMainBot(), IsNotSuperAdmin())


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(main_welcome(), reply_markup=ReplyKeyboardRemove())


@router.message()
async def ignore(message: Message):
    pass


@router.callback_query()
async def ignore_cb(call: CallbackQuery):
    await call.answer()
