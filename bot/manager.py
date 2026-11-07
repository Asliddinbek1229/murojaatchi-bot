"""Bir nechta botni bitta jarayonda yurgizish: asosiy bot + bo'lim botlari.

Har bir bot uchun alohida long-polling vazifasi ishlaydi; hammasi bitta Dispatcher'ga
yangilanish uzatadi. Bot qo'shish/to'xtatish dastur ishlab turganda bajariladi.
"""
import asyncio
import logging
import time
import traceback

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramConflictError, TelegramUnauthorizedError
from aiogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, User
from aiogram.utils.token import TokenValidationError, validate_token
from cryptography.fernet import Fernet

from bot.config import config
from bot.db import Database, now
from bot.ui import R
from bot.utils import esc

log = logging.getLogger(__name__)

_fernet = Fernet(config.secret_key)


def encrypt(token: str) -> str:
    return _fernet.encrypt(token.encode()).decode()


def decrypt(token_enc: str) -> str:
    return _fernet.decrypt(token_enc.encode()).decode()


def make_bot(token: str) -> Bot:
    return Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


class TokenError(Exception):
    pass


class BotManager:
    def __init__(self, dp: Dispatcher, db: Database, main_bot: Bot):
        self.dp = dp
        self.db = db
        self.main_bot = main_bot
        self.bots: dict[int, Bot] = {}          # bots.id -> Bot
        self.by_tg: dict[int, dict] = {}        # telegram bot id -> bots jadvalidagi yozuv
        self.tasks: dict[int, asyncio.Task] = {}
        self._main_task: asyncio.Task | None = None
        self.main_username: str = ""
        self._inflight: set[asyncio.Task] = set()   # qayta ishlanayotgan update'lar (to'xtashda kutiladi)
        self._err_last: dict[str, float] = {}       # xato turi -> oxirgi xabar vaqti (spamga qarshi)

    # ---------- kontekst ----------
    def record_for(self, bot: Bot) -> dict | None:
        """Bo'lim boti yozuvi; asosiy bot uchun None."""
        return self.by_tg.get(bot.id)

    def get(self, bot_id: int) -> Bot | None:
        return self.bots.get(bot_id)

    def is_running(self, bot_id: int) -> bool:
        t = self.tasks.get(bot_id)
        return bool(t and not t.done())

    # ---------- superadminga xabar ----------
    async def _notify_via(self, bot: Bot, text: str, markup=None):
        """Berilgan bot orqali barcha superadminlarga xabar (parallel, 10 s dan oshmaydi).
        Superadmin bu botni hali ochmagan bo'lsa — jim o'tkazib yuboriladi."""
        async def one(uid: int):
            try:
                await bot.send_message(uid, text, reply_markup=markup)
            except Exception:
                pass
        try:
            await asyncio.wait_for(
                asyncio.gather(*(one(uid) for uid in config.superadmin_ids)), timeout=10
            )
        except asyncio.TimeoutError:
            log.warning("Superadminga xabar yuborish vaqti tugadi")

    # ---------- ishga tushirish ----------
    async def start_all(self):
        me = await self.main_bot.get_me()
        self.main_username = me.username
        await self.main_bot.delete_webhook(drop_pending_updates=False)  # to'xtab turgan paytdagi xabarlar ham qayta ishlanadi
        self._main_task = asyncio.create_task(self._poll(self.main_bot, None), name="poll-main")

        # oldingi safar to'g'ri to'xtaganmi? (elektr, xato, majburan o'chirish bo'lsa — yo'q)
        unclean = (await self.db.get_setting("clean_shutdown", "1")) == "0"
        await self.db.set_setting("clean_shutdown", "0")

        ok, failed = [], []
        for rec in await self.db.bots(only_active=True):
            try:
                await self.start(rec)
                ok.append(rec)
            except Exception as ex:  # bitta bot xatosi boshqalarini to'xtatmasin
                log.error("@%s ishga tushmadi: %s", rec["username"], ex)
                await self.db.set_bot_active(rec["id"], False, str(ex)[:200])
                failed.append((rec, str(ex)))
        stopped = [b for b in await self.db.bots() if not b["is_active"] and b["id"] not in {r["id"] for r, _ in failed}]
        await self._notify_via(self.main_bot, self._startup_report(ok, failed, stopped, unclean))

    def _startup_report(self, ok: list, failed: list, stopped: list, unclean: bool) -> str:
        lines = [f"[[active]] {esc(r['title'])} — @{esc(r['username'])}" for r in ok]
        lines += [f"[[inactive]] {esc(r['title'])} — ishga tushmadi: <i>{esc(err[:120])}</i>" for r, err in failed]
        lines += [f"[[st_closed]] {esc(r['title'])} — o'chirib qo'yilgan" for r in stopped]
        bots_block = "\n".join(lines) or "Bo'lim botlari hali qo'shilmagan."
        text = (
            f"[[active]] <b>Tizim ishga tushdi</b> · {now()[:16]}\n\n"
            f"<blockquote>[[panel]] Asosiy bot: @{esc(self.main_username)}\n"
            f"[[robot]] Bo'lim botlari: <b>{len(ok)}</b> ta ishlayapti"
            + (f", <b>{len(failed)}</b> ta xato" if failed else "") + "</blockquote>\n"
            f"<blockquote expandable>{bots_block}</blockquote>"
        )
        if unclean:
            text += (
                "\n\n[[warn]] <b>Diqqat:</b> oldingi safar tizim <b>kutilmaganda</b> to'xtagan "
                "(server o'chgan, internet uzilgan yoki dastur majburan yopilgan). "
                "O'sha paytda kelgan xabarlar Telegram'da saqlanib turadi va hozir qayta ishlanadi."
            )
        return R(text)

    async def start(self, rec: dict, notify: bool = True):
        await self.stop(rec["id"])  # qayta ishga tushirish bo'lsa — jim to'xtatamiz
        bot = make_bot(decrypt(rec["token_enc"]))
        await bot.delete_webhook(drop_pending_updates=False)  # to'xtab turgan paytdagi xabarlar yo'qolmasin
        self.bots[rec["id"]] = bot
        self.by_tg[bot.id] = rec
        self.tasks[rec["id"]] = asyncio.create_task(self._poll(bot, rec["id"]), name=f"poll-{rec['username']}")
        log.info("Bo'lim boti ishga tushdi: @%s (%s)", rec["username"], rec["title"])
        if notify:
            await self._notify_via(bot, R(
                f"[[active]] <b>{esc(rec['title'])}</b> boti ishga tushdi · {now()[:16]}\n"
                "<blockquote>Murojaatlar qabul qilinmoqda.</blockquote>"
            ))

    async def stop(self, bot_id: int, reason: str | None = None):
        """Bo'lim botini to'xtatadi. reason berilsa — bot o'zi orqali superadminga xabar beradi."""
        task = self.tasks.pop(bot_id, None)
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        bot = self.bots.pop(bot_id, None)
        if bot:
            rec = self.by_tg.pop(bot.id, None)
            if reason and rec:
                await self._notify_via(bot, R(
                    f"[[inactive]] <b>{esc(rec['title'])}</b> boti to'xtadi · {now()[:16]}\n"
                    f"<blockquote>Sabab: {esc(reason)}\n"
                    "To'xtab turgan paytda talabalar yozgan xabarlar yo'qolmaydi — "
                    "bot qayta ishga tushganda qabul qilinadi.</blockquote>"
                ))
            await bot.session.close()

    async def refresh_record(self, bot_id: int):
        """Nom o'zgarganda xotiradagi yozuvni yangilash."""
        rec = await self.db.get_bot(bot_id)
        bot = self.bots.get(bot_id)
        if rec and bot:
            self.by_tg[bot.id] = rec

    async def shutdown(self):
        """To'g'ri to'xtatish: har bir bo'lim boti va asosiy bot superadminga xabar beradi."""
        count = len(self.tasks)
        # 1) yangi update olishni to'xtatamiz (sessiyalar hali ochiq)
        polls = [t for t in [self._main_task, *self.tasks.values()] if t]
        for t in polls:
            t.cancel()
        await asyncio.gather(*polls, return_exceptions=True)
        # 2) boshlangan ishlarni (javob yuborish, saqlash) tugatib olamiz
        if self._inflight:
            log.info("%d ta boshlangan ish tugashi kutilmoqda...", len(self._inflight))
            await asyncio.wait(list(self._inflight), timeout=15)
        # 3) har bir bot o'zi orqali «to'xtadi» deb xabar beradi
        await asyncio.gather(*(self.stop(bid, reason="tizim to'xtatildi") for bid in list(self.tasks)))
        if self._main_task:
            self._main_task.cancel()
        await self._notify_via(self.main_bot, R(
            f"[[inactive]] <b>Tizim to'xtatildi</b> · {now()[:16]}\n\n"
            f"<blockquote>Asosiy bot va {count} ta bo'lim boti ishlamayapti.\n"
            "Bu vaqtda yozilgan xabarlar yo'qolmaydi — tizim qayta ishga tushganda qabul qilinadi.\n"
            "Ishga tushishi bilan xabar beraman.</blockquote>"
        ))
        await self.db.set_setting("clean_shutdown", "1")
        await self.main_bot.session.close()

    def wait_task(self) -> asyncio.Task:
        return self._main_task

    # ---------- polling ----------
    async def _poll(self, bot: Bot, bot_id: int | None):
        allowed = self.dp.resolve_used_update_types()
        offset = None
        name = "asosiy" if bot_id is None else f"#{bot_id}"
        delay = 1
        while True:
            try:
                updates = await bot.get_updates(offset=offset, timeout=25, allowed_updates=allowed)
                delay = 1
            except asyncio.CancelledError:
                raise
            except TelegramUnauthorizedError as ex:
                log.error("Bot %s tokeni yaroqsiz: %s", name, ex)
                if bot_id is not None:
                    await self._on_token_revoked(bot_id, str(ex))
                return
            except TelegramConflictError:
                log.warning("Bot %s boshqa joyda ham ishlayapti (conflict), 5 s kutamiz", name)
                await asyncio.sleep(5)
                continue
            except Exception as ex:  # internet uzilishi, Telegram 5xx — kutib qayta urinamiz
                log.warning("Bot %s polling xatosi: %s (%d s dan keyin qayta)", name, ex, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            for upd in updates:
                offset = upd.update_id + 1
                task = asyncio.create_task(self._feed(bot, upd))
                self._inflight.add(task)
                task.add_done_callback(self._inflight.discard)

    async def _feed(self, bot: Bot, upd):
        try:
            await self.dp.feed_update(bot, upd)
        except Exception as ex:
            log.exception("Update qayta ishlashda xato")
            await self._report_error(bot, ex)

    async def _report_error(self, bot: Bot, ex: Exception):
        """Kutilmagan xato haqida superadminga qisqa xabar (bir xil xato 10 daqiqada 1 marta)."""
        key = f"{type(ex).__name__}:{str(ex)[:80]}"
        t = time.monotonic()
        if t - self._err_last.get(key, -1e9) < 600:
            return
        self._err_last[key] = t
        rec = self.by_tg.get(bot.id)
        where = f"@{rec['username']}" if rec else f"@{self.main_username} (asosiy)"
        tb = "".join(traceback.format_exception(type(ex), ex, ex.__traceback__)[-3:])[-1500:]
        try:
            await self._notify_via(self.main_bot, R(
                f"[[warn]] <b>Botda xato</b> · {esc(where)} · {now()[:16]}\n"
                f"<blockquote expandable><code>{esc(tb)}</code></blockquote>\n"
                "Foydalanuvchi amali bajarilmagan bo'lishi mumkin. Batafsil: server loglari."
            ))
        except Exception:
            pass

    async def _on_token_revoked(self, bot_id: int, error: str):
        rec = await self.db.get_bot(bot_id)
        await self.db.set_bot_active(bot_id, False, "Token yaroqsiz: " + error[:150])
        bot = self.bots.pop(bot_id, None)
        self.tasks.pop(bot_id, None)
        if bot:
            self.by_tg.pop(bot.id, None)
            await bot.session.close()
        await self.notify_superadmins(
            f"⚠️ <b>@{rec['username'] if rec else bot_id}</b> boti to'xtadi: token yaroqsiz "
            "(BotFather'da o'zgartirilgan yoki bot o'chirilgan bo'lishi mumkin).\n"
            "Asosiy bot → Bo'lim botlari → bot → «Tokenni almashtirish»."
        )

    async def notify_superadmins(self, text: str, markup=None):
        for uid in config.superadmin_ids:
            try:
                await self.main_bot.send_message(uid, text, reply_markup=markup)
            except TelegramAPIError:
                pass

    # ---------- token tekshirish / yangi bot ----------
    async def check_token(self, token: str, exclude_bot_id: int | None = None) -> User:
        token = token.strip()
        try:
            validate_token(token)
        except TokenValidationError:
            raise TokenError("Token formati noto'g'ri. U «123456789:AA...» ko'rinishida bo'ladi.")
        probe = make_bot(token)
        try:
            me = await probe.get_me()
        except TelegramUnauthorizedError:
            raise TokenError("Telegram bu tokenni qabul qilmadi (yaroqsiz yoki bekor qilingan).")
        except TelegramAPIError as ex:
            raise TokenError(f"Telegram xatosi: {ex}")
        finally:
            await probe.session.close()
        if me.id == self.main_bot.id:
            raise TokenError("Bu asosiy botning tokeni.")
        existing = await self.db.get_bot_by_tg(me.id)
        if existing and existing["id"] != exclude_bot_id:
            raise TokenError(f"@{me.username} allaqachon qo'shilgan («{existing['title']}»).")
        return me

    async def setup_profile(self, bot_id: int):
        """Bo'lim botining tavsifi va buyruqlarini avtomatik sozlash."""
        bot, rec = self.bots.get(bot_id), await self.db.get_bot(bot_id)
        if not bot or not rec:
            return
        try:
            await bot.set_my_commands([
                BotCommand(command="start", description="Bosh menyu"),
                BotCommand(command="cancel", description="Amalni bekor qilish"),
            ])
            await bot.set_my_short_description(f"{rec['title']} — anonim murojaatlar boti")
            await bot.set_my_description(
                f"«{rec['title']}» bo'limiga anonim murojaat yuborish boti.\n\n"
                "Shikoyat, taklif yoki savolingizni matn, rasm, video yoki fayl ko'rinishida yuboring. "
                "Ismingiz va ma'lumotlaringiz hech kimga ko'rsatilmaydi.\n\nBoshlash uchun «Start» ni bosing."
            )
        except TelegramAPIError as ex:
            log.warning("@%s profilini sozlab bo'lmadi: %s", rec["username"], ex)

    def link(self, username: str, payload: str | None = None) -> str:
        return f"https://t.me/{username}" + (f"?start={payload}" if payload else "")

    def open_kb(self, username: str, text: str, payload: str | None = None) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=text, url=self.link(username, payload), style="primary")
        ]])
