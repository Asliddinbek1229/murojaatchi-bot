"""Talabaga ko'rsatiladigan uzun matnlar. [[kalit]] — emoji (premium bo'lishi mumkin)."""
import html

from bot.ui import R
from bot.utils import MAX_ITEMS


def student_welcome(title: str) -> str:
    return R(
        "[[wave]] <b>Assalomu alaykum!</b>\n\n"
        f"Bu — <b>{html.escape(title)}</b> boti. Bu yerda shu bo'limga <b>anonim</b> murojaat — "
        "shikoyat, taklif yoki savol yuborishingiz mumkin.\n\n"
        "<blockquote>[[lock]] <b>Anonimlik kafolatlanadi.</b>\n"
        "Ismingiz, username va Telegram ID'ingiz murojaatni ko'radigan hech kimga ko'rsatilmaydi.</blockquote>\n\n"
        "[[write]] <b>«Murojaat yuborish»</b> — yangi murojaat yozish\n"
        "[[list]] <b>«Mening murojaatlarim»</b> — yuborganlaringiz holati\n"
        "[[help]] <b>«Qanday ishlaydi?»</b> — batafsil yo'riqnoma"
    )


def student_help() -> str:
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
        "• U tegishli bo'lim xodimlariga anonim tarzda boradi.\n"
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
        "Ismingizni yozish shart emas.\n"
        "• Dalil bo'lsa (rasm, skrinshot, hujjat) — qo'shib yuboring.\n"
        "• Bir murojaatda bitta mavzu bo'lsin.</blockquote>"
    )


def content_prompt() -> str:
    return R(
        "[[write]] <b>Murojaatingizni yozing</b>\n\n"
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
        "• Kurs, guruh, fan nomini ko'rsatsangiz, javob tezroq beriladi — ismingiz shart emas.\n"
        "• Rasm yoki videoga izoh (caption) yozsangiz ham saqlanadi.</blockquote>\n\n"
        "[[lock]] Murojaat <b>anonim</b> yuboriladi.\n"
        "[[cancel]] Fikringizdan qaytsangiz — <b>«Bekor qilish»</b>."
    )


def appeal_sent(appeal_id: int) -> str:
    return R(
        "[[party]] <b>Murojaatingiz yuborildi!</b>\n\n"
        f"[[number]] Raqami: <b>#{appeal_id}</b>\n\n"
        "<blockquote>[[rocket]] <b>Endi nima bo'ladi?</b>\n"
        "• Murojaat tegishli xodimlarga anonim tarzda yetkazildi.\n"
        "• Xodim uni qabul qilganda va javob berganda shu botga xabar keladi.\n"
        "• Holatini «Mening murojaatlarim» bo'limida kuzatishingiz mumkin.</blockquote>\n\n"
        "[[lock]] Shaxsingiz hech kimga ko'rsatilmadi."
    )


def main_welcome() -> str:
    """Asosiy bot oddiy foydalanuvchilar uchun — faqat qisqa ma'lumot."""
    return R(
        "[[wave]] <b>Assalomu alaykum!</b>\n\n"
        "<blockquote>[[robot]] Bu — talabalar murojaatlari tizimining <b>boshqaruv boti</b>. "
        "U faqat tizim ma'murlari uchun mo'ljallangan.</blockquote>\n\n"
        "[[lock]] Murojaatlar tegishli bo'limlarning alohida botlari orqali <b>anonim</b> tarzda qabul qilinadi."
    )
