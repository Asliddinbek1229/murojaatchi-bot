"""Bazaning zaxira nusxasini olish / tiklash.

    python scripts/backup.py            # nusxa olish (data/backups/, oxirgi BACKUP_KEEP tasi saqlanadi)
    python scripts/backup.py --list     # mavjud nusxalar
    python scripts/backup.py --restore data/backups/bot-2026-01-01_03-00-00.db.gz   # tiklash (botni to'xtatib!)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.backup import PREFIX, SUFFIX, create_backup, restore_backup  # noqa: E402
from bot.config import config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Baza zaxira nusxasi")
    ap.add_argument("--list", action="store_true", help="mavjud nusxalarni ko'rsatish")
    ap.add_argument("--restore", metavar="FAYL", help="ko'rsatilgan nusxadan tiklash (bot to'xtatilgan bo'lsin)")
    args = ap.parse_args()

    if args.list:
        files = sorted(Path(config.backup_dir).glob(f"{PREFIX}*{SUFFIX}"))
        for p in files:
            print(f"{p}  {p.stat().st_size / 1024:.0f} KB")
        print(f"Jami: {len(files)} ta")
        return 0
    if args.restore:
        restore_backup(args.restore, config.db_path)
        print(f"Tiklandi: {args.restore} -> {config.db_path}")
        return 0
    path = create_backup(config.db_path, config.backup_dir, config.backup_keep)
    print(f"Nusxa olindi: {path} ({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
