"""Umumiy yordamchi funksiyalar: kontentni ajratish, qayta yuborish, yig'ish, murojaatni yetkazish."""
import asyncio
import html
import logging
import re
from collections import defaultdict

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import config
from bot.db import Database
from bot.ui import CONTENT_NAMES, R, e, status_label, tg_time

log = logging.getLogger(__name__)

SUPPORTED = tuple(CONTENT_NAMES)
MAX_ITEMS = 10

# Albom (media group) xabarlari bir vaqtda keladi — FSM ma'lumotini buzmaslik uchun qulf
_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def user_lock(user_id: int) -> asyncio.Lock:
    """Bitta foydalanuvchining amallarini ketma-ket bajarish (ikki marta bosishdan himoya)."""
    return _locks[user_id]


def esc(text) -> str:
    return html.escape(str(text)) if text is not None else ""


def extract_content(message: Message) -> dict | None:
    """Xabardan saqlash mumkin bo'lgan kontentni ajratib oladi (premium emoji/formatlash saqlanadi)."""
    ct = str(getattr(message.content_type, "value", message.content_type))
    if ct == "text":
        return {"type": "text", "text": message.html_text}
    if ct not in SUPPORTED:
        return None
    file_id = message.photo[-1].file_id if ct == "photo" else getattr(message, ct).file_id
    caption = message.html_text if message.caption else None
    return {"type": ct, "file_id": file_id, "text": caption}


async def send_content(bot: Bot, chat_id: int, item: dict, reply_markup=None):
    t, fid, text = item["type"], item.get("file_id"), item.get("text")
    kw = {"reply_markup": reply_markup}
    if t == "text":
        return await bot.send_message(chat_id, text, **kw)
    senders = {
        "photo": bot.send_photo, "video": bot.send_video, "document": bot.send_document,
        "audio": bot.send_audio, "voice": bot.send_voice, "animation": bot.send_animation,
    }
    if t in senders:
        return await senders[t](chat_id, fid, caption=text, **kw)
    if t == "video_note":
        return await bot.send_video_note(chat_id, fid, **kw)
    if t == "sticker":
        return await bot.send_sticker(chat_id, fid, **kw)


def items_summary(items: list[dict]) -> str:
    counts: dict[str, int] = {}
    for it in items:
        counts[it["type"]] = counts.get(it["type"], 0) + 1
    return "\n".join(f"{e('c_' + t)} {CONTENT_NAMES[t]} — <b>{n} ta</b>" for t, n in counts.items())


# ---------- Xabarlarni yig'ish (talaba murojaati va admin javobi uchun umumiy) ----------
def _ack_text(items: list[dict], mode: str) -> str:
    n, left = len(items), MAX_ITEMS - len(items)
    what = "Murojaatingizda" if mode == "student" else "Javobingizda"
    target = "bo'limga" if mode == "student" else "talabaga"
    name = "Murojaat" if mode == "student" else "Javob"
    more = (
        f"[[add]] Yana matn, rasm, video, ovozli xabar yoki fayl qo'shishingiz mumkin (yana <b>{left} ta</b>)."
        if left > 0 else
        f"[[stop]] Limit to'ldi ({MAX_ITEMS} ta). Endi faqat yuborishingiz yoki oxirgisini o'chirishingiz mumkin."
    )
    return R(
        f"[[clip]] <b>Qo'shildi!</b> {what} hozir <b>{n} ta</b> xabar bor:\n"
        f"<blockquote>{items_summary(items)}</blockquote>\n"
        f"[[warn]] <b>{name} hali YUBORILMADI!</b> U faqat <b>«Yuborish»</b> tugmasini bosganingizdan "
        f"keyin {target} yetib boradi.\n\n"
        f"{more}\n"
        "[[eye]] <b>Ko'rib chiqish</b> — qo'shganlaringizni qayta ko'rish\n"
        "[[undo]] <b>Oxirgisini o'chirish</b> — oxirgi qo'shilgan xabarni olib tashlash\n"
        "[[send]] Hammasi tayyor bo'lsa — <b>«Yuborish»</b> tugmasini bosing."
    )


