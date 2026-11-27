"""
Copies of the SQLite database, so a bad migration, a bug or a damaged file never costs the journal.

A copy is made at most once every TRADELAB_BACKUP_HOURS (checked at startup and hourly), and before
any schema migration. The newest TRADELAB_BACKUP_KEEP copies are kept. Copies use SQLite's online
backup API, so they are consistent even while the app is writing, and each one is checked with
`PRAGMA integrity_check` before it counts.

To restore one: stop TradeLab, delete tradelab.db-wal and tradelab.db-shm if they exist, and copy the
backup over tradelab.db.
"""

import glob
import logging
import os
import sqlite3
import time
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

BACKUP_HOURS = float(os.getenv("TRADELAB_BACKUP_HOURS", "24"))
BACKUP_KEEP = int(os.getenv("TRADELAB_BACKUP_KEEP", "14"))
PREFIX = "tradelab-"


def backup_dir(db_file: str) -> str:
    """TRADELAB_BACKUP_DIR, or a `backups` folder next to the database."""
    return os.getenv("TRADELAB_BACKUP_DIR") or os.path.join(os.path.dirname(os.path.abspath(db_file)), "backups")


def list_backups(db_file: str) -> List[str]:
    """The backups of `db_file`, oldest first."""
    return sorted(glob.glob(os.path.join(backup_dir(db_file), f"{PREFIX}*.db")), key=os.path.getmtime)


def _integrity_check(conn: sqlite3.Connection) -> str:
    """SQLite's verdict on a database: "ok", or what is wrong with it."""
    return conn.execute("PRAGMA integrity_check").fetchone()[0]


def create_backup(db_file: str, label: Optional[str] = None, keep: Optional[int] = None) -> Optional[str]:
    """
    Copy `db_file` into the backup folder and return the copy's path, then delete all but the newest
    `keep` copies. Returns None if there is no database yet. Raises if the copy fails or is damaged;
    a failed copy never replaces or removes an existing one.
    """
    if not os.path.exists(db_file):
        return None
    directory = backup_dir(db_file)
    os.makedirs(directory, exist_ok=True)
    name = PREFIX + datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-{label}" if label else "")
    path = os.path.join(directory, f"{name}.db")
    suffix = 1
    while os.path.exists(path):
        suffix += 1
        path = os.path.join(directory, f"{name}-{suffix}.db")

    partial = path + ".partial"
    source = sqlite3.connect(db_file, timeout=30)
    target = sqlite3.connect(partial)
    try:
        source.backup(target)
        result = _integrity_check(target)
    finally:
        target.close()
        source.close()
    if result != "ok":
        os.remove(partial)
        raise sqlite3.DatabaseError(f"The backup of {db_file} failed its integrity check: {result}")
    os.replace(partial, path)
    logger.info(f"Backed up the database to {path}")

    for old in list_backups(db_file)[:-(keep or BACKUP_KEEP)]:
        os.remove(old)
    return path


def back_up_if_due(db_file: str, every_hours: float = BACKUP_HOURS) -> Optional[str]:
    """create_backup() if the newest backup is at least `every_hours` old (or there is none)."""
    backups = list_backups(db_file)
    if backups and time.time() - os.path.getmtime(backups[-1]) < every_hours * 3600:
        return None
    return create_backup(db_file)
