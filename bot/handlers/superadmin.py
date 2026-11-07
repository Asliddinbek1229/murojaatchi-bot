"""Asosiy botdagi superadmin paneli: bo'lim botlari, adminlar, murojaatlar, statistika, bloklar, e'lonlar."""
import asyncio
import io
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.db import MAIN_BOT_ID, STATUSES, Database
from bot.filters import IsMainBot, IsSuperAdmin
from bot.keyboards import (
    GREEN,
    RB_CATALOG,
    RB_PANEL,
    admin_card_kb,
    appeal_main_kb,
    appeals_filter_kb,
    appeals_list_kb,
    back_kb,
    blocked_kb,
    bot_admins_kb,
    bot_card_kb,
    bot_choice_kb,
    bots_kb,
    cancel_kb,
    catalog_kb,
    confirm_kb,
    ikb,
    panel_kb,
    pick_user_kb,
    super_menu,
)
from bot.manager import BotManager, TokenError, encrypt
from bot.states import AddAdminSG, BotSG, BroadcastSG, FindAppealSG
from bot.ui import R, custom_count, ibtn, match, status_label
from bot.utils import appeal_text_view, esc, extract_content

log = logging.getLogger(__name__)

router = Router(name="superadmin")
router.message.filter(IsMainBot(), IsSuperAdmin())
router.callback_query.filter(IsMainBot(), IsSuperAdmin())

# Bloklash har qanday botda (asosiy va bo'lim botlarida) superadmin uchun ishlaydi
block_router = Router(name="block")
block_router.message.filter(IsSuperAdmin())
block_router.callback_query.filter(IsSuperAdmin())

PAGE = 10


def _statuses(s: dict) -> str:
    return "\n".join(f"{status_label(k)}: <b>{s[k]}</b>" for k in STATUSES)


def panel_text() -> str:
    return R(
        "[[panel]] <b>Superadmin panel</b>\n\n"
        "<blockquote>[[robot]] <b>Bo'lim botlari</b> — bot qo'shish, adminlar tayinlash\n"
        "[[stats]] <b>Statistika</b> — barcha botlar bo'yicha\n"
        "[[envelope]] <b>Murojaatlar</b> — ko'rish va qidirish\n"
        "[[block]] <b>Bloklanganlar</b> — bloklangan mualliflar\n"
        "[[broadcast]] <b>E'lon</b> — foydalanuvchilarga xabar\n"
        f"[[sparkles]] <b>Premium emojilar</b> — {custom_count()} ta sozlangan</blockquote>\n"
        "<i>Tizim: /status — holat, /backup — baza nusxasi</i>"
    )


# =============== Panel ===============
@router.message(Command("admin"))
@router.message(match(RB_PANEL))
async def panel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(panel_text(), reply_markup=panel_kb())


@router.callback_query(F.data == "sa:panel")
async def panel_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(panel_text(), reply_markup=panel_kb())
    await call.answer()


@router.message(match(RB_CATALOG))
async def catalog(message: Message, db: Database):
    bots = await db.bots(only_active=True)
    if not bots:
        await message.answer(R("[[robot]] Hozircha faol bo'lim botlari yo'q."))
        return
    await message.answer(
        R(f"[[robot]] <b>Bo'lim botlari</b> — {len(bots)} ta\n<blockquote>Botni ochish uchun tanlang.</blockquote>"),
        reply_markup=catalog_kb(bots),
    )


# =============== Statistika ===============
@router.callback_query(F.data == "sa:stats")
async def stats(call: CallbackQuery, db: Database, manager: BotManager):
    s = await db.stats()
    bots = await db.bots()
    by_bot = "\n".join(
        f"{'🟢' if manager.is_running(b['id']) else '🔴'} {esc(b['title'])}: <b>{b['appeals']}</b>"
        f" (ochiq: {b['open_appeals']})"
        for b in bots
    ) or "—"
    top = "\n".join(
        f"{i}. {esc(a['full_name'] or a['user_id'])}: <b>{a['answered']}</b>"
        for i, a in enumerate((await db.all_admins())[:10], 1)
    ) or "—"
    text = R(
        "[[stats]] <b>Umumiy statistika</b>\n\n"
        f"<blockquote>[[users]] Foydalanuvchilar: <b>{s['users']}</b> (bloklangan: {s['blocked']})\n"
        f"[[robot]] Bo'lim botlari: <b>{s['bots']}</b> (faol: {s['active_bots']})\n"
        f"[[admins]] Adminlar: <b>{s['admins']}</b></blockquote>\n"
        f"[[envelope]] <b>Murojaatlar:</b> jami <b>{s['total']}</b>, bugun <b>{s['today']}</b>\n"
        f"<blockquote>{_statuses(s)}</blockquote>\n"
        f"[[robot]] <b>Botlar bo'yicha:</b>\n<blockquote expandable>{by_bot}</blockquote>\n"
        f"[[trophy]] <b>Adminlar reytingi</b> (javob berilgan murojaatlar):\n<blockquote expandable>{top}</blockquote>"
    )
    await call.message.edit_text(text, reply_markup=back_kb())
    await call.answer()


