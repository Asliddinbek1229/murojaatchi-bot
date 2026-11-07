"""SQLite bazaning zaxira nusxasi (bot ishlab turganda ham xavfsiz).

sqlite3 backup API ishlatiladi: WAL rejimida ham bazaning izchil (consistent) nusxasini oladi,
yozishni to'xtatmaydi. Nusxa gzip bilan siqiladi, eng oxirgi `keep` tasi saqlanadi.
"""
import gzip
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

PREFIX = "bot-"
SUFFIX = ".db.gz"


def create_backup(db_path: str, backup_dir: str, keep: int = 14) -> Path:
    src = Path(db_path)
    if not src.exists():
        raise FileNotFoundError(f"Baza topilmadi: {src}")
    out_dir = Path(backup_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    raw = out_dir / f"{PREFIX}{stamp}.db"
    final = out_dir / f"{PREFIX}{stamp}{SUFFIX}"

    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
    target = sqlite3.connect(raw)
    try:
        source.backup(target)
        target.execute("PRAGMA journal_mode = DELETE")  # nusxa bitta mustaqil fayl bo'lsin
        ok = target.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise RuntimeError(f"Nusxa butunligi tekshiruvi o'tmadi: {ok}")
    finally:
        target.close()
        source.close()

    with open(raw, "rb") as f_in, gzip.open(final, "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out)
    raw.unlink()
    try:
        final.chmod(0o600)
    except OSError:
        pass
    prune(out_dir, keep)
    return final


def prune(out_dir: Path, keep: int) -> list[Path]:
    files = sorted(out_dir.glob(f"{PREFIX}*{SUFFIX}"), key=lambda p: p.name, reverse=True)
    removed = files[keep:]
    for p in removed:
        p.unlink(missing_ok=True)
    return removed


def restore_backup(archive: str, db_path: str) -> None:
    """Zaxiradan tiklash (bot TO'XTATILGAN holatda chaqiring)."""
    dst = Path(db_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    for extra in ("-wal", "-shm"):
        Path(str(dst) + extra).unlink(missing_ok=True)
    if dst.exists():
        dst.replace(dst.with_name(dst.name + f".before-restore-{datetime.now():%Y%m%d%H%M%S}"))
    with gzip.open(archive, "rb") as f_in, open(dst, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    con = sqlite3.connect(dst)
    try:
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    if ok != "ok":
        raise RuntimeError(f"Tiklangan baza butunligi tekshiruvi o'tmadi: {ok}")
