from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup,
)

from bot.db import STATUSES
from bot.ui import EMOJI, custom_of, ibtn, plain, rbtn

# Tugma rangi (Bot API style)
GREEN, RED, BLUE = "success", "danger", "primary"

# ---------- Reply tugmalar: (emoji kaliti, matn) ----------
RB_NEW = ("write", "Murojaat yuborish")
RB_MY = ("list", "Mening murojaatlarim")
RB_HELP = ("help", "Qanday ishlaydi?")
RB_SEND = ("send", "Yuborish")
RB_CANCEL = ("cancel", "Bekor qilish")
RB_OPEN = ("inbox", "Ochiq murojaatlar")
RB_MYSTATS = ("stats", "Statistikam")
RB_PANEL = ("panel", "Admin panel")
RB_PICK = ("user", "Foydalanuvchini tanlash")
RB_CATALOG = ("robot", "Bo'limlar")
RB_REPORT = ("report", "Hisobot")


def _rows(buttons: list, width: int) -> list[list]:
    return [buttons[i:i + width] for i in range(0, len(buttons), width)]


def ikb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


def url_btn(key: str, text: str, url: str, style: str | None = BLUE) -> InlineKeyboardButton:
    return ibtn(key, text, url=url, style=style)


# ---------- Reply menyular ----------
def student_menu() -> ReplyKeyboardMarkup:
    """Bo'lim botidagi talaba menyusi."""
    return ReplyKeyboardMarkup(
        keyboard=[[rbtn(RB_NEW, BLUE)], [rbtn(RB_MY), rbtn(RB_HELP)]],
        resize_keyboard=True,
        input_field_placeholder="Murojaat yuborish uchun tugmani bosing",
    )


def admin_menu() -> ReplyKeyboardMarkup:
    """Bo'lim botidagi admin (va superadmin) menyusi."""
    return ReplyKeyboardMarkup(
        keyboard=[[rbtn(RB_OPEN, BLUE)], [rbtn(RB_MYSTATS), rbtn(RB_REPORT)]],
        resize_keyboard=True,
    )


def super_menu() -> ReplyKeyboardMarkup:
    """Asosiy botdagi superadmin menyusi."""
    return ReplyKeyboardMarkup(
        keyboard=[[rbtn(RB_PANEL, GREEN)], [rbtn(RB_CATALOG)]],
        resize_keyboard=True,
    )


def collect_kb(placeholder: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[rbtn(RB_SEND, GREEN), rbtn(RB_CANCEL, RED)]],
        resize_keyboard=True,
        input_field_placeholder=placeholder,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[rbtn(RB_CANCEL, RED)]], resize_keyboard=True)


def pick_user_kb() -> ReplyKeyboardMarkup:
    req = KeyboardButtonRequestUsers(
        request_id=1, user_is_bot=False, max_quantity=1, request_name=True, request_username=True,
    )
    return ReplyKeyboardMarkup(
        keyboard=[[rbtn(RB_PICK, BLUE, request_users=req)], [rbtn(RB_CANCEL, RED)]],
        resize_keyboard=True,
    )


# ---------- Xabar yig'ish ----------
def collect_actions_kb(count: int) -> InlineKeyboardMarkup:
    return ikb(
        [ibtn("send", f"Yuborish ({count} ta xabar)", "col:send", GREEN)],
        [ibtn("eye", "Ko'rib chiqish", "col:preview"), ibtn("undo", "Oxirgisini o'chirish", "col:undo")],
        [ibtn("cancel", "Bekor qilish", "col:cancel", RED)],
    )


# ---------- Murojaatlar ----------
def appeal_actions_kb(appeal_id: int, status: str, is_super=False) -> InlineKeyboardMarkup:
    """Murojaat kartasi tugmalari — holatga qarab faqat mumkin bo'lgan amallar ko'rsatiladi."""
    a = appeal_id
    if status == "new":
        first = [ibtn("accept", "Qabul qilish", f"ap:accept:{a}", GREEN), ibtn("reject", "Rad etish", f"ap:reject:{a}", RED)]
    elif status == "in_progress":
        first = [ibtn("reply", "Javob yozish", f"ap:reply:{a}", BLUE), ibtn("lock", "Yopish", f"ap:close:{a}", RED)]
    elif status == "answered":
        first = [ibtn("reply", "Yana javob yozish", f"ap:reply:{a}", BLUE), ibtn("lock", "Yopish", f"ap:close:{a}", RED)]
    else:  # closed / rejected
        first = [ibtn("unlock", "Qayta ochish", f"ap:reopen:{a}", GREEN)]
    second = [ibtn("history", "Tarix", f"ap:history:{a}")]
    if is_super:
        second.append(ibtn("block", "Muallifni bloklash", f"blk:ask:{a}", RED))
    return ikb(first, second)


