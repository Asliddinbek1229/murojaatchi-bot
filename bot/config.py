"""Sozlamalar: .env faylidan o'qiladi (loyiha papkasidagi .env).

Nisbiy yo'llar (DB_PATH, LOG_FILE, BACKUP_DIR) loyiha papkasiga nisbatan olinadi —
dastur qaysi papkadan ishga tushirilishidan qat'i nazar (systemd, cron) bir xil ishlaydi.
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

_TOKEN_RE = re.compile(r"^\d+:[\w-]{10,}$")


@dataclass
class Config:
    bot_token: str
    secret_key: bytes
    superadmin_ids: set[int] = field(default_factory=set)
    db_path: str = "data/bot.db"
    log_level: str = "INFO"
    log_file: str | None = None
    backup_dir: str = "data/backups"
    backup_keep: int = 14
    backup_hour: int = 3  # har kuni shu soatda avtomatik nusxa; -1 = o'chirilgan


def _path(value: str) -> str:
    p = Path(value).expanduser()
    return str(p if p.is_absolute() else BASE_DIR / p)


def _secret_key(db_path: str) -> bytes:
    """Bo'lim botlari tokenlarini shifrlash kaliti. .env da bo'lmasa — data/ ichida avtomatik yaratiladi."""
    env = os.getenv("SECRET_KEY", "").strip()
    key = env.encode() if env else None
    if not key:
        path = Path(db_path).parent / ".secret.key"
        if path.exists():
            key = path.read_bytes().strip()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            key = Fernet.generate_key()
            path.write_bytes(key)
            try:
                path.chmod(0o600)  # faqat egasi o'qiy oladi (Linux)
            except OSError:
                pass
    try:
        Fernet(key)
    except Exception:
        raise RuntimeError("SECRET_KEY noto'g'ri: Fernet kaliti (44 belgili base64) bo'lishi kerak")
    return key


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN .env faylida ko'rsatilmagan")
    if not _TOKEN_RE.match(token):
        raise RuntimeError("BOT_TOKEN formati noto'g'ri (123456789:AA... ko'rinishida bo'lishi kerak)")
    raw_ids = [x for x in os.getenv("SUPERADMIN_IDS", "").replace(" ", "").split(",") if x]
    bad = [x for x in raw_ids if not x.lstrip("-").isdigit()]
    if bad:
        raise RuntimeError(f"SUPERADMIN_IDS da noto'g'ri qiymat: {', '.join(bad)} (faqat raqamli ID, vergul bilan)")
    ids = {int(x) for x in raw_ids}
    if not ids:
        raise RuntimeError("SUPERADMIN_IDS .env faylida ko'rsatilmagan")
    db_path = _path(os.getenv("DB_PATH", "data/bot.db"))
    log_file = os.getenv("LOG_FILE", "").strip()
    try:
        keep = max(1, int(os.getenv("BACKUP_KEEP", "14")))
        hour = int(os.getenv("BACKUP_HOUR", "3"))
    except ValueError:
        raise RuntimeError("BACKUP_KEEP va BACKUP_HOUR butun son bo'lishi kerak")
    if not -1 <= hour <= 23:
        raise RuntimeError("BACKUP_HOUR 0..23 oralig'ida (yoki -1 — o'chirish) bo'lishi kerak")
    return Config(
        bot_token=token,
        secret_key=_secret_key(db_path),
        superadmin_ids=ids,
        db_path=db_path,
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        log_file=_path(log_file) if log_file else None,
        backup_dir=_path(os.getenv("BACKUP_DIR", "data/backups")),
        backup_keep=keep,
        backup_hour=hour,
    )


config = load_config()
