"""Emoji reyestri (oddiy + premium), rangli tugmalar va matn yordamchilari.

Botdagi har bir emoji shu yerda kalit bilan ro'yxatga olingan. Superadmin har biriga
premium (custom) emoji biriktirishi mumkin — shunda matnlarda <tg-emoji>, tugmalarda esa
icon_custom_emoji_id ishlatiladi. Biriktirilmagan bo'lsa — oddiy emoji ko'rsatiladi.
"""
import html
import re
from datetime import datetime

from aiogram import F
from aiogram.types import InlineKeyboardButton, KeyboardButton

# kalit -> (oddiy emoji, qayerda ishlatiladi)
EMOJI: dict[str, tuple[str, str]] = {
    # --- umumiy ---
    "wave": ("👋", "Salomlashish"),
    "write": ("✍️", "Murojaat yuborish tugmasi"),
    "list": ("📋", "Mening murojaatlarim"),
    "help": ("❓", "Yordam"),
    "send": ("✅", "Yuborish tugmasi"),
    "cancel": ("❌", "Bekor qilish"),
    "back": ("⬅️", "Orqaga tugmasi"),
    "yes": ("✅", "Ha (tasdiqlash)"),
    "no": ("✖️", "Yo'q"),
    "warn": ("⚠️", "Ogohlantirish"),
    "tip": ("💡", "Maslahat"),
    "lock": ("🔒", "Anonimlik / yopish"),
    "unlock": ("🔓", "Qayta ochish"),
    "stop": ("⛔️", "Ruxsat yo'q / blok"),
    "party": ("🎉", "Tabrik"),
    "rocket": ("🚀", "Nima keyin?"),
    "one": ("1️⃣", "1-qadam"),
    "two": ("2️⃣", "2-qadam"),
    "three": ("3️⃣", "3-qadam"),
    "four": ("4️⃣", "4-qadam"),
    # --- murojaat ---
    "folder": ("📂", "Bo'lim"),
    "envelope": ("📩", "Murojaat sarlavhasi"),
    "bell": ("🔔", "Yangi murojaat bildirishnomasi"),
    "mail": ("📨", "Javob keldi"),
    "clock": ("🕒", "Vaqt"),
    "number": ("🔢", "Murojaat raqami"),
    "clip": ("📎", "Xabar qo'shildi"),
    "add": ("➕", "Qo'shish"),
    "eye": ("👁", "Ko'rib chiqish"),
    "undo": ("↩️", "Oxirgisini olib tashlash"),
    "reply": ("✍️", "Javob yozish tugmasi"),
    "history": ("📜", "Tarix"),
    "inbox": ("📥", "Ochiq murojaatlar"),
    # --- holatlar ---
    "st_new": ("🆕", "Holat: yangi"),
    "st_progress": ("⏳", "Holat: qabul qilingan"),
    "st_answered": ("✅", "Holat: javob berilgan"),
    "st_closed": ("🔒", "Holat: yopilgan"),
    "st_rejected": ("🚫", "Holat: rad etilgan"),
    "accept": ("✅", "Qabul qilish tugmasi"),
    "reject": ("❌", "Rad etish tugmasi"),
    # --- kontent turlari ---
    "c_text": ("📝", "Matn"),
    "c_photo": ("🖼", "Rasm"),
    "c_video": ("🎬", "Video"),
    "c_document": ("📄", "Fayl / hujjat"),
    "c_audio": ("🎵", "Audio"),
    "c_voice": ("🎤", "Ovozli xabar"),
    "c_video_note": ("⏺", "Video xabar (dumaloq)"),
    "c_animation": ("🎞", "GIF"),
    "c_sticker": ("🌟", "Stiker"),
    # --- admin / superadmin ---
    "panel": ("🛠", "Admin panel"),
    "stats": ("📊", "Statistika"),
    "admins": ("👮", "Adminlar"),
    "user": ("👤", "Foydalanuvchi"),
    "users": ("👥", "Foydalanuvchilar"),
    "id": ("🆔", "ID"),
    "link": ("🔗", "Username"),
    "calendar": ("📅", "Sana"),
    "trophy": ("🏆", "Reyting"),
    "active": ("🟢", "Faol"),
    "inactive": ("🔴", "Nofaol"),
    "globe": ("🌐", "Barcha bo'limlar"),
    "trash": ("🗑", "O'chirish"),
    "edit": ("✏️", "Tahrirlash"),
    "search": ("🔎", "Qidirish"),
    "block": ("🚫", "Bloklash"),
    "broadcast": ("📢", "Xabar yuborish (e'lon)"),
    "prev": ("◀️", "Oldingi sahifa"),
    "next": ("▶️", "Keyingi sahifa"),
    "sparkles": ("✨", "Premium emojilar"),
    "bolt": ("⚡️", "Ketma-ket sozlash"),
    "skip": ("⏭", "O'tkazib yuborish"),
    "reset": ("🔄", "Asl holiga qaytarish"),
    "star": ("⭐️", "Premium belgisi"),
    # --- ko'p botli tuzilma ---
    "robot": ("🤖", "Bo'lim botlari"),
    "key": ("🔑", "Token"),
    "open": ("↗️", "Botni ochish havolasi"),
    "invite": ("💌", "Taklif havolasi"),
    "report": ("📑", "Excel hisobot"),
    "excel": ("📊", "Hisobot fayli"),
    # --- kategoriyalar ---
    "category": ("🗂", "Kategoriya"),
    "info": ("ℹ️", "Kategoriya izohi"),
    "up": ("⬆️", "Yuqoriga surish"),
    "down": ("⬇️", "Pastga surish"),
}

