"""Talabaga ko'rsatiladigan uzun matnlar. [[kalit]] — emoji (premium bo'lishi mumkin)."""
import html
import re

from bot.ui import R
from bot.utils import MAX_ITEMS


def privacy_note(anonymous: bool) -> str:
    """Talabaga shaxsi ko'rinadimi-yo'qmi — aniq va ochiq aytiladi."""
    if anonymous:
        return ("<blockquote>[[lock]] <b>Anonimlik kafolatlanadi.</b>\n"
                "Ismingiz, username va Telegram ID'ingiz murojaatni ko'radigan hech kimga ko'rsatilmaydi.</blockquote>")
    return ("<blockquote>[[user]] <b>Bu botda murojaatlar anonim emas.</b>\n"
            "Murojaatingiz bilan birga ismingiz, username va Telegram ID'ingiz bo'lim xodimlariga ko'rinadi — "
            "ular siz bilan bevosita bog'lanishi mumkin.</blockquote>")


def student_welcome(title: str, anonymous: bool = True) -> str:
    kind = "<b>anonim</b> murojaat" if anonymous else "murojaat"
    return R(
        "[[wave]] <b>Assalomu alaykum!</b>\n\n"
        f"Bu — <b>{html.escape(title)}</b> boti. Bu yerda shu bo'limga {kind} — "
        "shikoyat, taklif yoki savol yuborishingiz mumkin.\n\n"
        + privacy_note(anonymous) + "\n\n"
        "[[write]] <b>«Murojaat yuborish»</b> — yangi murojaat yozish\n"
        "[[list]] <b>«Mening murojaatlarim»</b> — yuborganlaringiz holati\n"
        "[[help]] <b>«Qanday ishlaydi?»</b> — batafsil yo'riqnoma"
    )


def student_help(anonymous: bool = True) -> str:
    how = "anonim tarzda boradi" if anonymous else "ismingiz va Telegram profilingiz bilan boradi"
    name_tip = ("Ismingizni yozish shart emas." if anonymous
                else "Ismingiz avtomatik ko'rinadi, uni qayta yozish shart emas.")
    return R(
        "[[help]] <b>Bot qanday ishlaydi?</b>\n\n"
        "<blockquote>[[one]] <b>«Murojaat yuborish»</b> tugmasini bosing.\n"
        "[[two]] Murojaatingizni yozing. Matn, rasm, video, ovozli xabar, fayl — istalganini, "
        f"bir nechtasini birga ham yuborishingiz mumkin (ko'pi bilan {MAX_ITEMS} ta).\n"
        "[[three]] Hammasi tayyor bo'lgach <b>«Yuborish»</b> tugmasini bosing.</blockquote>\n\n"
        "[[warn]] <b>«Yuborish»</b> tugmasini bosmaguningizcha murojaat hech kimga bormaydi — "
        "shu paytgacha xabar qo'shishingiz, ko'rib chiqishingiz yoki o'chirishingiz mumkin.\n\n"
        "<blockquote expandable>[[rocket]] <b>Yuborilgandan keyin nima bo'ladi?</b>\n"
        "• Murojaatingiz raqam oladi (masalan, #15).\n"
        f"• U tegishli bo'lim xodimlariga {how}.\n"
        "• Xodim murojaatni <b>qabul qilganda</b>, <b>javob berganda</b> va <b>yopganda</b> shu botga xabar keladi.\n"
        "• Javob matn, rasm, video yoki hujjat ko'rinishida kelishi mumkin.\n"
        "• Murojaat bo'limga tegishli bo'lmasa, sababi bilan rad etilishi mumkin.\n"
        "• Holatini istalgan vaqtda «Mening murojaatlarim» bo'limida ko'rasiz.\n\n"
        "[[st_new]] Yangi — hali ko'rilmagan\n"
        "[[st_progress]] Qabul qilingan — xodim ko'rib chiqmoqda, javob tayyorlanmoqda\n"
        "[[st_answered]] Javob berilgan — javob sizga yuborilgan\n"
        "[[st_closed]] Yopilgan — murojaat yakunlangan\n"
        "[[st_rejected]] Rad etilgan — sababi sizga yuborilgan</blockquote>\n\n"
        "<blockquote expandable>[[tip]] <b>Yaxshi murojaat yozish bo'yicha maslahatlar</b>\n"
        "• Muammoni aniq yozing: nima bo'ldi, qachon, qayerda.\n"
        "• Fakultet, kurs, guruh, fan nomini ko'rsatsangiz — javob tezroq beriladi. "
        f"{name_tip}\n"
        "• Dalil bo'lsa (rasm, skrinshot, hujjat) — qo'shib yuboring.\n"
        "• Bir murojaatda bitta mavzu bo'lsin.</blockquote>"
    )


