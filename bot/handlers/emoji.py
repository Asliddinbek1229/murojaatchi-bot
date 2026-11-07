"""Superadmin: botdagi emojilarni premium (custom) emojiga almashtirish."""
import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import ui
from bot.db import Database
from bot.filters import IsMainBot, IsSuperAdmin
from bot.keyboards import (
    EMOJI_PAGE,
    cancel_kb,
    confirm_kb,
    emoji_card_kb,
    emoji_list_kb,
    emoji_menu_kb,
    emoji_wizard_kb,
    ikb,
    super_menu,
)
from bot.states import EmojiSG
from bot.ui import EMOJI, R, ibtn, plain

log = logging.getLogger(__name__)

router = Router(name="emoji")
router.message.filter(IsMainBot(), IsSuperAdmin())
router.callback_query.filter(IsMainBot(), IsSuperAdmin())


def _extract(message: Message) -> list[tuple[str, str]]:
    """Xabardagi barcha premium emojilar: [(custom_emoji_id, alt), ...] (tartib bo'yicha)."""
    text = message.text or message.caption or ""
    ents = message.entities or message.caption_entities or []
    out = [(en.custom_emoji_id, en.extract_from(text)) for en in ents if en.type == "custom_emoji"]
    if not out and message.sticker and message.sticker.custom_emoji_id:
        out.append((message.sticker.custom_emoji_id, message.sticker.emoji or "⭐️"))
    return out


async def _apply(bot: Bot, db: Database, chat_id: int, pairs: list[tuple[str, tuple[str, str]]]) -> bool:
    """Emojilarni biriktiradi va sinov xabari bilan tekshiradi. Xato bo'lsa — qaytaradi."""
    old = {k: ui.custom_of(k) for k, _ in pairs}
    for key, (cid, alt) in pairs:
        ui.set_local(key, cid, alt)
    try:
        lines = "\n".join(f"{plain(k)} → {ui.premium_preview(k)}  <i>{EMOJI[k][1]}</i>" for k, _ in pairs)
        await bot.send_message(
            chat_id,
            R("[[send]] <b>Saqlandi:</b>\n") + f"<blockquote>{lines}</blockquote>",
            reply_markup=ikb([ibtn(pairs[0][0], "Tugmada shunday ko'rinadi", "em:noop")]),
        )
    except TelegramAPIError as ex:
        for key, prev in old.items():
            ui.set_local(key, *(prev or (None,)))
        await bot.send_message(
            chat_id,
            "⚠️ <b>Telegram bu premium emojini qabul qilmadi, saqlanmadi.</b>\n"
            "<blockquote>Bot egasining akkauntida Telegram Premium faol ekanini tekshiring.\n"
            f"<code>{html.escape(str(ex))}</code></blockquote>",
        )
        return False
    for key, (cid, alt) in pairs:
        await db.set_custom_emoji(key, cid, alt)
    return True


# =============== Menyu ===============
def _menu_text() -> str:
    total, done = len(EMOJI), ui.custom_count()
    status = R("[[active]] Yoqilgan") if ui.is_enabled() else R("[[inactive]] O'chirilgan")
    return R(
        "[[sparkles]] <b>Premium emojilar</b>\n\n"
        f"<blockquote>Botda <b>{total} ta</b> emoji ishlatiladi, shundan <b>{done} tasi</b> premiumga almashtirilgan.\n"
        f"Premium ko'rinish: {status}</blockquote>\n\n"
        "<blockquote expandable>[[tip]] <b>Qanday ishlaydi?</b>\n"
        "• Har bir oddiy emojiga premium emoji biriktirasiz — u bot matnlarida va tugmalarida "
        "(tugma ikonkasi sifatida) ko'rinadi.\n"
        "• Bu imkoniyat bot egasining akkauntida Telegram Premium bo'lgani uchun ishlaydi.\n"
        "• <b>Ro'yxat</b> — har bir emojini alohida sozlash. Ro'yxatda emojilar oddiy ko'rinishda, "
        "premium biriktirilganlari yashil.\n"
        "• <b>Ketma-ket sozlash</b> — bot emojilarni birma-bir ko'rsatadi, siz premium emoji yuborasiz. "
        "Bitta xabarda bir nechta premium emoji yuborsangiz, ular navbatdagilarga tartib bilan biriktiriladi.\n"
        "• <b>Premiumni o'chirish</b> — hammasi bir zumda oddiy emojiga qaytadi (sozlamalar saqlanib qoladi).</blockquote>"
    )


