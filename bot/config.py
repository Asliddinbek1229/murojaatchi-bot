import os
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    secret_key: bytes
    superadmin_ids: set[int] = field(default_factory=set)
    db_path: str = "data/bot.db"


def _secret_key(db_path: str) -> bytes:
    """Bo'lim botlari tokenlarini shifrlash kaliti. .env da bo'lmasa — data/ ichida avtomatik yaratiladi."""
    env = os.getenv("SECRET_KEY", "").strip()
    if env:
        return env.encode()
    path = Path(db_path).parent / ".secret.key"
    if path.exists():
        return path.read_bytes().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    path.write_bytes(key)
    return key


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN .env faylida ko'rsatilmagan")
    ids = {
        int(x)
        for x in os.getenv("SUPERADMIN_IDS", "").replace(" ", "").split(",")
        if x.strip().lstrip("-").isdigit()
    }
    if not ids:
        raise RuntimeError("SUPERADMIN_IDS .env faylida ko'rsatilmagan")
    db_path = os.getenv("DB_PATH", "data/bot.db")
    return Config(bot_token=token, secret_key=_secret_key(db_path), superadmin_ids=ids, db_path=db_path)


config = load_config()
