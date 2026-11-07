"""SQLite (aiosqlite) bilan ishlash. Ko'p botli tuzilma: asosiy bot (bot_id=0) + bo'lim botlari."""
import os
from datetime import datetime

import aiosqlite

MAIN_BOT_ID = 0  # bot_users jadvalida asosiy bot shu raqam bilan saqlanadi

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    full_name   TEXT,
    username    TEXT,
    is_blocked  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id       INTEGER NOT NULL UNIQUE,
    username    TEXT NOT NULL,
    title       TEXT NOT NULL,
    token_enc   TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    anonymous   INTEGER NOT NULL DEFAULT 1,   -- 1: murojaatchi anonim; 0: ismi/username/ID adminlarga ko'rinadi
    last_error  TEXT,
    added_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_admins (
    bot_id      INTEGER NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL,
    full_name   TEXT,
    username    TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1,
    added_at    TEXT NOT NULL,
    PRIMARY KEY (bot_id, user_id)
);

CREATE TABLE IF NOT EXISTS bot_users (
    bot_id      INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    started_at  TEXT NOT NULL,
    PRIMARY KEY (bot_id, user_id)
);

CREATE TABLE IF NOT EXISTS appeals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id       INTEGER,
    user_id      INTEGER NOT NULL,
    status       TEXT NOT NULL DEFAULT 'new',  -- new | in_progress | answered | closed
    admin_id     INTEGER,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    anonymous    INTEGER NOT NULL DEFAULT 1   -- yuborilgan paytdagi rejim (keyin o'zgarsa ham eski murojaat anonim qoladi)
);

CREATE TABLE IF NOT EXISTS appeal_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    appeal_id     INTEGER NOT NULL REFERENCES appeals(id) ON DELETE CASCADE,
    sender        TEXT NOT NULL,          -- student | admin
    sender_id     INTEGER NOT NULL,
    content_type  TEXT NOT NULL,
    file_id       TEXT,
    text          TEXT,
    created_at    TEXT NOT NULL
);

-- Murojaat bilan bog'liq amallar tarixi (hisobotlardagi reaksiya vaqti va admin faolligi uchun)
CREATE TABLE IF NOT EXISTS appeal_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    appeal_id   INTEGER NOT NULL,
    action      TEXT NOT NULL,      -- in_progress | answered | closed | rejected
    admin_id    INTEGER,
    at          TEXT NOT NULL
);

-- Adminlarga yuborilgan murojaat kartalari: holat o'zgarsa hammasi bir vaqtda yangilanadi
CREATE TABLE IF NOT EXISTS appeal_cards (
    appeal_id   INTEGER NOT NULL,
    chat_id     INTEGER NOT NULL,
    message_id  INTEGER NOT NULL,
    PRIMARY KEY (appeal_id, chat_id, message_id)
);