@router.callback_query(F.data == "em:menu")
async def menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(_menu_text(), reply_markup=emoji_menu_kb(ui.is_enabled()))
    await call.answer()


@router.callback_query(F.data == "em:noop")
async def noop(call: CallbackQuery):
    await call.answer("Bu shunchaki namuna tugma")


@router.callback_query(F.data == "em:toggle")
async def toggle(call: CallbackQuery, db: Database):
    ui.set_enabled(not ui.is_enabled())
    await db.set_setting("premium_enabled", "1" if ui.is_enabled() else "0")
    await call.message.edit_text(_menu_text(), reply_markup=emoji_menu_kb(ui.is_enabled()))
    await call.message.answer(R("[[sparkles]] Menyu yangilandi."), reply_markup=super_menu())
    await call.answer("Premium yoqildi" if ui.is_enabled() else "Premium o'chirildi")


@router.callback_query(F.data == "em:clear")
async def clear_ask(call: CallbackQuery):
    await call.message.edit_text(
        R("[[trash]] <b>Barcha premium emojilar o'chirilsinmi?</b>\nHammasi oddiy holiga qaytadi."),
        reply_markup=confirm_kb("em:clearok", "em:menu"),
    )
    await call.answer()


@router.callback_query(F.data == "em:clearok")
async def clear(call: CallbackQuery, db: Database):
    await db.clear_custom_emojis()
    await ui.load(db)
    await call.message.edit_text(_menu_text(), reply_markup=emoji_menu_kb(ui.is_enabled()))
    await call.message.answer(R("[[reset]] Hammasi oddiy holiga qaytarildi."), reply_markup=super_menu())
    await call.answer()


# =============== Ro'yxat va bitta emoji ===============
@router.callback_query(F.data.startswith("em:list:"))
async def emoji_list(call: CallbackQuery, state: FSMContext):
    await state.clear()
    page = int(call.data.split(":")[2])
    pages = (len(EMOJI) + EMOJI_PAGE - 1) // EMOJI_PAGE
    await call.message.edit_text(
        R(f"[[list]] <b>Botdagi emojilar</b> (sahifa {page + 1}/{pages})\n\n")
        + "<blockquote>Emojilar <b>oddiy</b> ko'rinishda ko'rsatilgan. "
        "Yashil va ✓ belgili — premium biriktirilgan.\nSozlash uchun emojini tanlang.</blockquote>",
        reply_markup=emoji_list_kb(page),
    )
    await call.answer()


def _card_text(key: str) -> str:
    char, desc = EMOJI[key]
    return R(
        "[[sparkles]] <b>Emoji sozlamasi</b>\n\n"
        f"<blockquote>Qayerda: <b>{desc}</b>\n"
        f"Kalit: <code>{key}</code>\n"
        f"Oddiy: {char}\n"
        f"Premium: {ui.premium_preview(key)}</blockquote>"
    )


@router.callback_query(F.data.startswith("em:key:"))
async def emoji_card(call: CallbackQuery):
    _, _, key, page = call.data.split(":")
    if key not in EMOJI:
        return await call.answer("Topilmadi", show_alert=True)
    await call.message.edit_text(_card_text(key), reply_markup=emoji_card_kb(key, int(page)))
    await call.answer()


@router.callback_query(F.data.startswith("em:del:"))
async def emoji_reset(call: CallbackQuery, db: Database):
    _, _, key, page = call.data.split(":")
    await db.delete_custom_emoji(key)
    ui.set_local(key, None)
    await call.message.edit_text(_card_text(key), reply_markup=emoji_card_kb(key, int(page)))
    await call.answer("Oddiy holiga qaytarildi")


@router.callback_query(F.data.startswith("em:set:"))
async def emoji_set_start(call: CallbackQuery, state: FSMContext):
    _, _, key, page = call.data.split(":")
    await state.set_state(EmojiSG.single)
    await state.update_data(key=key, page=int(page))
    await call.answer()
    await call.message.answer(
        R(f"[[star]] <b>{plain(key)} {EMOJI[key][1]}</b> uchun premium emoji yuboring.\n")
        + "<blockquote>Emoji klaviaturasidan istalgan premium (animatsiyali) emojini tanlab yuboring.</blockquote>",
        reply_markup=cancel_kb(),
    )