def reject_kb(appeal_id: int) -> InlineKeyboardMarkup:
    return ikb(
        [ibtn("reject", "Sababsiz rad etish", f"ap:rejnr:{appeal_id}", RED)],
        [ibtn("back", "Bekor qilish (rad etmaslik)", "ap:rejcancel")],
    )


def appeals_list_kb(appeals: list[dict], back: str | None = None, nav: list | None = None,
                    cb_prefix: str = "ap:open") -> InlineKeyboardMarkup:
    rows = []
    for a in appeals:
        key = STATUSES.get(a["status"], ("st_new",))[0]
        where = a.get("bot_title") or "O'chirilgan bot"
        cat = f" · {a['category_title'][:24]}" if a.get("category_title") else ""
        rows.append([ibtn(key, f"#{a['id']} · {where}{cat} · {a['created_at'][5:16]}", f"{cb_prefix}:{a['id']}")])
    if nav:
        rows.append(nav)
    if back:
        rows.append([ibtn("back", "Orqaga", back)])
    return ikb(*rows)


def confirm_kb(yes_cb: str, no_cb: str) -> InlineKeyboardMarkup:
    return ikb([ibtn("yes", "Ha", yes_cb, GREEN), ibtn("no", "Yo'q", no_cb, RED)])


def back_kb(cb="sa:panel") -> InlineKeyboardMarkup:
    return ikb([ibtn("back", "Orqaga", cb)])


# ---------- Hisobotlar ----------
def period_kb(prefix: str, back: str | None = None) -> InlineKeyboardMarkup:
    """Davr tanlash: haftalik / oylik / yillik (joriy va o'tgan)."""
    rows = [
        [ibtn("calendar", "Shu hafta", f"{prefix}:w0", BLUE), ibtn("calendar", "O'tgan hafta", f"{prefix}:w1")],
        [ibtn("calendar", "Shu oy", f"{prefix}:m0", BLUE), ibtn("calendar", "O'tgan oy", f"{prefix}:m1")],
        [ibtn("calendar", "Shu yil", f"{prefix}:y0", BLUE), ibtn("calendar", "O'tgan yil", f"{prefix}:y1")],
    ]
    rows.append([ibtn("back", "Orqaga", back)] if back else [ibtn("cancel", "Bekor qilish", "rep:cancel", RED)])
    return ikb(*rows)


# ---------- Asosiy bot: katalog ----------
def catalog_kb(bots: list[dict]) -> InlineKeyboardMarkup:
    return ikb(*[[url_btn("folder", b["title"], f"https://t.me/{b['username']}")] for b in bots])


# ---------- Superadmin panel ----------
def panel_kb() -> InlineKeyboardMarkup:
    return ikb(
        [ibtn("robot", "Bo'lim botlari", "sa:bots", GREEN)],
        [ibtn("stats", "Statistika", "sa:stats", BLUE), ibtn("envelope", "Murojaatlar", "sa:appeals", BLUE)],
        [ibtn("report", "Excel hisobotlar", "sa:reports", GREEN)],
        [ibtn("block", "Bloklanganlar", "sa:blocked"), ibtn("broadcast", "E'lon yuborish", "sa:broadcast")],
        [ibtn("sparkles", "Premium emojilar", "em:menu")],
    )


def bots_kb(bots: list[dict], running: set[int]) -> InlineKeyboardMarkup:
    rows = []
    for b in bots:
        key = "active" if b["id"] in running else "inactive"
        extra = f" · {b['open_appeals']} ochiq" if b["open_appeals"] else ""
        rows.append([ibtn(key, f"{b['title']} (@{b['username']}){extra}", f"sa:bot:{b['id']}")])
    rows.append([ibtn("add", "Bo'lim boti qo'shish", "sa:bot_add", GREEN)])
    rows.append([ibtn("back", "Orqaga", "sa:panel")])
    return ikb(*rows)