async def _show_ack(bot: Bot, chat_id: int, state: FSMContext, items: list[dict], mode: str):
    """Eski holat xabarini o'chirib, yangisini eng pastda ko'rsatadi (doim bitta bo'ladi)."""
    from bot.keyboards import collect_actions_kb

    data = await state.get_data()
    if data.get("ack_id"):
        try:
            await bot.delete_message(chat_id, data["ack_id"])
        except TelegramAPIError:
            pass
    if not items:
        await state.update_data(ack_id=None)
        return
    msg = await bot.send_message(chat_id, _ack_text(items, mode), reply_markup=collect_actions_kb(len(items)))
    await state.update_data(ack_id=msg.message_id)


async def collect(message: Message, state: FSMContext, bot: Bot, mode: str):
    item = extract_content(message)
    if item is None:
        await message.answer(R(
            "[[warn]] Bu turdagi xabar qabul qilinmaydi.\n"
            "<blockquote>Matn, rasm, video, fayl, audio, ovozli xabar, GIF yoki stiker yuboring.</blockquote>"
        ))
        return
    async with _locks[message.from_user.id]:
        data = await state.get_data()
        items = data.get("items", [])
        if len(items) >= MAX_ITEMS:
            await message.answer(R(
                f"[[stop]] Ko'pi bilan <b>{MAX_ITEMS} ta</b> xabar qo'shish mumkin — bu xabar qo'shilmadi.\n"
                "<b>«Yuborish»</b> tugmasini bosing yoki oxirgisini o'chiring."
            ))
            return
        items.append(item)
        await state.update_data(items=items)
        await _show_ack(bot, message.chat.id, state, items, mode)


async def undo_last(bot: Bot, chat_id: int, user_id: int, state: FSMContext, mode: str) -> dict | None:
    async with _locks[user_id]:
        data = await state.get_data()
        items = data.get("items", [])
        if not items:
            return None
        removed = items.pop()
        await state.update_data(items=items)
        await _show_ack(bot, chat_id, state, items, mode)
        return removed


async def preview(bot: Bot, chat_id: int, state: FSMContext, mode: str):
    items = (await state.get_data()).get("items", [])
    await bot.send_message(chat_id, R(f"[[eye]] <b>Siz qo'shgan xabarlar ({len(items)} ta):</b>"))
    for it in items:
        await send_content(bot, chat_id, it)
    await _show_ack(bot, chat_id, state, items, mode)


async def drop_ack(bot: Bot, chat_id: int, state: FSMContext):
    ack = (await state.get_data()).get("ack_id")
    if ack:
        try:
            await bot.delete_message(chat_id, ack)
        except TelegramAPIError:
            pass


# ---------- Murojaatni ko'rsatish / yetkazish ----------
def is_open_identity(appeal: dict) -> bool:
    """Murojaatchi shaxsi ko'rsatiladimi: faqat murojaat anonim EMAS rejimda yuborilgan bo'lsa."""
    return appeal.get("anonymous", 1) == 0


def author_lines(appeal: dict) -> list[str]:
    if not is_open_identity(appeal):
        return [f"{e('lock')} Murojaatchi: <i>anonim</i>"]
    uid = appeal["user_id"]
    name = esc(appeal.get("author_name") or "Foydalanuvchi")
    lines = [f'{e("user")} Murojaatchi: <a href="tg://user?id={uid}">{name}</a>']
    if appeal.get("author_username"):
        lines.append(f"{e('link')} Username: @{esc(appeal['author_username'])}")
    lines.append(f"{e('id')} Telegram ID: <code>{uid}</code>")
    return lines


def contact_url(appeal: dict, allow_id_link: bool = True) -> str | None:
    """«Murojaatchi bilan bog'lanish» tugmasi havolasi (faqat anonim bo'lmagan murojaatda)."""
    if not is_open_identity(appeal):
        return None
    if appeal.get("author_username"):
        return f"https://t.me/{appeal['author_username']}"
    return f"tg://user?id={appeal['user_id']}" if allow_id_link else None


def _privacy_error(ex: Exception) -> bool:
    # foydalanuvchi maxfiylik sozlamasi tg://user?id havolasini taqiqlagan bo'lsa
    return "BUTTON_USER_PRIVACY_RESTRICTED" in str(ex) or "USER_PRIVACY" in str(ex)


