"""Murojaat kategoriyalarini boshqarish (asosiy bot, superadmin).

Bo'lim botida faol kategoriyalar bo'lsa, talaba «Murojaat yuborish»ni bosganda avval kategoriyani tanlaydi.
Kategoriya bo'lmasa — bot avvalgidek kategoriyasiz ishlaydi.
"""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db import Database
from bot.filters import IsMainBot, IsSuperAdmin
from bot.keyboards import back_kb, cancel_kb, categories_kb, category_card_kb, confirm_kb, super_menu
from bot.states import CategorySG
from bot.texts import category_description, content_prompt
from bot.ui import R
from bot.utils import esc

router = Router(name="categories")
router.message.filter(IsMainBot(), IsSuperAdmin())
router.callback_query.filter(IsMainBot(), IsSuperAdmin())

MAX_TITLE = 48
MAX_CATS = 30
MAX_DESC = 1000


def _list_text(bot: dict, cats: list[dict]) -> str:
    if cats:
        state = (
            "[[active]] talabalarga ko'rinadi · [[inactive]] yashirilgan\n"
            "Raqam — shu kategoriyadagi murojaatlar soni."
        )
        mode = "[[tip]] Talaba «Murojaat yuborish»ni bosganda avval shu kategoriyalardan birini tanlaydi."
    else:
        state = "Hozircha kategoriya yo'q."
        mode = ("[[tip]] Kategoriya bo'lmasa, talaba murojaatni darhol yozadi (hozirgi holat). "
                "Kategoriya qo'shsangiz, murojaatdan oldin uni tanlash so'raladi va hisobotlarda "
                "kategoriyalar bo'yicha statistika paydo bo'ladi.")
    return R(
        f"[[category]] <b>Murojaat kategoriyalari</b> — {esc(bot['title'])}\n\n"
        f"<blockquote>{state}</blockquote>\n{mode}"
    )


async def _list_view(message: Message, db: Database, bid: int, edit=True):
    bot = await db.get_bot(bid)
    if not bot:
        return await message.edit_text(R("[[stop]] Bot topilmadi."), reply_markup=back_kb("sa:bots"))
    cats = await db.categories(bid)
    kw = dict(text=_list_text(bot, cats), reply_markup=categories_kb(bid, cats))
    await (message.edit_text(**kw) if edit else message.answer(**kw))


async def _card_view(message: Message, db: Database, cid: int, edit=True):
    cat = await db.get_category(cid)
    if not cat:
        return await message.edit_text(R("[[stop]] Kategoriya topilmadi."), reply_markup=back_kb("sa:bots"))
    cats = await db.categories(cat["bot_id"])
    ids = [c["id"] for c in cats]
    state = R("[[active]] Talabalarga ko'rinadi") if cat["is_active"] else R("[[inactive]] Yashirilgan")
    text = R(
        f"[[category]] <b>{esc(cat['title'])}</b>\n\n"
        f"<blockquote>Holati: {state}\n"
        f"Tartib raqami: <b>{ids.index(cid) + 1}</b> / {len(ids)}\n"
        f"[[envelope]] Murojaatlar: <b>{cat['appeals']}</b> (ochiq: {cat['open_appeals']})</blockquote>\n"
    )
    if cat.get("description"):
        text += R("[[info]] <b>Izoh</b> (talaba shu kategoriyani tanlaganda ko'radi):\n") + \
            f"<blockquote expandable>{category_description(cat['description'])}</blockquote>"
    else:
        text += R("[[info]] Izoh yo'q. Izoh qo'shsangiz, talaba kategoriyani tanlaganda "
                  "«Murojaatingizni yozing» xabari bilan birga ko'radi (ixtiyoriy).")
    kw = dict(text=text, reply_markup=category_card_kb(cat, ids[0] == cid, ids[-1] == cid))
    await (message.edit_text(**kw) if edit else message.answer(**kw))