@router.callback_query(F.data.startswith("sa:bot_stats:"))
async def bot_stats(call: CallbackQuery, db: Database):
    bid = int(call.data.split(":")[2])
    b = await db.get_bot(bid)
    if not b:
        return await call.answer("Bot topilmadi", show_alert=True)
    s = await db.stats(bid)
    admins = await db.bot_admins(bid)
    top = "\n".join(f"• {esc(a['full_name'])}: <b>{a['answered']}</b>" for a in admins) or "—"
    cats = await db.category_stats(bid)
    cat_block = ""
    if any(c["title"] for c in cats):
        lines = [
            f"• {esc(c['title'] or 'Kategoriyasiz')}{' (o‘chirilgan)' if c['is_deleted'] else ''}: <b>{c['total']}</b>"
            f" — ochiq {c['open'] or 0}, hal qilingan {c['done'] or 0}, rad {c['rejected'] or 0}"
            for c in cats
        ]
        cat_block = "\n[[category]] <b>Kategoriyalar bo'yicha:</b>\n<blockquote expandable>" + "\n".join(lines) + "</blockquote>"
    await call.message.edit_text(
        R(
            f"[[stats]] <b>{esc(b['title'])}</b> — statistika\n\n"
            f"<blockquote>[[users]] Botni ochganlar: <b>{s['bot_users']}</b>\n"
            f"[[envelope]] Murojaatlar: jami <b>{s['total']}</b>, bugun <b>{s['today']}</b></blockquote>\n"
            f"<blockquote>{_statuses(s)}</blockquote>\n"
            f"[[admins]] <b>Adminlar</b> (javob berilgan):\n<blockquote>{top}</blockquote>"
            + cat_block
        ),
        reply_markup=back_kb(f"sa:bot:{bid}"),
    )
    await call.answer()


# =============== Bo'lim botlari ===============
async def _bots_view(call: CallbackQuery, db: Database, manager: BotManager, edit=True):
    bots = await db.bots()
    running = {b["id"] for b in bots if manager.is_running(b["id"])}
    text = R(
        f"[[robot]] <b>Bo'lim botlari</b> — {len(bots)} ta\n\n"
        "<blockquote>Har bir bo'limning o'z boti bor: talabalar shu botga murojaat yozadi, "
        "shu botning adminlari javob beradi.\n[[active]] ishlayapti · [[inactive]] to'xtagan</blockquote>"
    )
    if edit:
        await call.message.edit_text(text, reply_markup=bots_kb(bots, running))
    else:
        await call.message.answer(text, reply_markup=bots_kb(bots, running))


@router.callback_query(F.data == "sa:bots")
async def bots_list(call: CallbackQuery, state: FSMContext, db: Database, manager: BotManager):
    await state.clear()
    await _bots_view(call, db, manager)
    await call.answer()


def _bot_card_text(b: dict, running: bool, admins: int) -> str:
    state = R("[[active]] Ishlayapti") if running else R("[[inactive]] To'xtatilgan")
    err = f"\n[[warn]] Oxirgi xato: <i>{esc(b['last_error'])}</i>" if b.get("last_error") else ""
    return R(
        f"[[robot]] <b>{esc(b['title'])}</b>\n\n"
        f"<blockquote>[[link]] Bot: @{esc(b['username'])}\n"
        f"Holati: {state}\n"
        f"[[admins]] Adminlar: <b>{admins}</b>\n"
        f"[[category]] Kategoriyalar: <b>{b.get('categories') or 'yo‘q'}</b>\n"
        + ("[[lock]] Murojaatchilar: <b>anonim</b>\n" if b.get("anonymous", 1)
           else "[[user]] Murojaatchilar: <b>anonim emas</b> (ismi, username, ID adminlarga ko'rinadi)\n") +
        f"[[envelope]] Murojaatlar: <b>{b.get('appeals', 0)}</b> (ochiq: {b.get('open_appeals', 0)})\n"
        f"[[calendar]] Qo'shilgan: {b['added_at'][:16]}{err}</blockquote>"
    )


async def _bot_card(message: Message, db: Database, manager: BotManager, bid: int, edit=True):
    b = next((x for x in await db.bots() if x["id"] == bid), None)
    if not b:
        return await message.edit_text(R("[[stop]] Bot topilmadi."), reply_markup=back_kb("sa:bots"))
    running = manager.is_running(bid)
    kw = dict(text=_bot_card_text(b, running, b["admins"]), reply_markup=bot_card_kb(b, running))
    await (message.edit_text(**kw) if edit else message.answer(**kw))


@router.callback_query(F.data.startswith("sa:bot:"))
async def bot_card(call: CallbackQuery, state: FSMContext, db: Database, manager: BotManager):
    await state.clear()
    await _bot_card(call.message, db, manager, int(call.data.split(":")[2]))
    await call.answer()


# ---- Bot qo'shish ----
@router.callback_query(F.data == "sa:bot_add")
async def bot_add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(BotSG.token)
    await call.answer()
    await call.message.answer(
        R(
            "[[add]] <b>Yangi bo'lim boti qo'shish</b>\n\n"
            "<blockquote>[[one]] @BotFather da <code>/newbot</code> orqali yangi bot yarating "
            "(premium emojilar ishlashi uchun — Premium akkauntingizdan).\n"
            "[[two]] BotFather bergan <b>tokenni</b> shu yerga yuboring.\n"
            "[[three]] Bo'lim nomini yozasiz — bot darhol ishga tushadi.</blockquote>\n\n"
            "[[key]] Token shifrlangan holda saqlanadi. Token yuborilgan xabarni o'chirib qo'yaman."
        ),
        reply_markup=cancel_kb(),
    )