def bot_card_kb(b: dict, running: bool) -> InlineKeyboardMarkup:
    bid = b["id"]
    toggle = (
        ibtn("inactive", "To'xtatish", f"sa:bot_toggle:{bid}", RED) if running
        else ibtn("active", "Ishga tushirish", f"sa:bot_toggle:{bid}", GREEN)
    )
    return ikb(
        [ibtn("admins", "Adminlar", f"sa:admins:{bid}", BLUE), ibtn("stats", "Statistika", f"sa:bot_stats:{bid}")],
        [ibtn("envelope", "Murojaatlari", f"sa:apf:{bid}:all:0"), ibtn("report", "Excel hisobot", f"sa:rpb:{bid}", GREEN)],
        [ibtn("category", "Murojaat kategoriyalari", f"sa:cats:{bid}", BLUE)],
        [url_btn("open", "Botni ochish", f"https://t.me/{b['username']}", None)],
        [toggle],
        [ibtn("edit", "Bo'lim nomini o'zgartirish", f"sa:bot_rename:{bid}"), ibtn("key", "Tokenni almashtirish", f"sa:bot_token:{bid}")],
        [ibtn("trash", "Botni o'chirish", f"sa:bot_del:{bid}", RED)],
        [ibtn("back", "Orqaga", "sa:bots")],
    )


# ---------- Kategoriyalar ----------
def categories_kb(bid: int, cats: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [ibtn("active" if c["is_active"] else "inactive", f"{c['title']} · {c['appeals']}", f"sa:cat:{c['id']}")]
        for c in cats
    ]
    rows.append([ibtn("add", "Kategoriya qo'shish", f"sa:cat_add:{bid}", GREEN)])
    rows.append([ibtn("back", "Orqaga", f"sa:bot:{bid}")])
    return ikb(*rows)


def category_card_kb(cat: dict, first: bool, last: bool) -> InlineKeyboardMarkup:
    cid = cat["id"]
    toggle = (
        ibtn("inactive", "Yashirish", f"sa:cat_tog:{cid}", RED) if cat["is_active"]
        else ibtn("active", "Ko'rsatish", f"sa:cat_tog:{cid}", GREEN)
    )
    move = []
    if not first:
        move.append(ibtn("up", "Yuqoriga", f"sa:cat_mv:{cid}:-1"))
    if not last:
        move.append(ibtn("down", "Pastga", f"sa:cat_mv:{cid}:1"))
    rows = [[ibtn("edit", "Nomini o'zgartirish", f"sa:cat_ren:{cid}"), toggle]]
    if cat.get("description"):
        rows.append([ibtn("info", "Izohni o'zgartirish", f"sa:cat_desc:{cid}", BLUE),
                     ibtn("trash", "Izohni o'chirish", f"sa:cat_descdel:{cid}")])
    else:
        rows.append([ibtn("info", "Izoh qo'shish", f"sa:cat_desc:{cid}", GREEN)])
    if move:
        rows.append(move)
    rows.append([ibtn("trash", "O'chirish", f"sa:cat_del:{cid}", RED)])
    rows.append([ibtn("back", "Orqaga", f"sa:cats:{cat['bot_id']}")])
    return ikb(*rows)


def category_pick_kb(cats: list[dict]) -> InlineKeyboardMarkup:
    """Talaba uchun: murojaat kategoriyasini tanlash."""
    rows = [[ibtn("category", c["title"], f"cat:pick:{c['id']}")] for c in cats]
    rows.append([ibtn("cancel", "Bekor qilish", "col:cancel", RED)])
    return ikb(*rows)


def bot_admins_kb(bid: int, admins: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [ibtn("active" if a["is_active"] else "inactive", a["full_name"] or str(a["user_id"]), f"sa:adm:{bid}:{a['user_id']}")]
        for a in admins
    ]
    rows.append([ibtn("add", "Admin qo'shish", f"sa:adm_add:{bid}", GREEN)])
    rows.append([ibtn("back", "Orqaga", f"sa:bot:{bid}")])
    return ikb(*rows)


def admin_card_kb(bid: int, admin: dict) -> InlineKeyboardMarkup:
    uid = admin["user_id"]
    toggle = (
        ibtn("inactive", "Nofaol qilish", f"sa:adm_toggle:{bid}:{uid}", RED) if admin["is_active"]
        else ibtn("active", "Faol qilish", f"sa:adm_toggle:{bid}:{uid}", GREEN)
    )
    return ikb(
        [toggle],
        [ibtn("invite", "Taklif havolasini qayta yuborish", f"sa:adm_invite:{bid}:{uid}", BLUE)],
        [ibtn("trash", "Adminlikdan olish", f"sa:adm_del:{bid}:{uid}", RED)],
        [ibtn("back", "Orqaga", f"sa:admins:{bid}")],
    )