def category_prompt() -> str:
    return R(
        "[[category]] <b>Murojaat mavzusini tanlang</b>\n\n"
        "<blockquote>Murojaatingiz qaysi masala bo'yicha? Pastdagi ro'yxatdan mosini tanlang — "
        "shunda u tegishli xodimga tezroq yetib boradi.</blockquote>\n"
        "[[tip]] Tanlaganingizdan keyin murojaat matnini yozasiz. Aniq mos mavzu bo'lmasa, eng yaqinini tanlang."
    )


_DESC = "\x00DESC\x00"
_BQ = re.compile(r"</?blockquote[^>]*>")


def category_description(description: str) -> str:
    """Superadmin yozgan izoh (HTML) — talabaga ko'rsatish uchun; ichma-ich blockquote Telegram'da taqiqlangan."""
    return _BQ.sub("", description).strip()


def content_prompt(category: str | None = None, description: str | None = None, anonymous: bool = True) -> str:
    name_tip = "ismingiz shart emas" if anonymous else "ismingiz avtomatik ko'rinadi"
    privacy = ("[[lock]] Murojaat <b>anonim</b> yuboriladi.\n" if anonymous else
               "[[user]] Murojaat <b>anonim emas</b>: ismingiz, username va Telegram ID'ingiz xodimlarga ko'rinadi.\n")
    cat = ""
    if category:
        cat = f"[[category]] Mavzu: <b>{html.escape(category)}</b>\n"
        cat += f"<blockquote>[[info]] {_DESC}</blockquote>\n\n" if description else "\n"
    text = R(
        "[[write]] <b>Murojaatingizni yozing</b>\n\n" + cat +
        "<blockquote><b>Qanday yuboriladi?</b>\n"
        "[[one]] Muammo, taklif yoki savolingizni <b>matn</b> qilib yozing.\n"
        "[[two]] Kerak bo'lsa <b>rasm, video, ovozli xabar yoki fayl</b> qo'shing. "
        "Bir nechtasini birin-ketin yoki albom qilib yuborsangiz ham bo'ladi.\n"
        "[[three]] Hammasi tayyor bo'lgach, pastdagi <b>«Yuborish»</b> tugmasini bosing.</blockquote>\n\n"
        "[[warn]] <b>Muhim:</b> «Yuborish» tugmasini bosmaguningizcha murojaat <b>hech kimga bormaydi</b>. "
        f"Shu paytgacha istalgancha xabar qo'shishingiz mumkin (ko'pi bilan <b>{MAX_ITEMS} ta</b>). "
        "Har bir xabardan keyin nimalar qo'shilganini ko'rsatib turaman — ularni qayta ko'rishingiz "
        "yoki oxirgisini o'chirishingiz mumkin.\n\n"
        "<blockquote expandable>[[tip]] <b>Maslahatlar</b>\n"
        "• Muammoni aniq yozing: nima, qachon, qayerda.\n"
        f"• Kurs, guruh, fan nomini ko'rsatsangiz, javob tezroq beriladi — {name_tip}.\n"
        "• Rasm yoki videoga izoh (caption) yozsangiz ham saqlanadi.</blockquote>\n\n"
        + privacy +
        "[[cancel]] Fikringizdan qaytsangiz — <b>«Bekor qilish»</b>."
    )
    # izoh R() dan keyin qo'yiladi: superadmin matnidagi belgilar emoji-kalit deb talqin qilinmasin
    return text.replace(_DESC, category_description(description)) if description else text


def appeal_sent(appeal_id: int, category: str | None = None, anonymous: bool = True) -> str:
    how = "anonim tarzda yetkazildi" if anonymous else "yetkazildi"
    last = ("[[lock]] Shaxsingiz hech kimga ko'rsatilmadi." if anonymous else
            "[[user]] Ismingiz va Telegram profilingiz xodimlarga ko'rinadi — ular siz bilan bog'lanishi mumkin.")
    cat = f"[[category]] Mavzu: <b>{html.escape(category)}</b>\n" if category else ""
    return R(
        "[[party]] <b>Murojaatingiz yuborildi!</b>\n\n"
        f"[[number]] Raqami: <b>#{appeal_id}</b>\n{cat}\n"
        "<blockquote>[[rocket]] <b>Endi nima bo'ladi?</b>\n"
        f"• Murojaat tegishli xodimlarga {how}.\n"
        "• Xodim uni qabul qilganda va javob berganda shu botga xabar keladi.\n"
        "• Holatini «Mening murojaatlarim» bo'limida kuzatishingiz mumkin.</blockquote>\n\n"
        + last
    )


def main_welcome() -> str:
    """Asosiy bot oddiy foydalanuvchilar uchun — faqat qisqa ma'lumot."""
    return R(
        "[[wave]] <b>Assalomu alaykum!</b>\n\n"
        "<blockquote>[[robot]] Bu — <b>Murojaat-bot</b> tizimining <b>boshqaruv boti</b>. "
        "U faqat tizim ma'murlari uchun mo'ljallangan.</blockquote>\n\n"
        "[[envelope]] Murojaatlar tegishli bo'limlarning alohida botlari orqali qabul qilinadi."
    )
