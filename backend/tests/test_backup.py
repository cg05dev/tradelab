"""Database backups (backup.py) and the SQLite settings that let several threads write."""

import os
import sqlite3
import time

import pytest

import backup
import storage


def _trade(asset="BTC-USDC"):
    return storage.insert_trade({"Date": "2026-11-27 10:00:00", "Asset": asset, "Direction": "long", "Entry": 100.0,
                                 "Position_Size": 1_000.0, "Status": "Open"}, "paper")


def _age(path, hours):
    stamp = time.time() - hours * 3600
    os.utime(path, (stamp, stamp))


@pytest.fixture
def backups(data_dir, monkeypatch):
    monkeypatch.delenv("TRADELAB_BACKUP_DIR", raising=False)
    return data_dir / "backups"


class TestCreateBackup:
    def test_copies_the_journal(self, backups):
        _trade()

        path = backup.create_backup(storage.DB_FILE)

        assert os.path.dirname(path) == str(backups)
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT asset FROM trades").fetchall() == [("BTC-USDC",)]

    def test_a_copy_includes_writes_still_in_the_write_ahead_log(self, backups):
        _trade()
        with storage._connect() as conn:  # an open reader keeps SQLite from checkpointing the log
            _trade("ETH-USDC")
            path = backup.create_backup(storage.DB_FILE)
            conn.execute("SELECT 1")

        with sqlite3.connect(path) as copy:
            assert copy.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 2

    def test_keeps_only_the_newest(self, backups):
        _trade()
        older = [backup.create_backup(storage.DB_FILE, keep=100) for _ in range(5)]
        for hours, path in enumerate(older):
            _age(path, 5 - hours)  # oldest first

        newest = backup.create_backup(storage.DB_FILE, keep=3)

        assert backup.list_backups(storage.DB_FILE) == [*older[-2:], newest]

    def test_names_never_collide(self, backups):
        _trade()

        paths = {backup.create_backup(storage.DB_FILE) for _ in range(3)}

        assert len(paths) == 3

    def test_nothing_to_back_up_without_a_database(self, backups):
        assert backup.create_backup(storage.DB_FILE) is None
        assert not backups.exists()

    def test_a_damaged_copy_is_discarded(self, backups, monkeypatch):
        _trade()
        good = backup.create_backup(storage.DB_FILE)

        monkeypatch.setattr(backup, "_integrity_check", lambda conn: "*** in database main *** Page 3 is never used")

        with pytest.raises(sqlite3.DatabaseError, match="integrity"):
            backup.create_backup(storage.DB_FILE)

        assert backup.list_backups(storage.DB_FILE) == [good]
        assert not [name for name in os.listdir(backups) if name.endswith(".partial")]

    def test_the_folder_can_be_configured(self, data_dir, monkeypatch):
        monkeypatch.setenv("TRADELAB_BACKUP_DIR", str(data_dir / "elsewhere"))
        _trade()

        assert os.path.dirname(backup.create_backup(storage.DB_FILE)) == str(data_dir / "elsewhere")


class TestBackUpIfDue:
    def test_backs_up_when_there_is_no_backup_yet(self, backups):
        _trade()

        assert backup.back_up_if_due(storage.DB_FILE, every_hours=24)

    def test_skips_while_the_newest_is_recent(self, backups):
        _trade()
        _age(backup.create_backup(storage.DB_FILE), hours=23)

        assert backup.back_up_if_due(storage.DB_FILE, every_hours=24) is None
        assert len(backup.list_backups(storage.DB_FILE)) == 1

    def test_backs_up_once_the_newest_is_old_enough(self, backups):
        _trade()
        _age(backup.create_backup(storage.DB_FILE), hours=25)

        assert backup.back_up_if_due(storage.DB_FILE, every_hours=24)
        assert len(backup.list_backups(storage.DB_FILE)) == 2


class TestMigrations:
    def test_a_migration_backs_up_the_database_first(self, backups):
        trade_id = _trade()
        with sqlite3.connect(storage.DB_FILE) as conn:  # an install from before closed_at existed
            conn.execute("ALTER TABLE trades DROP COLUMN closed_at")

        storage.load_trades("paper")

        [copy] = backup.list_backups(storage.DB_FILE)
        assert copy.endswith("-before-migration.db")
        with sqlite3.connect(copy) as conn:
            assert "closed_at" not in {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
            assert conn.execute("SELECT id FROM trades").fetchall() == [(trade_id,)]

    def test_no_backup_when_nothing_is_migrated(self, backups):
        _trade()
        storage.load_trades("paper")

        assert backup.list_backups(storage.DB_FILE) == []


def test_the_database_uses_write_ahead_logging(data_dir):
    _trade()

    with sqlite3.connect(storage.DB_FILE) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