async def _delete_quietly(message: Message):
    try:
        await message.delete()
    except TelegramAPIError:
        pass


@router.message(BotSG.token, F.text)
async def bot_add_token(message: Message, state: FSMContext, manager: BotManager):
    token = message.text.strip()
    await _delete_quietly(message)  # token chatda qolmasin
    try:
        me = await manager.check_token(token)
    except TokenError as ex:
        await message.answer(R(f"[[stop]] {esc(ex)}\nBoshqa token yuboring yoki bekor qiling."))
        return
    await state.update_data(token=encrypt(token), tg_id=me.id, username=me.username, name=me.full_name)
    await state.set_state(BotSG.title)
    await message.answer(R(
        f"[[send]] Token to'g'ri: <b>@{esc(me.username)}</b> ({esc(me.full_name)})\n\n"
        "[[edit]] Endi <b>bo'lim nomini</b> yuboring.\n"
        "<blockquote>Masalan: Dekanat, Yotoqxona, Stipendiya bo'limi, Kutubxona</blockquote>"
    ))


@router.message(BotSG.title, F.text)
async def bot_add_title(message: Message, state: FSMContext, db: Database, manager: BotManager):
    data = await state.get_data()
    await state.clear()
    title = message.text.strip()[:64]
    if await db.get_bot_by_tg(data["tg_id"]):
        await message.answer(R("[[stop]] Bu bot allaqachon qo'shilgan."), reply_markup=super_menu())
        return
    bid = await db.add_bot(data["tg_id"], data["username"], title, data["token"])
    rec = await db.get_bot(bid)
    try:
        await manager.start(rec)
        await manager.setup_profile(bid)
        status = R("[[active]] Bot ishga tushdi, tavsifi va buyruqlari sozlandi.")
    except Exception as ex:
        await db.set_bot_active(bid, False, str(ex)[:200])
        status = R(f"[[warn]] Bot saqlandi, lekin ishga tushmadi: <code>{esc(ex)}</code>")
    await message.answer(
        R(f"[[party]] <b>{esc(title)}</b> boti qo'shildi — @{esc(data['username'])}\n") + status
        + R("\n\n[[admins]] Endi bu botga admin tayinlang:"),
        reply_markup=super_menu(),
    )
    await message.answer(
        R(f"[[robot]] <b>{esc(title)}</b>"),
        reply_markup=ikb(
            [ibtn("add", "Admin qo'shish", f"sa:adm_add:{bid}", GREEN)],
            [ibtn("robot", "Bot kartasi", f"sa:bot:{bid}")],
        ),
    )


# ---- Boshqarish ----
@router.callback_query(F.data.startswith("sa:bot_toggle:"))
async def bot_toggle(call: CallbackQuery, db: Database, manager: BotManager):
    bid = int(call.data.split(":")[2])
    rec = await db.get_bot(bid)
    if not rec:
        return await call.answer("Bot topilmadi", show_alert=True)
    if manager.is_running(bid):
        await manager.stop(bid, reason="superadmin panel orqali to'xtatdi")
        await db.set_bot_active(bid, False)
        msg = "Bot to'xtatildi"
    else:
        try:
            await manager.start(rec)
            await db.set_bot_active(bid, True)
            msg = "Bot ishga tushdi"
        except Exception as ex:
            await db.set_bot_active(bid, False, str(ex)[:200])
            msg = f"Ishga tushmadi: {ex}"[:190]
    await _bot_card(call.message, db, manager, bid)
    await call.answer(msg, show_alert=msg.startswith("Ishga tushmadi"))