@router.callback_query(F.data.startswith("sa:cats:"))
async def cats_list(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    await _list_view(call.message, db, int(call.data.split(":")[2]))
    await call.answer()


@router.callback_query(F.data.startswith("sa:cat:"))
async def cat_card(call: CallbackQuery, db: Database):
    await _card_view(call.message, db, int(call.data.split(":")[2]))
    await call.answer()


# ---- qo'shish ----
@router.callback_query(F.data.startswith("sa:cat_add:"))
async def cat_add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(CategorySG.add)
    await state.update_data(bid=int(call.data.split(":")[2]))
    await call.answer()
    await call.message.answer(
        R(
            "[[add]] <b>Kategoriya qo'shish</b>\n\n"
            "Kategoriya nomini yuboring. Bir nechtasini birdaniga qo'shish uchun "
            "<b>har birini yangi qatorga</b> yozing:\n"
            "<blockquote>Stipendiya\nYotoqxona\nDars jadvali\nBaholash va imtihonlar\nBoshqa</blockquote>\n"
            f"[[tip]] Nom qisqa va tushunarli bo'lsin (ko'pi bilan {MAX_TITLE} belgi) — u talabaga tugma bo'lib ko'rinadi."
        ),
        reply_markup=cancel_kb(),
    )


@router.message(CategorySG.add, F.text)
async def cat_add(message: Message, state: FSMContext, db: Database):
    bid = (await state.get_data())["bid"]
    titles = []
    for line in message.text.splitlines():
        t = " ".join(line.strip(" •-–—\t").split())
        if t and t not in titles:
            titles.append(t)
    too_long = [t for t in titles if len(t) > MAX_TITLE]
    if not titles or too_long:
        return await message.answer(R(
            f"[[warn]] Nom {MAX_TITLE} belgidan oshmasin. Qisqartirib qayta yuboring"
            + (f": <i>{esc(too_long[0])}</i>" if too_long else ".")
        ))
    have = len(await db.categories(bid))
    if have + len(titles) > MAX_CATS:
        return await message.answer(R(f"[[warn]] Bitta botda ko'pi bilan {MAX_CATS} ta kategoriya bo'lishi mumkin (hozir {have} ta)."))
    added = await db.add_categories(bid, titles)
    await state.clear()
    skipped = len(titles) - len(added)
    note = f"\n<i>{skipped} tasi oldindan mavjud — qayta qo'shilmadi.</i>" if skipped else ""
    await message.answer(
        R(f"[[send]] <b>{len(added)}</b> ta kategoriya qo'shildi.{note}"), reply_markup=super_menu()
    )
    await _list_view(message, db, bid, edit=False)


# ---- nomini o'zgartirish ----
@router.callback_query(F.data.startswith("sa:cat_ren:"))
async def cat_rename_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(CategorySG.rename)
    await state.update_data(cid=int(call.data.split(":")[2]))
    await call.answer()
    await call.message.answer(R("[[edit]] Kategoriyaning yangi nomini yuboring:"), reply_markup=cancel_kb())


@router.message(CategorySG.rename, F.text)
async def cat_rename(message: Message, state: FSMContext, db: Database):
    cid = (await state.get_data())["cid"]
    title = " ".join(message.text.split())
    if not title or len(title) > MAX_TITLE:
        return await message.answer(R(f"[[warn]] Nom 1–{MAX_TITLE} belgi bo'lsin. Qayta yuboring:"))
    cat = await db.get_category(cid)
    if not cat:
        await state.clear()
        return await message.answer(R("[[stop]] Kategoriya topilmadi."), reply_markup=super_menu())
    if any(c["title"].casefold() == title.casefold() and c["id"] != cid for c in await db.categories(cat["bot_id"])):
        return await message.answer(R("[[warn]] Bu nomli kategoriya allaqachon bor. Boshqa nom yuboring:"))
    await state.clear()
    await db.rename_category(cid, title)
    await message.answer(R("[[send]] Nomi o'zgartirildi."), reply_markup=super_menu())
    await _card_view(message, db, cid, edit=False)


# ---- izoh ----
@router.callback_query(F.data.startswith("sa:cat_desc:"))
async def cat_desc_start(call: CallbackQuery, state: FSMContext, db: Database):
    cid = int(call.data.split(":")[2])
    cat = await db.get_category(cid)
    if not cat:
        return await call.answer("Kategoriya topilmadi", show_alert=True)
    await state.set_state(CategorySG.description)
    await state.update_data(cid=cid)
    await call.answer()
    await call.message.answer(
        R(
            f"[[info]] <b>«{esc(cat['title'])}» uchun izoh</b>\n\n"
            "Talaba shu kategoriyani tanlagach, «Murojaatingizni yozing» xabarida mavzu ostida ko'radi. "
            "Masalan, nimalarni yozish kerakligi, qanday hujjat ilova qilish yoki qachon javob berilishi.\n"
            "<blockquote>Stipendiya to'lovi, miqdori yoki kechikishi bo'yicha murojaatlar. "
            "Kurs, guruh va qaysi oy uchun ekanini yozing; kerak bo'lsa, bank kartasi ko'chirmasini rasm qilib qo'shing.</blockquote>\n"
            f"[[tip]] Qalin, kursiv, havola va premium emoji ishlaydi. Ko'pi bilan {MAX_DESC} belgi."
        ),
        reply_markup=cancel_kb(),
    )


@router.message(CategorySG.description, F.text)
async def cat_desc_save(message: Message, state: FSMContext, db: Database):
    cid = (await state.get_data())["cid"]
    cat = await db.get_category(cid)
    if not cat:
        await state.clear()
        return await message.answer(R("[[stop]] Kategoriya topilmadi."), reply_markup=super_menu())
    desc = message.html_text.strip()
    if len(message.text) > MAX_DESC or len(desc) > MAX_DESC * 2:
        return await message.answer(R(f"[[warn]] Izoh juda uzun ({len(message.text)} belgi). "
                                      f"Ko'pi bilan {MAX_DESC} belgi — qisqartirib qayta yuboring:"))
    # Telegram qabul qilishini tekshiramiz: talaba ko'radigan xabarni aynan shu ko'rinishda yuboramiz
    try:
        await message.answer(R("[[eye]] <b>Talaba shunday ko'radi:</b>"))
        await message.answer(content_prompt(cat["title"], desc))
    except TelegramBadRequest as ex:
        return await message.answer(R(f"[[warn]] Bu izohni Telegram qabul qilmadi: <code>{esc(ex.message)}</code>\n"
                                      "Boshqacha yozib qayta yuboring:"))
    await state.clear()
    await db.set_category_description(cid, desc)
    await message.answer(R("[[send]] Izoh saqlandi."), reply_markup=super_menu())
    await _card_view(message, db, cid, edit=False)


@router.message(CategorySG.description)
async def cat_desc_not_text(message: Message):
    await message.answer(R("[[warn]] Izoh faqat matn bo'lishi mumkin. Matn yuboring yoki «Bekor qilish»ni bosing."))


@router.callback_query(F.data.startswith("sa:cat_descdel:"))
async def cat_desc_delete(call: CallbackQuery, db: Database):
    cid = int(call.data.split(":")[2])
    await db.set_category_description(cid, None)
    await _card_view(call.message, db, cid)
    await call.answer("Izoh o'chirildi")


# ---- yashirish / tartib / o'chirish ----
@router.callback_query(F.data.startswith("sa:cat_tog:"))
async def cat_toggle(call: CallbackQuery, db: Database):
    cid = int(call.data.split(":")[2])
    await db.toggle_category(cid)
    await _card_view(call.message, db, cid)
    cat = await db.get_category(cid)
    await call.answer("Talabalarga ko'rinadi" if cat and cat["is_active"] else "Yashirildi: talabalar endi tanlay olmaydi")


@router.callback_query(F.data.startswith("sa:cat_mv:"))
async def cat_move(call: CallbackQuery, db: Database):
    _, _, cid, delta = call.data.split(":")
    await db.move_category(int(cid), int(delta))
    await _card_view(call.message, db, int(cid))
    await call.answer()


@router.callback_query(F.data.startswith("sa:cat_del:"))
async def cat_delete_ask(call: CallbackQuery, db: Database):
    cid = int(call.data.split(":")[2])
    cat = await db.get_category(cid)
    if not cat:
        return await call.answer("Kategoriya topilmadi", show_alert=True)
    note = (
        f"Bu kategoriyada <b>{cat['appeals']}</b> ta murojaat bor — ular o'chmaydi, "
        "hisobotlarda ham shu kategoriya nomi bilan qoladi." if cat["appeals"]
        else "Bu kategoriyada murojaatlar yo'q."
    )
    await call.message.edit_text(
        R(f"[[trash]] <b>«{esc(cat['title'])}»</b> kategoriyasini o'chirasizmi?\n<blockquote>{note}</blockquote>"),
        reply_markup=confirm_kb(f"sa:cat_delok:{cid}", f"sa:cat:{cid}"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("sa:cat_delok:"))
async def cat_delete(call: CallbackQuery, db: Database):
    cid = int(call.data.split(":")[2])
    cat = await db.get_category(cid)
    if not cat:
        return await call.answer("Kategoriya topilmadi", show_alert=True)
    await db.delete_category(cid)
    await _list_view(call.message, db, cat["bot_id"])
    await call.answer("O'chirildi")
