"""FSM holatini SQLite'da saqlash.

Bot qayta ishga tushganda (yangilash, server qayta yonishi) talabaning yarim yig'ilgan murojaati,
adminning yozayotgan javobi va boshqa amallar yo'qolmaydi.
"""
import asyncio
import json
from typing import Any, Mapping

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from bot.db import Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS fsm (
    k     TEXT PRIMARY KEY,
    state TEXT,
    data  TEXT NOT NULL DEFAULT '{}'
);
"""


def _k(key: StorageKey) -> str:
    return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.thread_id or 0}:{key.business_connection_id or ''}:{key.destiny}"


class SQLiteStorage(BaseStorage):
    def __init__(self, db: Database):
        self.db = db
        self._ready = False
        self._lock = asyncio.Lock()  # o'qish-o'zgartirish-yozish bitta qadamda bo'lsin

    async def _ensure(self):
        if not self._ready:
            await self.db.conn.executescript(SCHEMA)
            await self.db.conn.commit()
            self._ready = True

    async def _write(self, k: str, state: str | None, data: dict):
        if state is None and not data:
            await self.db.conn.execute("DELETE FROM fsm WHERE k=?", (k,))
        else:
            await self.db.conn.execute(
                "INSERT INTO fsm(k, state, data) VALUES (?,?,?) "
                "ON CONFLICT(k) DO UPDATE SET state=excluded.state, data=excluded.data",
                (k, state, json.dumps(data, ensure_ascii=False)),
            )
        await self.db.conn.commit()

    async def _read(self, k: str) -> tuple[str | None, dict]:
        await self._ensure()
        async with self.db.conn.execute("SELECT state, data FROM fsm WHERE k=?", (k,)) as cur:
            row = await cur.fetchone()
        if not row:
            return None, {}
        return row[0], json.loads(row[1] or "{}")

    async def set_state(self, key: StorageKey, state: str | State | None = None) -> None:
        k = _k(key)
        async with self._lock:
            _, data = await self._read(k)
            await self._write(k, state.state if isinstance(state, State) else state, data)

    async def get_state(self, key: StorageKey) -> str | None:
        return (await self._read(_k(key)))[0]

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        k = _k(key)
        async with self._lock:
            state, _ = await self._read(k)
            await self._write(k, state, dict(data))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        return (await self._read(_k(key)))[1]

    async def close(self) -> None:  # ulanish Database'ga tegishli — u yerda yopiladi
        pass