def bot_choice_kb(bots: list[dict], prefix: str, all_text: str | None = None, back: str = "sa:panel") -> InlineKeyboardMarkup:
    rows = []
    if all_text:
        rows.append([ibtn("globe", all_text, f"{prefix}:a", BLUE)])
    rows += [[ibtn("robot", b["title"], f"{prefix}:{b['id']}")] for b in bots]
    rows.append([ibtn("back", "Orqaga", back)])
    return ikb(*rows)


def appeals_filter_kb(scope: str) -> InlineKeyboardMarkup:
    st = [ibtn(key, name, f"sa:apf:{scope}:{code}:0") for code, (key, name) in STATUSES.items()]
    return ikb(
        *_rows(st, 2),
        [ibtn("list", "Barchasi", f"sa:apf:{scope}:all:0", BLUE)],
        [ibtn("search", "Raqam bo'yicha topish", "sa:ap_find")],
        [ibtn("back", "Orqaga", "sa:appeals")],
    )


def appeal_main_kb(appeal: dict) -> InlineKeyboardMarkup:
    """Asosiy botda murojaatni ko'rish: media bo'lim botida ochiladi."""
    rows = []
    if appeal.get("bot_username"):
        rows.append([url_btn("open", f"@{appeal['bot_username']} da ochish",
                             f"https://t.me/{appeal['bot_username']}?start=ap_{appeal['id']}")])
    rows.append([ibtn("block", "Muallifni bloklash", f"blk:ask:{appeal['id']}", RED)])
    return ikb(*rows)


def blocked_kb(rows: list[dict]) -> InlineKeyboardMarkup:
    out = []
    for r in rows:
        label = f"#{r['last_appeal']} muallifi" if r["last_appeal"] else "Murojaatsiz foydalanuvchi"
        out.append([ibtn("unlock", f"{label} — blokdan chiqarish", f"sa:unblock:{r['user_id']}", GREEN)])
    out.append([ibtn("back", "Orqaga", "sa:panel")])
    return ikb(*out)


# ---------- Premium emoji boshqaruvi ----------
EMOJI_PAGE = 16


def emoji_menu_kb(enabled: bool) -> InlineKeyboardMarkup:
    return ikb(
        [ibtn("list", "Barcha emojilar ro'yxati", "em:list:0", BLUE)],
        [ibtn("bolt", "Ketma-ket sozlash (faqat sozlanmaganlar)", "em:wiz:unset", GREEN)],
        [ibtn("bolt", "Ketma-ket sozlash (hammasini qaytadan)", "em:wiz:all")],
        [
            ibtn("inactive", "Premiumni o'chirish", "em:toggle", RED) if enabled
            else ibtn("active", "Premiumni yoqish", "em:toggle", GREEN)
        ],
        [ibtn("trash", "Hammasini tozalash", "em:clear", RED)],
        [ibtn("back", "Orqaga", "sa:panel")],
    )


def emoji_list_kb(page: int) -> InlineKeyboardMarkup:
    """Ro'yxatda emojilar ODDIY ko'rinishda; premium biriktirilganlari yashil rangda."""
    keys = list(EMOJI)
    chunk = keys[page * EMOJI_PAGE:(page + 1) * EMOJI_PAGE]
    btns = [
        InlineKeyboardButton(
            text=f"{plain(k)} {EMOJI[k][1]}" + (" ✓" if custom_of(k) else ""),
            callback_data=f"em:key:{k}:{page}",
            style=GREEN if custom_of(k) else None,
        )
        for k in chunk
    ]
    rows = _rows(btns, 2)
    nav = []
    if page > 0:
        nav.append(ibtn("prev", "Oldingi", f"em:list:{page - 1}"))
    if (page + 1) * EMOJI_PAGE < len(keys):
        nav.append(ibtn("next", "Keyingi", f"em:list:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([ibtn("back", "Orqaga", "em:menu")])
    return ikb(*rows)


def emoji_card_kb(key: str, page: int) -> InlineKeyboardMarkup:
    rows = [[ibtn("star", "Premium emoji biriktirish", f"em:set:{key}:{page}", GREEN)]]
    if custom_of(key):
        rows.append([ibtn("reset", "Oddiy holiga qaytarish", f"em:del:{key}:{page}", RED)])
    rows.append([ibtn("back", "Orqaga", f"em:list:{page}")])
    return ikb(*rows)


def emoji_wizard_kb() -> InlineKeyboardMarkup:
    return ikb(
        [ibtn("skip", "O'tkazib yuborish", "em:skip"), ibtn("reset", "Oddiy qilib qo'yish", "em:wreset")],
        [ibtn("stop", "To'xtatish", "em:stop", RED)],
    )