def appeal_header(appeal: dict) -> str:
    where = appeal.get("bot_title") or "O'chirilgan bot"
    lines = [
        f"{e('robot')} Bo'lim: <b>{esc(where)}</b>",
        *([f"{e('category')} Mavzu: <b>{esc(appeal['category_title'])}</b>"] if appeal.get("category_title") else []),
        f"{e('clock')} Vaqt: {tg_time(appeal['created_at'])}",
        f"Holati: <b>{status_label(appeal['status'])}</b>",
        *author_lines(appeal),
    ]
    if appeal["status"] != "new" and appeal.get("admin_name"):
        lines.append(f"{e('user')} Mas'ul: {esc(appeal['admin_name'])}")
    if appeal["status"] == "rejected" and appeal.get("reject_reason"):
        lines.append(f"{e('st_rejected')} Sabab: <i>{esc(appeal['reject_reason'])}</i>")
    return f"{e('envelope')} <b>Murojaat #{appeal['id']}</b>\n<blockquote>" + "\n".join(lines) + "</blockquote>"


NEXT_STEP = {
    "new": "[[tip]] <b>Keyingi qadam:</b> murojaatni qabul qiling yoki rad eting.",
    "in_progress": "[[tip]] <b>Keyingi qadam:</b> javob yozing. Javob yuborilgach, murojaat «Ochiq murojaatlar»dan chiqadi.",
    "answered": "[[tip]] Masala to'liq hal bo'lgan bo'lsa — murojaatni yoping.",
}


def card_text(appeal: dict, types: list[str]) -> str:
    """Murojaat kartasi matni (boshqaruv tugmalari shu xabarda bo'ladi)."""
    summary = items_summary([{"type": t} for t in types]) or "—"
    text = f"{appeal_header(appeal)}\n<b>Tarkibi (yuqorida):</b>\n{summary}"
    step = NEXT_STEP.get(appeal["status"])
    return text + ("\n\n" + R(step) if step else "")


async def send_appeal(bot: Bot, chat_id: int, db: Database, appeal: dict, history=False):
    """Murojaatni chat_id ga yuboradi (anonim bo'lsa — muallifsiz): kontent + oxirida boshqaruv kartasi.
    Karta ro'yxatga olinadi — holat o'zgarsa, barcha adminlardagi kartalar avtomatik yangilanadi.
    Faqat murojaat kelgan botning o'zida ishlaydi (file_id lar botga bog'liq)."""
    from bot.keyboards import appeal_actions_kb

    msgs = await db.appeal_messages(appeal["id"])
    student_msgs = [m for m in msgs if m["sender"] == "student"]
    for m in student_msgs:
        await send_content(bot, chat_id, {"type": m["content_type"], "file_id": m["file_id"], "text": m["text"]})
    if history:
        answers = [m for m in msgs if m["sender"] == "admin"]
        if answers:
            await bot.send_message(chat_id, f"{e('history')} <b>Berilgan javoblar ({len(answers)} ta):</b>")
            for m in answers:
                await send_content(bot, chat_id, {"type": m["content_type"], "file_id": m["file_id"], "text": m["text"]})
    text = card_text(appeal, [m["content_type"] for m in student_msgs])
    is_super = chat_id in config.superadmin_ids
    try:
        card = await bot.send_message(chat_id, text, reply_markup=appeal_actions_kb(
            appeal["id"], appeal["status"], is_super, contact_url(appeal)))
    except TelegramBadRequest as ex:
        if not _privacy_error(ex):
            raise
        card = await bot.send_message(chat_id, text, reply_markup=appeal_actions_kb(
            appeal["id"], appeal["status"], is_super, contact_url(appeal, allow_id_link=False)))
    await db.add_card(appeal["id"], chat_id, card.message_id)
    return card