-- Murojaat kategoriyalari (har bir bo'lim boti uchun alohida; bo'lmasa — kategoriyasiz ishlaydi)
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id      INTEGER NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1,   -- 0 = talabalarga ko'rinmaydi
    is_deleted  INTEGER NOT NULL DEFAULT 0,   -- o'chirilgan, lekin eski murojaatlar/hisobot uchun saqlanadi
    description TEXT,                         -- ixtiyoriy izoh (HTML): kategoriya tanlangach talabaga ko'rsatiladi
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_emojis (
    key       TEXT PRIMARY KEY,
    emoji_id  TEXT NOT NULL,
    alt       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_appeals_status ON appeals(status);
CREATE INDEX IF NOT EXISTS idx_appeals_user ON appeals(user_id);
CREATE INDEX IF NOT EXISTS idx_appeals_bot ON appeals(bot_id);
CREATE INDEX IF NOT EXISTS idx_msgs_appeal ON appeal_messages(appeal_id);
CREATE INDEX IF NOT EXISTS idx_appeals_category ON appeals(category_id);
CREATE INDEX IF NOT EXISTS idx_categories_bot ON categories(bot_id);
"""

# holat -> (emoji kaliti, nomi)
# Hayot sikli: new → (qabul) in_progress → (javob) answered → (yopish) closed
#              new → (rad etish) rejected;  closed/rejected → (qayta ochish) in_progress
STATUSES = {
    "new": ("st_new", "Yangi"),
    "in_progress": ("st_progress", "Qabul qilingan"),
    "answered": ("st_answered", "Javob berilgan"),
    "closed": ("st_closed", "Yopilgan"),
    "rejected": ("st_rejected", "Rad etilgan"),
}
OPEN_STATUSES = ["new", "in_progress"]  # «Ochiq murojaatlar» — hali javob berilmaganlar

_APPEAL_SELECT = """SELECT ap.*, b.title AS bot_title, b.username AS bot_username,
                           ad.full_name AS admin_name, c.title AS category_title,
                           au.full_name AS author_name, au.username AS author_username
                    FROM appeals ap
                    LEFT JOIN bots b ON b.id = ap.bot_id
                    LEFT JOIN users ad ON ad.user_id = ap.admin_id
                    LEFT JOIN users au ON au.user_id = ap.user_id
                    LEFT JOIN categories c ON c.id = ap.category_id"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys = ON")
        await self.conn.execute("PRAGMA journal_mode = WAL")      # tezroq yozish, o'qish bloklanmaydi
        await self.conn.execute("PRAGMA synchronous = NORMAL")
        await self.conn.execute("PRAGMA busy_timeout = 5000")
        await self.conn.executescript(SCHEMA)
        await self._migrate()
        await self.conn.executescript(INDEXES)
        await self.conn.commit()

    async def _migrate(self):
        """Eski (bitta botli) bazadan o'tish: appeals jadvaliga bot_id ustunini qo'shadi."""
        cols = {r["name"] for r in await self._all("PRAGMA table_info(appeals)")}
        if "bot_id" not in cols:
            await self.conn.execute("ALTER TABLE appeals ADD COLUMN bot_id INTEGER")
        if "reject_reason" not in cols:
            await self.conn.execute("ALTER TABLE appeals ADD COLUMN reject_reason TEXT")
        if "category_id" not in cols:
            await self.conn.execute("ALTER TABLE appeals ADD COLUMN category_id INTEGER")
        if "anonymous" not in cols:
            await self.conn.execute("ALTER TABLE appeals ADD COLUMN anonymous INTEGER NOT NULL DEFAULT 1")
        bot_cols = {r["name"] for r in await self._all("PRAGMA table_info(bots)")}
        if "anonymous" not in bot_cols:
            await self.conn.execute("ALTER TABLE bots ADD COLUMN anonymous INTEGER NOT NULL DEFAULT 1")
        await self._migrate_legacy_categories()

    async def _migrate_legacy_categories(self):
        """Eng birinchi (bitta botli) versiyadagi `categories(id, name, is_active)` jadvalini yangi tuzilishga o'tkazadi.

        Eski jadval `categories_legacy` nomi bilan saqlab qo'yiladi. Murojaatlarda ishlatilgan eski kategoriyalar
        murojaat tegishli bo'lgan botga «o'chirilgan» (faqat tarix uchun) kategoriya sifatida ko'chiriladi —
        talabalarga ko'rinmaydi, lekin eski murojaatlar va hisobotlarda nomi qoladi.
        Boti noma'lum eski murojaatlarning kategoriyasi bo'shatiladi.
        """
        cols = {r["name"] for r in await self._all("PRAGMA table_info(categories)")}
        if "bot_id" in cols and "description" not in cols:  # izoh ustuni keyinroq qo'shilgan
            await self.conn.execute("ALTER TABLE categories ADD COLUMN description TEXT")
        if not cols or "bot_id" in cols:
            return
        name_col = "name" if "name" in cols else ("title" if "title" in cols else None)
        old = {r["id"]: r for r in await self._all("SELECT * FROM categories")}
        legacy = "categories_legacy"
        n = 1
        while await self._scalar("SELECT count(*) FROM sqlite_master WHERE name=?", (legacy,)):
            n += 1
            legacy = f"categories_legacy{n}"
        await self.conn.execute(f"ALTER TABLE categories RENAME TO {legacy}")
        await self.conn.executescript(SCHEMA)  # yangi `categories` jadvali yaratiladi
        used = await self._all(
            "SELECT DISTINCT bot_id, category_id FROM appeals WHERE category_id IS NOT NULL"
        )
        mapping: dict[tuple[int, int], int] = {}
        for u in used:
            bot_id, old_id = u["bot_id"], u["category_id"]
            exists = bot_id is not None and await self._scalar("SELECT count(*) FROM bots WHERE id=?", (bot_id,))
            if not exists or old_id not in old:
                await self.conn.execute(
                    "UPDATE appeals SET category_id=NULL WHERE category_id=? AND bot_id IS ?", (old_id, bot_id)
                )
                continue
            title = (old[old_id].get(name_col) if name_col else None) or f"Kategoriya #{old_id}"
            cur = await self.conn.execute(
                "INSERT INTO categories(bot_id, title, position, is_active, is_deleted, created_at) "
                "VALUES (?,?,?,0,1,?)",
                (bot_id, str(title)[:64], old_id, now()),
            )
            mapping[(bot_id, old_id)] = cur.lastrowid
        # eski va yangi ID'lar to'qnashmasligi uchun avval manfiy qiymat bilan belgilab, keyin qaytaramiz
        for (bot_id, old_id), new_id in mapping.items():
            await self.conn.execute(
                "UPDATE appeals SET category_id=? WHERE category_id=? AND bot_id=?", (-new_id, old_id, bot_id)
            )
        await self.conn.execute("UPDATE appeals SET category_id=-category_id WHERE category_id < 0")
        # eski indeks yangi jadvalga mos (appeals.category_id) — qoladi; INDEXES qolganini yaratadi

    async def close(self):
        if self.conn:
            await self.conn.close()

    # ---------- helpers ----------
    async def _one(self, sql, params=()):
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def _all(self, sql, params=()):
        async with self.conn.execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def _exec(self, sql, params=()):
        cur = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cur

    async def _scalar(self, sql, params=()):
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

    # ---------- users ----------
    async def upsert_user(self, user_id: int, full_name: str, username: str | None, bot_id: int):
        t = now()
        await self.conn.execute(
            """INSERT INTO users(user_id, full_name, username, created_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET full_name=excluded.full_name, username=excluded.username""",
            (user_id, full_name, username, t),
        )
        await self.conn.execute(
            "INSERT OR IGNORE INTO bot_users(bot_id, user_id, started_at) VALUES (?, ?, ?)",
            (bot_id, user_id, t),
        )
        await self.conn.commit()

    async def get_user(self, user_id: int):
        return await self._one("SELECT * FROM users WHERE user_id=?", (user_id,))

    async def find_user_by_username(self, username: str):
        return await self._one("SELECT * FROM users WHERE lower(username)=lower(?)", (username.lstrip("@"),))

    async def is_blocked(self, user_id: int) -> bool:
        return bool(await self._scalar("SELECT is_blocked FROM users WHERE user_id=?", (user_id,)))

    async def set_blocked(self, user_id: int, blocked: bool):
        await self._exec("UPDATE users SET is_blocked=? WHERE user_id=?", (int(blocked), user_id))

    async def blocked_users(self):
        """Bloklanganlar (anonim: faqat oxirgi murojaat raqami bilan)."""
        return await self._all(
            """SELECT u.user_id, (SELECT max(id) FROM appeals a WHERE a.user_id=u.user_id) AS last_appeal
               FROM users u WHERE u.is_blocked=1"""
        )

    async def bot_user_ids(self, bot_id: int) -> list[int]:
        rows = await self._all(
            """SELECT bu.user_id FROM bot_users bu JOIN users u ON u.user_id=bu.user_id
               WHERE bu.bot_id=? AND u.is_blocked=0""",
            (bot_id,),
        )
        return [r["user_id"] for r in rows]

    async def has_started(self, bot_id: int, user_id: int) -> bool:
        return bool(await self._scalar(
            "SELECT 1 FROM bot_users WHERE bot_id=? AND user_id=?", (bot_id, user_id)
        ))

    # ---------- bots ----------
    async def add_bot(self, tg_id: int, username: str, title: str, token_enc: str) -> int:
        cur = await self._exec(
            "INSERT INTO bots(tg_id, username, title, token_enc, added_at) VALUES (?,?,?,?,?)",
            (tg_id, username, title, token_enc, now()),
        )
        return cur.lastrowid

    async def get_bot(self, bot_id: int):
        return await self._one("SELECT * FROM bots WHERE id=?", (bot_id,))

    async def get_bot_by_tg(self, tg_id: int):
        return await self._one("SELECT * FROM bots WHERE tg_id=?", (tg_id,))

    async def bots(self, only_active=False):
        sql = """SELECT b.*,
                    (SELECT count(*) FROM bot_admins a WHERE a.bot_id=b.id) AS admins,
                    (SELECT count(*) FROM appeals ap WHERE ap.bot_id=b.id) AS appeals,
                    (SELECT count(*) FROM appeals ap WHERE ap.bot_id=b.id
                        AND ap.status IN ('new','in_progress')) AS open_appeals,
                    (SELECT count(*) FROM categories c WHERE c.bot_id=b.id AND c.is_deleted=0
                        AND c.is_active=1) AS categories
                 FROM bots b"""
        if only_active:
            sql += " WHERE b.is_active=1"
        return await self._all(sql + " ORDER BY b.id")

    async def set_bot_active(self, bot_id: int, active: bool, error: str | None = None):
        await self._exec("UPDATE bots SET is_active=?, last_error=? WHERE id=?", (int(active), error, bot_id))

    async def set_bot_anonymous(self, bot_id: int, anonymous: bool):
        await self._exec("UPDATE bots SET anonymous=? WHERE id=?", (int(anonymous), bot_id))

    async def rename_bot(self, bot_id: int, title: str):
        await self._exec("UPDATE bots SET title=? WHERE id=?", (title, bot_id))

    async def update_bot_token(self, bot_id: int, token_enc: str, username: str):
        await self._exec(
            "UPDATE bots SET token_enc=?, username=?, last_error=NULL WHERE id=?", (token_enc, username, bot_id)
        )

    async def delete_bot(self, bot_id: int):
        await self._exec("DELETE FROM bots WHERE id=?", (bot_id,))
        await self._exec("DELETE FROM bot_users WHERE bot_id=?", (bot_id,))

    # ---------- admins (har bir botga alohida) ----------
    async def add_admin(self, bot_id: int, user_id: int, full_name: str, username: str | None):
        await self._exec(
            """INSERT INTO bot_admins(bot_id, user_id, full_name, username, is_active, added_at)
               VALUES (?, ?, ?, ?, 1, ?)
               ON CONFLICT(bot_id, user_id) DO UPDATE SET full_name=excluded.full_name,
                    username=excluded.username, is_active=1""",
            (bot_id, user_id, full_name, username, now()),
        )

    async def get_admin(self, bot_id: int, user_id: int):
        return await self._one("SELECT * FROM bot_admins WHERE bot_id=? AND user_id=?", (bot_id, user_id))

    async def bot_admins(self, bot_id: int):
        return await self._all(
            """SELECT a.*,
                  (SELECT count(DISTINCT m.appeal_id) FROM appeal_messages m JOIN appeals ap ON ap.id=m.appeal_id
                    WHERE m.sender='admin' AND m.sender_id=a.user_id AND ap.bot_id=a.bot_id) AS answered
               FROM bot_admins a WHERE a.bot_id=? ORDER BY a.added_at""",
            (bot_id,),
        )

    async def admin_bots(self, user_id: int):
        return await self._all(
            """SELECT b.*, a.is_active AS admin_active FROM bot_admins a JOIN bots b ON b.id=a.bot_id
               WHERE a.user_id=? ORDER BY b.id""",
            (user_id,),
        )

    async def is_active_admin(self, bot_id: int, user_id: int) -> bool:
        return bool(await self._scalar(
            "SELECT is_active FROM bot_admins WHERE bot_id=? AND user_id=?", (bot_id, user_id)
        ))

    async def toggle_admin(self, bot_id: int, user_id: int):
        await self._exec(
            "UPDATE bot_admins SET is_active=1-is_active WHERE bot_id=? AND user_id=?", (bot_id, user_id)
        )

    async def delete_admin(self, bot_id: int, user_id: int):
        await self._exec("DELETE FROM bot_admins WHERE bot_id=? AND user_id=?", (bot_id, user_id))

    async def recipients(self, bot_id: int) -> list[int]:
        rows = await self._all("SELECT user_id FROM bot_admins WHERE bot_id=? AND is_active=1", (bot_id,))
        return [r["user_id"] for r in rows]

    async def all_admins(self):
        """Barcha botlar bo'yicha adminlar reytingi (statistika uchun)."""
        return await self._all(
            """SELECT a.user_id, max(a.full_name) AS full_name,
                  (SELECT count(DISTINCT appeal_id) FROM appeal_messages m
                    WHERE m.sender='admin' AND m.sender_id=a.user_id) AS answered
               FROM bot_admins a GROUP BY a.user_id ORDER BY answered DESC"""
        )

    # ---------- appeals ----------
    async def create_appeal(self, bot_id: int, user_id: int, category_id: int | None = None,
                            anonymous: bool = True) -> int:
        t = now()
        cur = await self._exec(
            "INSERT INTO appeals(bot_id, user_id, status, created_at, updated_at, category_id, anonymous) "
            "VALUES (?,?,?,?,?,?,?)",
            (bot_id, user_id, "new", t, t, category_id, int(anonymous)),
        )
        return cur.lastrowid

    # ---------- kategoriyalar ----------
    async def categories(self, bot_id: int, only_active=False) -> list[dict]:
        sql = """SELECT c.*,
                    (SELECT count(*) FROM appeals ap WHERE ap.category_id=c.id) AS appeals,
                    (SELECT count(*) FROM appeals ap WHERE ap.category_id=c.id
                        AND ap.status IN ('new','in_progress')) AS open_appeals
                 FROM categories c WHERE c.bot_id=? AND c.is_deleted=0"""
        if only_active:
            sql += " AND c.is_active=1"
        return await self._all(sql + " ORDER BY c.position, c.id", (bot_id,))

    async def get_category(self, cat_id: int):
        return await self._one(
            """SELECT c.*, (SELECT count(*) FROM appeals ap WHERE ap.category_id=c.id) AS appeals,
                      (SELECT count(*) FROM appeals ap WHERE ap.category_id=c.id
                          AND ap.status IN ('new','in_progress')) AS open_appeals
               FROM categories c WHERE c.id=? AND c.is_deleted=0""",
            (cat_id,),
        )

    async def add_categories(self, bot_id: int, titles: list[str]) -> list[str]:
        """Bir nechta kategoriyani qo'shadi; mavjudlari (nomi bir xil) takrorlanmaydi. Qo'shilganlarini qaytaradi."""
        existing = {c["title"].casefold() for c in await self.categories(bot_id)}
        pos = await self._scalar("SELECT coalesce(max(position), 0) FROM categories WHERE bot_id=?", (bot_id,))
        added = []
        for t in titles:
            if t.casefold() in existing:
                continue
            pos += 1
            await self.conn.execute(
                "INSERT INTO categories(bot_id, title, position, created_at) VALUES (?,?,?,?)", (bot_id, t, pos, now())
            )
            existing.add(t.casefold())
            added.append(t)
        await self.conn.commit()
        return added

    async def rename_category(self, cat_id: int, title: str):
        await self._exec("UPDATE categories SET title=? WHERE id=?", (title, cat_id))

    async def set_category_description(self, cat_id: int, description: str | None):
        await self._exec("UPDATE categories SET description=? WHERE id=?", (description or None, cat_id))

    async def toggle_category(self, cat_id: int):
        await self._exec("UPDATE categories SET is_active=1-is_active WHERE id=?", (cat_id,))

    async def delete_category(self, cat_id: int):
        """Murojaatlari bo'lsa — yashirin o'chiriladi (tarix va hisobotlarda nomi qoladi), aks holda butunlay."""
        used = await self._scalar("SELECT count(*) FROM appeals WHERE category_id=?", (cat_id,))
        if used:
            await self._exec("UPDATE categories SET is_deleted=1, is_active=0 WHERE id=?", (cat_id,))
        else:
            await self._exec("DELETE FROM categories WHERE id=?", (cat_id,))

    async def move_category(self, cat_id: int, delta: int):
        """Tartibini bir pog'ona yuqoriga (-1) yoki pastga (+1) suradi."""
        cat = await self.get_category(cat_id)
        if not cat:
            return
        cats = await self.categories(cat["bot_id"])
        ids = [c["id"] for c in cats]
        i = ids.index(cat_id)
        j = i + delta
        if not 0 <= j < len(ids):
            return
        ids[i], ids[j] = ids[j], ids[i]
        for pos, cid in enumerate(ids, start=1):
            await self.conn.execute("UPDATE categories SET position=? WHERE id=?", (pos, cid))
        await self.conn.commit()

    async def category_stats(self, bot_id: int) -> list[dict]:
        """Kategoriyalar kesimida holatlar (o'chirilganlari va «kategoriyasiz» ham)."""
        return await self._all(
            """SELECT c.title AS title, c.is_deleted AS is_deleted, count(ap.id) AS total,
                      sum(ap.status IN ('new','in_progress')) AS open,
                      sum(ap.status IN ('answered','closed')) AS done,
                      sum(ap.status = 'rejected') AS rejected
               FROM appeals ap LEFT JOIN categories c ON c.id = ap.category_id
               WHERE ap.bot_id=? GROUP BY ap.category_id ORDER BY total DESC""",
            (bot_id,),
        )

    async def get_appeal(self, appeal_id: int):
        return await self._one(_APPEAL_SELECT + " WHERE ap.id=?", (appeal_id,))

    async def set_appeal_status(self, appeal_id: int, status: str, admin_id: int | None = None):
        if admin_id is not None:
            await self._exec(
                "UPDATE appeals SET status=?, admin_id=?, updated_at=? WHERE id=?",
                (status, admin_id, now(), appeal_id),
            )
        else:
            await self._exec("UPDATE appeals SET status=?, updated_at=? WHERE id=?", (status, now(), appeal_id))

    async def transition(self, appeal_id: int, allowed_from: list[str], to: str, admin_id: int,
                         reject_reason: str | None = None) -> bool:
        """Holatni ATOMAR o'zgartiradi: faqat joriy holat allowed_from ichida bo'lsa.
        Ikki admin bir vaqtda bossa — faqat bittasi muvaffaqiyatli bo'ladi."""
        cur = await self._exec(
            f"""UPDATE appeals SET status=?, admin_id=?, updated_at=?, reject_reason=?
                WHERE id=? AND status IN ({','.join('?' * len(allowed_from))})""",
            (to, admin_id, now(), reject_reason, appeal_id, *allowed_from),
        )
        if cur.rowcount == 1:
            await self._exec(
                "INSERT INTO appeal_events(appeal_id, action, admin_id, at) VALUES (?,?,?,?)",
                (appeal_id, to, admin_id, now()),
            )
            return True
        return False

    # ---------- hisobot ma'lumotlari ----------
    async def report_data(self, start: str, end: str, bot_id: int | None) -> dict:
        """Davr ichida kelgan murojaatlar, ularning xabarlari va amallari (bot_id=None — barcha botlar)."""
        where = " WHERE ap.created_at >= ? AND ap.created_at < ?"
        params: list = [start, end]
        if bot_id is not None:
            where += " AND ap.bot_id = ?"
            params.append(bot_id)
        appeals = await self._all(_APPEAL_SELECT + where + " ORDER BY ap.id", params)
        ids = [a["id"] for a in appeals]
        msgs, events, names = [], [], {}
        if ids:
            ph = ",".join("?" * len(ids))
            msgs = await self._all(f"SELECT * FROM appeal_messages WHERE appeal_id IN ({ph}) ORDER BY id", ids)
            events = await self._all(f"SELECT * FROM appeal_events WHERE appeal_id IN ({ph}) ORDER BY id", ids)
            people = {m["sender_id"] for m in msgs if m["sender"] == "admin"} | {e["admin_id"] for e in events if e["admin_id"]}
            if people:
                ph2 = ",".join("?" * len(people))
                rows = await self._all(f"SELECT user_id, full_name FROM users WHERE user_id IN ({ph2})", list(people))
                names = {r["user_id"]: r["full_name"] for r in rows}
        # kategoriyalar: davrda murojaat bo'lmaganlari ham hisobotda 0 bilan ko'rinsin
        cat_sql = """SELECT c.id, c.title, c.is_deleted, c.position, b.title AS bot_title
                     FROM categories c JOIN bots b ON b.id = c.bot_id WHERE c.is_deleted = 0"""
        cat_params: list = []
        if bot_id is not None:
            cat_sql += " AND c.bot_id = ?"
            cat_params.append(bot_id)
        categories = await self._all(cat_sql + " ORDER BY b.id, c.position, c.id", cat_params)
        return {"appeals": appeals, "messages": msgs, "events": events, "names": names, "categories": categories}

    # ---------- kartalar ----------
    async def add_card(self, appeal_id: int, chat_id: int, message_id: int):
        await self._exec(
            "INSERT OR IGNORE INTO appeal_cards(appeal_id, chat_id, message_id) VALUES (?,?,?)",
            (appeal_id, chat_id, message_id),
        )
        # bitta chatda eng ko'pi bilan 3 ta karta saqlanadi (eskilari yangilanmaydi)
        await self._exec(
            """DELETE FROM appeal_cards WHERE appeal_id=? AND chat_id=? AND message_id NOT IN (
                 SELECT message_id FROM appeal_cards WHERE appeal_id=? AND chat_id=?
                 ORDER BY message_id DESC LIMIT 3)""",
            (appeal_id, chat_id, appeal_id, chat_id),
        )

    async def cards(self, appeal_id: int):
        return await self._all("SELECT * FROM appeal_cards WHERE appeal_id=?", (appeal_id,))

    async def delete_card(self, appeal_id: int, chat_id: int, message_id: int):
        await self._exec(
            "DELETE FROM appeal_cards WHERE appeal_id=? AND chat_id=? AND message_id=?",
            (appeal_id, chat_id, message_id),
        )

    async def user_appeals(self, bot_id: int, user_id: int, limit=10):
        return await self._all(
            _APPEAL_SELECT + " WHERE ap.bot_id=? AND ap.user_id=? ORDER BY ap.id DESC LIMIT ?",
            (bot_id, user_id, limit),
        )

    def _filter(self, statuses, bot_id):
        where, params = " WHERE 1=1", []
        if statuses:
            where += f" AND ap.status IN ({','.join('?' * len(statuses))})"
            params += statuses
        if bot_id != "any":
            where += " AND ap.bot_id=?"
            params.append(bot_id)
        return where, params

    async def list_appeals(self, statuses=None, bot_id="any", limit=20, offset=0, oldest_first=False):
        where, params = self._filter(statuses, bot_id)
        order = " ORDER BY ap.id ASC" if oldest_first else " ORDER BY ap.id DESC"
        return await self._all(_APPEAL_SELECT + where + order + " LIMIT ? OFFSET ?", params + [limit, offset])

    async def open_queue(self, bot_id: int, limit=40):
        """Ochiq murojaatlar navbati: avval yangilar, keyin qabul qilinganlar; eng eskisi birinchi."""
        return await self._all(
            _APPEAL_SELECT + """ WHERE ap.bot_id=? AND ap.status IN ('new','in_progress')
               ORDER BY CASE ap.status WHEN 'new' THEN 0 ELSE 1 END, ap.id ASC LIMIT ?""",
            (bot_id, limit),
        )

    async def count_appeals(self, statuses=None, bot_id="any") -> int:
        where, params = self._filter(statuses, bot_id)
        return await self._scalar("SELECT count(*) FROM appeals ap" + where, params)

    async def add_message(self, appeal_id: int, sender: str, sender_id: int, content: dict):
        await self._exec(
            """INSERT INTO appeal_messages(appeal_id, sender, sender_id, content_type, file_id, text, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (appeal_id, sender, sender_id, content["type"], content.get("file_id"), content.get("text"), now()),
        )

    async def appeal_messages(self, appeal_id: int):
        return await self._all("SELECT * FROM appeal_messages WHERE appeal_id=? ORDER BY id", (appeal_id,))

    # ---------- stats ----------
    async def stats(self, bot_id="any") -> dict:
        where, params = self._filter(None, bot_id)
        s = {
            "users": await self._scalar("SELECT count(*) FROM users"),
            "blocked": await self._scalar("SELECT count(*) FROM users WHERE is_blocked=1"),
            "bots": await self._scalar("SELECT count(*) FROM bots"),
            "active_bots": await self._scalar("SELECT count(*) FROM bots WHERE is_active=1"),
            "admins": await self._scalar("SELECT count(DISTINCT user_id) FROM bot_admins"),
            "total": await self._scalar("SELECT count(*) FROM appeals ap" + where, params),
            "today": await self._scalar(
                "SELECT count(*) FROM appeals ap" + where + " AND date(ap.created_at)=date('now','localtime')", params
            ),
        }
        for st in STATUSES:
            s[st] = await self._scalar("SELECT count(*) FROM appeals ap" + where + " AND ap.status=?", params + [st])
        if bot_id != "any":
            s["bot_users"] = await self._scalar("SELECT count(*) FROM bot_users WHERE bot_id=?", (bot_id,))
        return s

    async def admin_stats(self, admin_id: int, bot_id: int) -> dict:
        return {
            "answered": await self._scalar(
                """SELECT count(DISTINCT m.appeal_id) FROM appeal_messages m JOIN appeals ap ON ap.id=m.appeal_id
                   WHERE m.sender='admin' AND m.sender_id=? AND ap.bot_id=?""",
                (admin_id, bot_id),
            ),
            "replies": await self._scalar(
                """SELECT count(*) FROM appeal_messages m JOIN appeals ap ON ap.id=m.appeal_id
                   WHERE m.sender='admin' AND m.sender_id=? AND ap.bot_id=?""",
                (admin_id, bot_id),
            ),
            "closed": await self._scalar(
                "SELECT count(*) FROM appeals WHERE status='closed' AND admin_id=? AND bot_id=?", (admin_id, bot_id)
            ),
            "rejected": await self._scalar(
                "SELECT count(*) FROM appeals WHERE status='rejected' AND admin_id=? AND bot_id=?", (admin_id, bot_id)
            ),
            "in_work": await self._scalar(
                "SELECT count(*) FROM appeals WHERE status='in_progress' AND admin_id=? AND bot_id=?", (admin_id, bot_id)
            ),
        }

    # ---------- premium emoji / sozlamalar ----------
    async def custom_emojis(self) -> dict[str, tuple[str, str]]:
        rows = await self._all("SELECT * FROM custom_emojis")
        return {r["key"]: (r["emoji_id"], r["alt"]) for r in rows}

    async def set_custom_emoji(self, key: str, emoji_id: str, alt: str):
        await self._exec(
            "INSERT INTO custom_emojis(key, emoji_id, alt) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET emoji_id=excluded.emoji_id, alt=excluded.alt",
            (key, emoji_id, alt),
        )

    async def delete_custom_emoji(self, key: str):
        await self._exec("DELETE FROM custom_emojis WHERE key=?", (key,))

    async def clear_custom_emojis(self):
        await self._exec("DELETE FROM custom_emojis")

    async def get_setting(self, key: str, default=None):
        v = await self._scalar("SELECT value FROM settings WHERE key=?", (key,))
        return default if v is None else v

    async def set_setting(self, key: str, value: str):
        await self._exec(
            "INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