@router.message(EmojiSG.single)
async def emoji_set(message: Message, state: FSMContext, db: Database, bot: Bot):
    found = _extract(message)
    if not found:
        await message.answer(R(
            "[[warn]] Bu xabarda premium emoji topilmadi.\n"
            "<blockquote>Oddiy emoji emas, premium (custom) emoji yuboring.</blockquote>"
        ))
        return
    data = await state.get_data()
    key, page = data["key"], data["page"]
    await state.clear()
    ok = await _apply(bot, db, message.chat.id, [(key, found[0])])
    await message.answer(
        R("[[sparkles]] Tayyor.") if ok else R("[[tip]] Boshqa premium emoji bilan qayta urinib ko'ring."),
        reply_markup=super_menu(),
    )
    await message.answer(_card_text(key), reply_markup=emoji_card_kb(key, page))


# =============== Ketma-ket sozlash ===============
async def _wizard_prompt(bot: Bot, chat_id: int, state: FSMContext):
    data = await state.get_data()
    keys, idx = data["keys"], data["idx"]
    if data.get("prompt_id"):
        try:
            await bot.delete_message(chat_id, data["prompt_id"])
        except TelegramAPIError:
            pass
    if idx >= len(keys):
        await state.clear()
        await bot.send_message(
            chat_id,
            R(f"[[party]] <b>Ketma-ket sozlash tugadi!</b>\nPremium emojilar: <b>{ui.custom_count()}/{len(EMOJI)}</b>"),
            reply_markup=super_menu(),
        )
        await bot.send_message(chat_id, _menu_text(), reply_markup=emoji_menu_kb(ui.is_enabled()))
        return
    key = keys[idx]
    char, desc = EMOJI[key]
    msg = await bot.send_message(
        chat_id,
        R(f"[[bolt]] <b>Ketma-ket sozlash</b> — {idx + 1}/{len(keys)}\n\n")
        + f"<blockquote>Oddiy: {char}\nQayerda: <b>{desc}</b>\nHozirgi premium: {ui.premium_preview(key)}</blockquote>\n"
        "Shu emoji uchun <b>premium emoji yuboring</b>.\n"
        "<i>Bir xabarda bir nechtasini yuborsangiz — navbatdagilarga ketma-ket biriktiriladi.</i>",
        reply_markup=emoji_wizard_kb(),
    )
    await state.update_data(prompt_id=msg.message_id)


@router.callback_query(F.data.startswith("em:wiz:"))
async def wizard_start(call: CallbackQuery, state: FSMContext, bot: Bot):
    mode = call.data.split(":")[2]
    keys = [k for k in EMOJI if mode == "all" or not ui.custom_of(k)]
    if not keys:
        return await call.answer("Hamma emojilar allaqachon premium!", show_alert=True)
    await state.set_state(EmojiSG.wizard)
    await state.update_data(keys=keys, idx=0, prompt_id=None)
    await call.answer()
    await call.message.answer(
        R("[[bolt]] Boshladik! Istalgan payt «To'xtatish» yoki «Bekor qilish» ni bosishingiz mumkin."),
        reply_markup=cancel_kb(),
    )
    await _wizard_prompt(bot, call.message.chat.id, state)


@router.message(EmojiSG.wizard)
async def wizard_receive(message: Message, state: FSMContext, db: Database, bot: Bot):
    found = _extract(message)
    if not found:
        await message.answer(R("[[warn]] Premium emoji topilmadi. Premium (custom) emoji yuboring yoki «O'tkazib yuborish» ni bosing."))
        return
    data = await state.get_data()
    keys, idx = data["keys"], data["idx"]
    pairs = list(zip(keys[idx:], found))
    if await _apply(bot, db, message.chat.id, pairs):
        await state.update_data(idx=idx + len(pairs))
    await _wizard_prompt(bot, message.chat.id, state)


@router.callback_query(EmojiSG.wizard, F.data == "em:skip")
async def wizard_skip(call: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(idx=(await state.get_data())["idx"] + 1)
    await call.answer("O'tkazib yuborildi")
    await _wizard_prompt(bot, call.message.chat.id, state)


@router.callback_query(EmojiSG.wizard, F.data == "em:wreset")
async def wizard_reset(call: CallbackQuery, state: FSMContext, db: Database, bot: Bot):
    data = await state.get_data()
    key = data["keys"][data["idx"]]
    await db.delete_custom_emoji(key)
    ui.set_local(key, None)
    await state.update_data(idx=data["idx"] + 1)
    await call.answer("Oddiy holida qoldirildi")
    await _wizard_prompt(bot, call.message.chat.id, state)


@router.callback_query(EmojiSG.wizard, F.data == "em:stop")
async def wizard_stop(call: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(idx=10**6)
    await call.answer("To'xtatildi")
    await _wizard_prompt(bot, call.message.chat.id, state)