CONTENT_NAMES = {
    "text": "Matn", "photo": "Rasm", "video": "Video", "document": "Fayl",
    "audio": "Audio", "voice": "Ovozli xabar", "video_note": "Video xabar",
    "animation": "GIF", "sticker": "Stiker",
}

# kalit -> (custom_emoji_id, alt)
_custom: dict[str, tuple[str, str]] = {}
_enabled = True


async def load(db) -> None:
    global _enabled
    _custom.clear()
    _custom.update({k: v for k, v in (await db.custom_emojis()).items() if k in EMOJI})
    _enabled = (await db.get_setting("premium_enabled", "1")) == "1"


def set_local(key: str, emoji_id: str | None, alt: str | None = None):
    if emoji_id:
        _custom[key] = (emoji_id, alt or EMOJI[key][0])
    else:
        _custom.pop(key, None)


def set_enabled(value: bool):
    global _enabled
    _enabled = value


def is_enabled() -> bool:
    return _enabled


def custom_of(key: str) -> tuple[str, str] | None:
    return _custom.get(key)


def custom_count() -> int:
    return len(_custom)


def plain(key: str) -> str:
    return EMOJI[key][0]


def e(key: str) -> str:
    """HTML matn uchun emoji: premium bo'lsa <tg-emoji>, aks holda oddiy."""
    char = EMOJI[key][0]
    c = _custom.get(key) if _enabled else None
    if c:
        return f'<tg-emoji emoji-id="{c[0]}">{html.escape(c[1])}</tg-emoji>'
    return char


def premium_preview(key: str) -> str:
    """Faqat premium ko'rinish (o'chirilgan bo'lsa ham) — panelda ko'rsatish uchun."""
    c = _custom.get(key)
    return f'<tg-emoji emoji-id="{c[0]}">{html.escape(c[1])}</tg-emoji>' if c else "—"


_MARK = re.compile(r"\[\[(\w+)\]\]")


def R(text: str) -> str:
    """Matndagi [[kalit]] belgilarini emoji bilan almashtiradi."""
    return _MARK.sub(lambda m: e(m.group(1)) if m.group(1) in EMOJI else m.group(0), text)


def _icon(key: str | None) -> str | None:
    if key and _enabled and key in _custom:
        return _custom[key][0]
    return None


def ibtn(key: str | None, text: str, cb: str | None = None, style: str | None = None, **kw) -> InlineKeyboardButton:
    """Inline tugma: premium bo'lsa ikonka sifatida, aks holda matn boshida oddiy emoji."""
    icon = _icon(key)
    label = text if (icon or not key) else f"{EMOJI[key][0]} {text}"
    return InlineKeyboardButton(text=label, callback_data=cb, style=style, icon_custom_emoji_id=icon, **kw)


def rbtn(spec: tuple[str, str], style: str | None = None, **kw) -> KeyboardButton:
    key, text = spec
    icon = _icon(key)
    label = text if icon else f"{EMOJI[key][0]} {text}"
    return KeyboardButton(text=label, style=style, icon_custom_emoji_id=icon, **kw)


def match(spec: tuple[str, str]):
    """Reply tugma matnini (premium/oddiy ikkala ko'rinishda) tutuvchi filtr."""
    key, text = spec
    return F.text.in_({text, f"{EMOJI[key][0]} {text}"})


def status_label(status: str) -> str:
    from bot.db import STATUSES
    key, name = STATUSES.get(status, ("st_new", status))
    return f"{e(key)} {name}"


def tg_time(value: str) -> str:
    """'YYYY-MM-DD HH:MM:SS' -> foydalanuvchi vaqt mintaqasida ko'rinadigan <tg-time>."""
    try:
        ts = int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").timestamp())
    except (ValueError, TypeError):
        return html.escape(str(value))
    return f'<tg-time unix="{ts}">{html.escape(value[:16])}</tg-time>'