async def refresh_cards(bot: Bot, db: Database, appeal_id: int):
    """Holat o'zgargach, shu murojaatning barcha adminlardagi kartalarini bir vaqtda yangilaydi."""
    from bot.keyboards import appeal_actions_kb

    appeal = await db.get_appeal(appeal_id)
    if not appeal:
        return
    types = [m["content_type"] for m in await db.appeal_messages(appeal_id) if m["sender"] == "student"]
    text = card_text(appeal, types)

    async def _edit(card, allow_id_link=True):
        await bot.edit_message_text(
            text=text, chat_id=card["chat_id"], message_id=card["message_id"],
            reply_markup=appeal_actions_kb(appeal_id, appeal["status"], card["chat_id"] in config.superadmin_ids,
                                           contact_url(appeal, allow_id_link)),
        )

    async def _one(card):
        try:
            try:
                await _edit(card)
            except TelegramBadRequest as ex:
                if not _privacy_error(ex):
                    raise
                await _edit(card, allow_id_link=False)
        except TelegramBadRequest as ex:
            if "not modified" not in str(ex):
                await db.delete_card(appeal_id, card["chat_id"], card["message_id"])
        except TelegramAPIError:
            await db.delete_card(appeal_id, card["chat_id"], card["message_id"])

    await asyncio.gather(*(_one(c) for c in await db.cards(appeal_id)))


_BQ = re.compile(r"</?blockquote[^>]*>")


def _text_line(m: dict) -> str:
    t = m["content_type"]
    body = _BQ.sub("", m.get("text") or "")  # ichma-ich blockquote Telegram'da taqiqlangan
    if t == "text":
        return body
    caption = f": {body}" if body else ""
    return f"{e('c_' + t)} <i>[{CONTENT_NAMES.get(t, t)}]</i>{caption}"


async def appeal_text_view(db: Database, appeal: dict) -> str:
    """Asosiy bot uchun matnli ko'rinish (media boshqa botga tegishli — faqat belgisi ko'rsatiladi)."""
    msgs = await db.appeal_messages(appeal["id"])
    student = "\n\n".join(_text_line(m) for m in msgs if m["sender"] == "student") or "—"
    answers = [_text_line(m) for m in msgs if m["sender"] == "admin"]
    text = f"{appeal_header(appeal)}\n<b>Murojaat matni:</b>\n<blockquote expandable>{student}</blockquote>"
    if answers:
        text += f"\n{e('history')} <b>Javoblar:</b>\n<blockquote expandable>" + "\n\n".join(answers) + "</blockquote>"
    if len(text) > 4000:
        text = f"{appeal_header(appeal)}\n<i>Murojaat juda uzun — to'liq holini bo'lim botida oching.</i>"
    return text


async def deliver_new_appeal(bot: Bot, db: Database, manager, appeal_id: int) -> int:
    """Yangi murojaatni shu bo'lim botining faol adminlariga yuboradi.
    Hech kimga yetmasa — superadminlarga asosiy bot orqali xabar beradi."""
    appeal = await db.get_appeal(appeal_id)

    async def _one(uid: int) -> bool:
        try:
            await bot.send_message(uid, R("[[bell]] <b>Yangi anonim murojaat keldi!</b>" if not is_open_identity(appeal)
                                          else "[[bell]] <b>Yangi murojaat keldi!</b>"))
            await send_appeal(bot, uid, db, appeal)
            return True
        except TelegramAPIError as ex:
            log.warning("Adminga (%s) yuborib bo'lmadi: %s", uid, ex)
            return False

    # barcha adminlarga parallel — tez yetib boradi
    sent = sum(await asyncio.gather(*(_one(uid) for uid in await db.recipients(appeal["bot_id"]))))
    if sent == 0:
        await manager.notify_superadmins(
            R(
                f"[[bell]] <b>Murojaat #{appeal_id}</b> — «{esc(appeal['bot_title'])}» boti\n"
                "<blockquote>[[warn]] Bu botda murojaatni qabul qiladigan faol admin yo'q "
                "(yoki adminlar botni hali ochmagan). Botni ochib, o'zingiz javob berishingiz mumkin.</blockquote>"
            ),
            manager.open_kb(appeal["bot_username"], "Murojaatni ochish", f"ap_{appeal_id}"),
        )
    return sent


async def can_access_appeal(db: Database, user_id: int, appeal: dict, bot_id: int) -> bool:
    """Murojaat faqat o'zi kelgan botda ochiladi; u yerda superadmin yoki shu botning faol admini ko'radi."""
    if appeal["bot_id"] != bot_id:
        return False
    if user_id in config.superadmin_ids:
        return True
    return await db.is_active_admin(bot_id, user_id)