# ---- Anonimlik rejimi ----
@router.callback_query(F.data.startswith("sa:bot_anon:"))
async def bot_anon_ask(call: CallbackQuery, db: Database, manager: BotManager):
    bid = int(call.data.split(":")[2])
    b = await db.get_bot(bid)
    if not b:
        return await call.answer("Bot topilmadi", show_alert=True)
    if not b["anonymous"]:  # anonimlikni qayta yoqish — maxfiylikni oshiradi, tasdiq shart emas
        await _set_anon(call, db, manager, bid, True)
        return
    await call.message.edit_text(
        R(
            f"[[user]] <b>«{esc(b['title'])}» botida anonimlikni o'chirasizmi?</b>\n\n"
            "<blockquote>Shundan keyin yangi murojaatlarda adminlarga ko'rinadi:\n"
            "• murojaatchining ismi, username va Telegram ID'si;\n"
            "• «Murojaatchi bilan bog'lanish» tugmasi.</blockquote>\n"
            "[[lock]] <b>Oldin yuborilgan anonim murojaatlar anonim qoladi</b> — ularning muallifi hech qachon ochilmaydi.\n"
            "[[tip]] Talabalarga bot boshida va murojaat yozishda «murojaat anonim emas» deb aniq aytiladi."
        ),
        reply_markup=confirm_kb(f"sa:bot_anonok:{bid}:0", f"sa:bot:{bid}"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("sa:bot_anonok:"))
async def bot_anon_off(call: CallbackQuery, db: Database, manager: BotManager):
    _, _, bid, value = call.data.split(":")
    await _set_anon(call, db, manager, int(bid), value == "1")


async def _set_anon(call: CallbackQuery, db: Database, manager: BotManager, bid: int, anonymous: bool):
    await db.set_bot_anonymous(bid, anonymous)
    await manager.refresh_record(bid)
    await manager.setup_profile(bid)  # bot tavsifi ham rejimga moslanadi
    await _bot_card(call.message, db, manager, bid)
    await call.answer(
        "Anonimlik yoqildi: yangi murojaatlar anonim bo'ladi." if anonymous
        else "Anonimlik o'chirildi: yangi murojaatlarda murojaatchi ma'lumotlari ko'rinadi.",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("sa:bot_rename:"))
async def bot_rename_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(BotSG.rename)
    await state.update_data(bid=int(call.data.split(":")[2]))
    await call.answer()
    await call.message.answer(R("[[edit]] Bo'limning yangi nomini yuboring:"), reply_markup=cancel_kb())


@router.message(BotSG.rename, F.text)
async def bot_rename(message: Message, state: FSMContext, db: Database, manager: BotManager):
    bid = (await state.get_data())["bid"]
    await state.clear()
    await db.rename_bot(bid, message.text.strip()[:64])
    await manager.refresh_record(bid)
    await manager.setup_profile(bid)
    await message.answer(R("[[send]] Nomi o'zgartirildi, bot tavsifi yangilandi."), reply_markup=super_menu())
    await _bot_card(message, db, manager, bid, edit=False)


@router.callback_query(F.data.startswith("sa:bot_token:"))
async def bot_token_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(BotSG.new_token)
    await state.update_data(bid=int(call.data.split(":")[2]))
    await call.answer()
    await call.message.answer(
        R(
            "[[key]] <b>Yangi tokenni yuboring</b>\n"
            "<blockquote>BotFather → /mybots → bot → API Token → Revoke current token. "
            "Token aynan shu botniki bo'lishi kerak.</blockquote>"
        ),
        reply_markup=cancel_kb(),
    )


@router.message(BotSG.new_token, F.text)
async def bot_token_set(message: Message, state: FSMContext, db: Database, manager: BotManager):
    bid = (await state.get_data())["bid"]
    token = message.text.strip()
    await _delete_quietly(message)
    rec = await db.get_bot(bid)
    try:
        me = await manager.check_token(token, exclude_bot_id=bid)
    except TokenError as ex:
        await message.answer(R(f"[[stop]] {esc(ex)}"))
        return
    if me.id != rec["tg_id"]:
        await message.answer(R(f"[[stop]] Bu token boshqa botniki (@{esc(me.username)}). @{esc(rec['username'])} tokenini yuboring."))
        return
    await state.clear()
    await db.update_bot_token(bid, encrypt(token), me.username)
    await db.set_bot_active(bid, True)
    try:
        await manager.start(await db.get_bot(bid))
        text = R("[[send]] Token yangilandi va bot qayta ishga tushdi.")
    except Exception as ex:
        text = R(f"[[warn]] Token saqlandi, lekin bot ishga tushmadi: <code>{esc(ex)}</code>")
    await message.answer(text, reply_markup=super_menu())
    await _bot_card(message, db, manager, bid, edit=False)


@router.callback_query(F.data.startswith("sa:bot_del:"))
async def bot_delete_ask(call: CallbackQuery, db: Database):
    bid = int(call.data.split(":")[2])
    b = await db.get_bot(bid)
    if not b:
        return await call.answer("Bot topilmadi", show_alert=True)
    await call.message.edit_text(
        R(
            f"[[trash]] <b>{esc(b['title'])}</b> (@{esc(b['username'])}) botini o'chirasizmi?\n\n"
            "<blockquote>[[warn]] Bot to'xtatiladi, adminlari o'chiriladi. Murojaatlar tarixi bazada qoladi, "
            "lekin ulardagi rasm/videolarni endi ko'rib bo'lmaydi.\n"
            "Telegram'dagi botning o'zi o'chmaydi — uni BotFather'da o'chirasiz.</blockquote>"
        ),
        reply_markup=confirm_kb(f"sa:bot_delok:{bid}", f"sa:bot:{bid}"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("sa:bot_delok:"))
async def bot_delete(call: CallbackQuery, db: Database, manager: BotManager):
    bid = int(call.data.split(":")[2])
    await manager.stop(bid, reason="bot tizimdan o'chirildi")
    await db.delete_bot(bid)
    await _bots_view(call, db, manager)
    await call.answer("Bot o'chirildi")


# =============== Adminlar (har bir botga alohida) ===============
async def _admins_view(message: Message, db: Database, bid: int, edit=True):
    b = await db.get_bot(bid)
    admins = await db.bot_admins(bid)
    text = R(
        f"[[admins]] <b>{esc(b['title'])}</b> — adminlar ({len(admins)} ta)\n"
        "<blockquote>[[active]] faol · [[inactive]] nofaol\n"
        "Murojaatlar shu botning faol adminlariga keladi. Faol admin bo'lmasa — sizga.</blockquote>"
    )
    kw = dict(text=text, reply_markup=bot_admins_kb(bid, admins))
    await (message.edit_text(**kw) if edit else message.answer(**kw))


@router.callback_query(F.data.startswith("sa:admins:"))
async def admins_list(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    await _admins_view(call.message, db, int(call.data.split(":")[2]))
    await call.answer()


async def _admin_card(call: CallbackQuery, db: Database, bid: int, uid: int):
    a = await db.get_admin(bid, uid)
    if not a:
        await call.answer("Admin topilmadi", show_alert=True)
        return await _admins_view(call.message, db, bid)
    s = await db.admin_stats(uid, bid)
    started = await db.has_started(bid, uid)
    uname = f"@{esc(a['username'])}" if a["username"] else "—"
    state = R("[[active]] Faol") if a["is_active"] else R("[[inactive]] Nofaol")
    opened = R("[[send]] Botni ochgan") if started else R("[[warn]] Botni hali ochmagan — murojaatlar unga bormaydi")
    await call.message.edit_text(
        R(
            f"[[user]] <b>{esc(a['full_name'])}</b>\n\n"
            f"<blockquote>[[id]] ID: <code>{uid}</code>\n"
            f"[[link]] Username: {uname}\n"
            f"Holati: {state}\n{opened}\n"
            f"[[calendar]] Qo'shilgan: {a['added_at'][:16]}</blockquote>\n"
            f"[[st_answered]] Javob bergan: <b>{s['answered']}</b> · [[mail]] Xabarlar: <b>{s['replies']}</b> · "
            f"[[st_closed]] Yopgan: <b>{s['closed']}</b>"
        ),
        reply_markup=admin_card_kb(bid, a),
    )


@router.callback_query(F.data.startswith("sa:adm:"))
async def admin_card(call: CallbackQuery, db: Database):
    _, _, bid, uid = call.data.split(":")
    await _admin_card(call, db, int(bid), int(uid))
    await call.answer()


@router.callback_query(F.data.startswith("sa:adm_toggle:"))
async def admin_toggle(call: CallbackQuery, db: Database, manager: BotManager):
    _, _, bid, uid = call.data.split(":")
    bid, uid = int(bid), int(uid)
    await db.toggle_admin(bid, uid)
    a = await db.get_admin(bid, uid)
    dept = manager.get(bid)
    if dept:
        try:
            await dept.send_message(
                uid,
                R("[[active]] Siz yana admin sifatida faollashtirildingiz. /start") if a["is_active"]
                else R("[[inactive]] Bu botdagi admin huquqlaringiz vaqtincha to'xtatildi."),
            )
        except TelegramAPIError:
            pass
    await _admin_card(call, db, bid, uid)
    await call.answer("Holat o'zgartirildi")


@router.callback_query(F.data.startswith("sa:adm_del:"))
async def admin_delete_ask(call: CallbackQuery, db: Database):
    _, _, bid, uid = call.data.split(":")
    a = await db.get_admin(int(bid), int(uid))
    if not a:
        return await call.answer("Admin topilmadi", show_alert=True)
    await call.message.edit_text(
        R(f"[[trash]] <b>{esc(a['full_name'])}</b> ni bu botning adminlaridan olib tashlaysizmi?"),
        reply_markup=confirm_kb(f"sa:adm_delok:{bid}:{uid}", f"sa:adm:{bid}:{uid}"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("sa:adm_delok:"))
async def admin_delete(call: CallbackQuery, db: Database, manager: BotManager):
    _, _, bid, uid = call.data.split(":")
    bid, uid = int(bid), int(uid)
    await db.delete_admin(bid, uid)
    dept = manager.get(bid)
    if dept:
        try:
            await dept.send_message(uid, R("[[tip]] Siz bu botning adminlaridan chiqarildingiz. /start"))
        except TelegramAPIError:
            pass
    await _admins_view(call.message, db, bid)
    await call.answer("Admin olib tashlandi")


async def _send_invite(bot: Bot, db: Database, manager: BotManager, bid: int, uid: int) -> str:
    """Yangi adminga xabar: bo'lim botidan (agar ochgan bo'lsa) yoki asosiy botdan taklif havolasi."""
    b = await db.get_bot(bid)
    text = R(
        "[[party]] <b>Siz admin etib tayinlandingiz!</b>\n\n"
        f"<blockquote>[[robot]] Bo'lim: <b>{esc(b['title'])}</b> — @{esc(b['username'])}\n"
        "[[bell]] Murojaatlar shu botga keladi va javobni ham o'sha botdan yozasiz.</blockquote>\n\n"
        "[[warn]] Quyidagi tugma orqali botni oching va <b>«Start»</b> ni bosing — shundan keyin murojaatlar sizga kela boshlaydi."
    )
    kb = ikb([ibtn("open", f"@{b['username']} ni ochish", url=manager.link(b["username"], "admin"), style=GREEN)])
    dept = manager.get(bid)
    if dept and await db.has_started(bid, uid):
        try:
            await dept.send_message(uid, R(f"[[party]] Siz <b>{esc(b['title'])}</b> botining admini etib tayinlandingiz. /start"))
            return R("[[send]] Unga bo'lim boti orqali xabar yuborildi.")
        except TelegramAPIError:
            pass
    try:
        await bot.send_message(uid, text, reply_markup=kb)
        return R("[[send]] Unga asosiy bot orqali taklif havolasi yuborildi.")
    except TelegramAPIError:
        link = manager.link(b["username"], "admin")
        return R(
            "[[warn]] Unga xabar yuborib bo'lmadi (u botlarni hali ochmagan).\n"
            f"Bu havolani unga o'zingiz yuboring: <code>{link}</code>"
        )


@router.callback_query(F.data.startswith("sa:adm_invite:"))
async def admin_invite(call: CallbackQuery, bot: Bot, db: Database, manager: BotManager):
    _, _, bid, uid = call.data.split(":")
    result = await _send_invite(bot, db, manager, int(bid), int(uid))
    await call.answer()
    await call.message.answer(result)


@router.callback_query(F.data.startswith("sa:adm_add:"))
async def admin_add_start(call: CallbackQuery, state: FSMContext, db: Database):
    bid = int(call.data.split(":")[2])
    b = await db.get_bot(bid)
    await state.set_state(AddAdminSG.user)
    await state.update_data(bid=bid)
    await call.answer()
    await call.message.answer(
        R(
            f"[[add]] <b>{esc(b['title'])}</b> botiga admin qo'shish\n\n"
            "<blockquote>Quyidagi usullardan birini tanlang:\n"
            "[[one]] <b>«Foydalanuvchini tanlash»</b> tugmasi — kontaktlardan tanlash\n"
            "[[two]] Telegram ID sini yuboring (masalan <code>123456789</code>)\n"
            "[[three]] @username yuboring — u avval istalgan botimizga /start bosgan bo'lishi kerak\n"
            "[[four]] Uning biror xabarini shu yerga forward qiling</blockquote>"
        ),
        reply_markup=pick_user_kb(),
    )


async def _resolve_name(bot: Bot, db: Database, uid: int) -> tuple[str, str | None]:
    try:
        chat = await bot.get_chat(uid)
        return chat.full_name or str(uid), chat.username
    except Exception:  # foydalanuvchi botni ochmagan bo'lsa Telegram xato qaytaradi
        u = await db.get_user(uid)
        if u:
            return u["full_name"] or str(uid), u["username"]
    return str(uid), None


@router.message(AddAdminSG.user)
async def admin_add_user(message: Message, state: FSMContext, db: Database, bot: Bot, manager: BotManager):
    uid, name, username = None, None, None
    text = (message.text or "").strip()
    if message.users_shared:
        shared = message.users_shared.users[0]
        uid = shared.user_id
        name = " ".join(filter(None, [shared.first_name, shared.last_name])) or None
        username = shared.username
    elif message.forward_origin and getattr(message.forward_origin, "sender_user", None):
        u = message.forward_origin.sender_user
        uid, name, username = u.id, u.full_name, u.username
    elif text.isdigit():
        uid = int(text)
    elif text.startswith("@"):
        u = await db.find_user_by_username(text)
        if not u:
            await message.answer(R("[[stop]] Bu username bazada topilmadi. U avval botlardan biriga /start bosishi kerak."))
            return
        uid, name, username = u["user_id"], u["full_name"], u["username"]
    else:
        await message.answer(R(
            "[[warn]] Foydalanuvchini aniqlab bo'lmadi.\n"
            "<blockquote>Tugma orqali tanlang yoki ID yuboring. Forward qilingan xabar egasi "
            "maxfiylik sozlamasi tufayli yashirin bo'lishi mumkin.</blockquote>"
        ))
        return
    if not name:
        name, username2 = await _resolve_name(bot, db, uid)
        username = username or username2
    bid = (await state.get_data())["bid"]
    await state.clear()
    await db.add_admin(bid, uid, name, username)
    result = await _send_invite(bot, db, manager, bid, uid)
    await message.answer(
        R(f"[[party]] <b>{esc(name)}</b> admin qilib qo'shildi.\n") + result,
        reply_markup=super_menu(),
    )
    await _admins_view(message, db, bid, edit=False)


# =============== Murojaatlar ===============
@router.callback_query(F.data == "sa:appeals")
async def appeals_menu(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    s = await db.stats()
    await call.message.edit_text(
        R("[[envelope]] <b>Murojaatlar</b>\n\n") + f"<blockquote>{_statuses(s)}\nJami: <b>{s['total']}</b></blockquote>\n"
        "Qaysi botning murojaatlari?",
        reply_markup=bot_choice_kb(await db.bots(), "sa:apsc", "Barcha botlar"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("sa:apsc:"))
async def appeals_scope(call: CallbackQuery, db: Database):
    scope = call.data.split(":")[2]
    title = "Barcha botlar"
    if scope != "a":
        b = await db.get_bot(int(scope))
        title = b["title"] if b else "?"
    await call.message.edit_text(
        R(f"[[envelope]] <b>Murojaatlar</b> — {esc(title)}\nHolat bo'yicha tanlang:"),
        reply_markup=appeals_filter_kb(scope),
    )
    await call.answer()


@router.callback_query(F.data.startswith("sa:apf:"))
async def appeals_filtered(call: CallbackQuery, db: Database):
    _, _, scope, status, page = call.data.split(":")
    page = int(page)
    statuses = None if status == "all" else [status]
    bot_filter = "any" if scope == "a" else int(scope)
    total = await db.count_appeals(statuses, bot_filter)
    appeals = await db.list_appeals(statuses, bot_filter, limit=PAGE, offset=page * PAGE)
    nav = []
    if page > 0:
        nav.append(ibtn("prev", "Oldingi", f"sa:apf:{scope}:{status}:{page - 1}"))
    if (page + 1) * PAGE < total:
        nav.append(ibtn("next", "Keyingi", f"sa:apf:{scope}:{status}:{page + 1}"))
    label = R("[[list]] Barchasi") if status == "all" else status_label(status)
    pages = max(1, (total + PAGE - 1) // PAGE)
    text = (
        f"<b>{label}</b> — {total} ta (sahifa {page + 1}/{pages})\nKo'rish uchun murojaatni tanlang:"
        if total else f"<b>{label}</b> — murojaat yo'q."
    )
    await call.message.edit_text(
        text, reply_markup=appeals_list_kb(appeals, back=f"sa:apsc:{scope}", nav=nav, cb_prefix="sa:apv")
    )
    await call.answer()


async def _show_appeal(message: Message, db: Database, appeal: dict):
    await message.answer(await appeal_text_view(db, appeal), reply_markup=appeal_main_kb(appeal))


@router.callback_query(F.data.startswith("sa:apv:"))
async def appeal_view(call: CallbackQuery, db: Database):
    appeal = await db.get_appeal(int(call.data.split(":")[2]))
    if not appeal:
        return await call.answer("Murojaat topilmadi", show_alert=True)
    await call.answer()
    await _show_appeal(call.message, db, appeal)


@router.callback_query(F.data == "sa:ap_find")
async def appeal_find_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(FindAppealSG.appeal_id)
    await call.answer()
    await call.message.answer(R("[[search]] Murojaat raqamini yuboring (masalan: <code>15</code>):"), reply_markup=cancel_kb())


@router.message(FindAppealSG.appeal_id)
async def appeal_find(message: Message, state: FSMContext, db: Database):
    text = (message.text or "").strip().lstrip("#")
    if not text.isdigit():
        await message.answer(R("[[warn]] Faqat raqam yuboring."))
        return
    appeal = await db.get_appeal(int(text))
    if not appeal:
        await message.answer(R("[[stop]] Bunday murojaat topilmadi. Boshqa raqam yuboring yoki bekor qiling."))
        return
    await state.clear()
    await message.answer(R("[[search]] Topildi:"), reply_markup=super_menu())
    await _show_appeal(message, db, appeal)


# =============== Bloklash (har qanday botda) ===============
@block_router.callback_query(F.data.startswith("blk:ask:"))
async def block_ask(call: CallbackQuery):
    aid = int(call.data.split(":")[2])
    await call.answer()
    await call.message.answer(
        R(
            f"[[block]] Murojaat <b>#{aid}</b> muallifini bloklaysizmi?\n"
            "<blockquote>U <b>barcha botlarda</b> murojaat yubora olmaydi. Shaxsi baribir yashirin qoladi.</blockquote>"
        ),
        reply_markup=confirm_kb(f"blk:ok:{aid}", "blk:no"),
    )


@block_router.callback_query(F.data.startswith("blk:ok:"))
async def block_user(call: CallbackQuery, db: Database):
    appeal = await db.get_appeal(int(call.data.split(":")[2]))
    if not appeal:
        return await call.answer("Murojaat topilmadi", show_alert=True)
    await db.set_blocked(appeal["user_id"], True)
    await call.message.edit_text(R(f"[[block]] Murojaat #{appeal['id']} muallifi barcha botlarda bloklandi."))
    await call.answer()


@block_router.callback_query(F.data == "blk:no")
async def block_cancel(call: CallbackQuery):
    await call.message.delete()
    await call.answer("Bekor qilindi")


async def _blocked_view(call: CallbackQuery, db: Database):
    rows = await db.blocked_users()
    await call.message.edit_text(
        R(
            f"[[block]] <b>Bloklangan foydalanuvchilar</b> — {len(rows)} ta\n"
            "<blockquote>[[lock]] Anonimlik saqlanadi — faqat oxirgi murojaat raqami ko'rsatiladi.</blockquote>"
        ),
        reply_markup=blocked_kb(rows),
    )


@router.callback_query(F.data == "sa:blocked")
async def blocked_list(call: CallbackQuery, db: Database):
    await _blocked_view(call, db)
    await call.answer()


@router.callback_query(F.data.startswith("sa:unblock:"))
async def unblock(call: CallbackQuery, db: Database):
    await db.set_blocked(int(call.data.split(":")[2]), False)
    await _blocked_view(call, db)
    await call.answer("Blokdan chiqarildi")


# =============== E'lon (broadcast) ===============
REUPLOAD = {"photo", "video", "document", "audio", "voice", "animation"}


@router.callback_query(F.data == "sa:broadcast")
async def broadcast_target(call: CallbackQuery, state: FSMContext, db: Database):
    await state.clear()
    bots = await db.bots(only_active=True)
    kb = bot_choice_kb(bots, "sa:bct", "Hammaga (har kimga bir marta)")
    kb.inline_keyboard.insert(1, [ibtn("panel", "Faqat asosiy bot foydalanuvchilari", "sa:bct:0")])
    await call.message.edit_text(
        R("[[broadcast]] <b>E'lon yuborish</b>\n\nKimlarga yuborilsin?"), reply_markup=kb
    )
    await call.answer()


@router.callback_query(F.data.startswith("sa:bct:"))
async def broadcast_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastSG.content)
    await state.update_data(target=call.data.split(":")[2])
    await call.answer()
    await call.message.answer(
        R(
            "[[broadcast]] E'lon xabarini yuboring.\n\n"
            "<blockquote><b>Bitta</b> xabar: matn, rasm, video, fayl, audio, ovozli xabar yoki GIF. "
            "Formatlash va premium emojilar saqlanadi.\n"
            "Yuborishdan oldin tasdiqlash so'raladi.</blockquote>"
        ),
        reply_markup=cancel_kb(),
    )


async def _targets(db: Database, manager: BotManager, target: str) -> dict[int, list[int]]:
    """bot_id -> foydalanuvchilar. «Hammaga» rejimida har bir odam faqat bir marta oladi."""
    if target == "0":
        return {MAIN_BOT_ID: await db.bot_user_ids(MAIN_BOT_ID)}
    if target != "a":
        bid = int(target)
        return {bid: await db.bot_user_ids(bid)} if manager.get(bid) else {}
    out: dict[int, list[int]] = {}
    seen: set[int] = set()
    for bid in [MAIN_BOT_ID] + [b["id"] for b in await db.bots(only_active=True) if manager.get(b["id"])]:
        ids = [u for u in await db.bot_user_ids(bid) if u not in seen]
        seen.update(ids)
        if ids:
            out[bid] = ids
    return out


@router.message(BroadcastSG.content)
async def broadcast_preview(message: Message, state: FSMContext, db: Database, manager: BotManager):
    content = extract_content(message)
    target = (await state.get_data())["target"]
    if content is None or (target != "0" and content["type"] not in REUPLOAD | {"text"}):
        await message.answer(R("[[warn]] Bu turdagi xabarni bo'lim botlari orqali yuborib bo'lmaydi. Boshqa xabar yuboring."))
        return
    if message.document:
        content["file_name"] = message.document.file_name
    targets = await _targets(db, manager, target)
    total = sum(len(v) for v in targets.values())
    await state.set_state(BroadcastSG.confirm)
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id, content=content)
    await message.answer(
        R(f"[[broadcast]] Yuqoridagi xabar <b>{total} ta</b> foydalanuvchiga ({len(targets)} ta bot orqali) yuborilsinmi?"),
        reply_markup=confirm_kb("sa:bc_ok", "sa:bc_no"),
    )


@router.callback_query(BroadcastSG.confirm, F.data == "sa:bc_no")
async def broadcast_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(R("[[cancel]] E'lon bekor qilindi."))
    await call.message.answer(R("[[panel]] Bosh menyu"), reply_markup=super_menu())
    await call.answer()


@router.callback_query(BroadcastSG.confirm, F.data == "sa:bc_ok")
async def broadcast_go(call: CallbackQuery, state: FSMContext, db: Database, bot: Bot, manager: BotManager):
    data = await state.get_data()
    await state.clear()
    targets = await _targets(db, manager, data["target"])
    await call.message.edit_text(R(f"[[st_progress]] {sum(len(v) for v in targets.values())} ta foydalanuvchiga yuborilmoqda..."))
    await call.message.answer(R("[[tip]] Natija tayyor bo'lganda xabar beraman."), reply_markup=super_menu())
    await call.answer()
    asyncio.create_task(_broadcast(bot, manager, call.from_user.id, targets, data))


async def _send_with_retry(coro_factory):
    try:
        return await coro_factory()
    except TelegramRetryAfter as ex:
        await asyncio.sleep(ex.retry_after)
        return await coro_factory()


async def _broadcast(main_bot: Bot, manager: BotManager, report_to: int, targets: dict[int, list[int]], data: dict):
    content = data["content"]
    ok = fail = 0
    file_bytes: bytes | None = None
    for bid, user_ids in targets.items():
        if bid == MAIN_BOT_ID:
            for uid in user_ids:
                try:
                    await _send_with_retry(lambda: main_bot.copy_message(uid, data["chat_id"], data["message_id"]))
                    ok += 1
                except TelegramAPIError:
                    fail += 1
                await asyncio.sleep(0.05)
            continue
        dept = manager.get(bid)
        if not dept:
            fail += len(user_ids)
            continue
        t = content["type"]
        file_ref = None  # shu botdagi file_id (birinchi yuklashdan keyin)
        if t != "text" and file_bytes is None:
            try:  # fayl boshqa botga tegishli — bir marta yuklab olib, qayta yuklaymiz (20 MB gacha)
                buf = await main_bot.download(content["file_id"], destination=io.BytesIO())
                file_bytes = buf.getvalue()
            except Exception as ex:
                log.warning("E'lon faylini yuklab bo'lmadi: %s", ex)
                fail += sum(len(v) for k, v in targets.items() if k != MAIN_BOT_ID)
                break
        for uid in user_ids:
            try:
                if t == "text":
                    await _send_with_retry(lambda: dept.send_message(uid, content["text"]))
                else:
                    media = file_ref or BufferedInputFile(file_bytes, filename=content.get("file_name") or f"file.{t}")
                    sender = getattr(dept, f"send_{t}")
                    msg = await _send_with_retry(lambda: sender(uid, media, caption=content.get("text")))
                    if file_ref is None:
                        obj = msg.photo[-1] if t == "photo" else getattr(msg, t)
                        file_ref = obj.file_id
                ok += 1
            except TelegramAPIError:
                fail += 1
            await asyncio.sleep(0.05)
    try:
        await main_bot.send_message(report_to, R(
            f"[[broadcast]] <b>E'lon yuborish tugadi</b>\n"
            f"<blockquote>[[send]] Yetkazildi: <b>{ok}</b>\n[[cancel]] Xato: <b>{fail}</b></blockquote>"
        ))
    except TelegramAPIError:
        log.warning("E'lon hisobotini yuborib bo'lmadi")
