"""Closed trades count when they closed, not when they opened (storage.closed_dates)."""

from datetime import datetime, timedelta

import pytest

import storage

NOW = datetime.now()


def _closed_trade(opened_days_ago, closed_days_ago, pnl, asset="BTC"):
    def ago(days):
        return (NOW - timedelta(days=days)).strftime(storage.TIME_FORMAT)

    return storage.insert_trade({
        "Date": ago(opened_days_ago), "Closed_At": ago(closed_days_ago), "Asset": asset, "Direction": "long",
        "Entry": 100, "Position_Size": 1_000, "Status": "Closed", "Exit_Price": 110, "P&L": pnl, "Leverage": 1,
    }, "paper")


@pytest.fixture
def journal(client):
    """A swing trade opened 40 days ago and closed yesterday, and a trade opened and closed 35 days ago."""
    _closed_trade(opened_days_ago=40, closed_days_ago=1, pnl=50, asset="SWING")
    _closed_trade(opened_days_ago=35, closed_days_ago=35, pnl=-20, asset="OLD")
    return client


def test_timeframes_count_trades_by_close_date(journal):
    week = journal.get("/api/analytics/metrics?timeframe=7d&mode=paper").json()

    assert week["trade_count"] == 1
    assert week["total_pnl"] == pytest.approx(50)


def test_pnl_series_is_ordered_by_close_date(journal):
    series = journal.get("/api/analytics/pnl-series?mode=paper").json()

    assert [p["asset"] for p in series] == ["OLD", "SWING"]
    assert [p["cumulative_pnl"] for p in series] == pytest.approx([-20, 30])


def test_closed_trades_filter_and_sort_by_close_date(journal):
    yesterday = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")

    newest_first = journal.get("/api/trades/closed?mode=paper").json()["trades"]
    on_the_day = journal.get(f"/api/trades/closed?mode=paper&start={yesterday}&end={yesterday}").json()["trades"]

    assert [t["Asset"] for t in newest_first] == ["SWING", "OLD"]
    assert [t["Asset"] for t in on_the_day] == ["SWING"]  # a date-only end includes that whole day


@pytest.mark.usefixtures("no_fees")
def test_closing_a_trade_records_when(client):
    client.put("/api/portfolio?mode=paper", json={"portfolio_size": 1_000})
    trade_id = client.post("/api/trades?mode=paper", json={
        "asset": "BTC", "direction": "long", "entry_price": 100, "stop_loss": 95,
        "position_size": 1_000, "take_profits": [], "stop_losses": [],
    }).json()["trade_index"]

    client.post("/api/trades/close?mode=paper", json={"trade_index": trade_id, "exit_price": 110})

    closed_at = datetime.strptime(storage.load_trades("paper").loc[trade_id, "Closed_At"], storage.TIME_FORMAT)
    assert abs((closed_at - datetime.now()).total_seconds()) < 60


def test_older_databases_get_close_dates_from_the_hold_time(data_dir):
    """A database from before closed_at existed: the column is added and filled from date + hold time."""
    import sqlite3

    conn = sqlite3.connect(storage.DB_FILE)
    conn.executescript(storage.SCHEMA.replace("    closed_at     TEXT     -- when the trade fully closed (local time, like date)\n", "")
                       .replace("    leverage      INTEGER,\n", "    leverage      INTEGER\n"))
    conn.execute("INSERT INTO settings (key, value) VALUES ('legacy_import_done', '1')")
    conn.execute("INSERT INTO trades (mode, date, status, hold_time) VALUES ('paper', '2026-01-01 10:00:00', 'Closed', '26.5h')")
    conn.execute("INSERT INTO trades (mode, date, status) VALUES ('paper', '2026-01-02 10:00:00', 'Open')")
    conn.commit()
    conn.close()

    trades = storage.load_trades("paper")

    assert trades["Closed_At"].iloc[0] == "2026-01-02 12:30:00"
    assert trades["Closed_At"].isna().iloc[1]
