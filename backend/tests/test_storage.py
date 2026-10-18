import json

import pytest

import storage

LEGACY_CSV = """Date,Asset,Direction,Entry,SL,TPs,SLs,Position_Size,Confirmations,Thesis,Status,Exit_Price,P&L,Hold_Time,TP_Hit,TP_Price,SL_Hit,SL_Price,Hit_TPs,Margin,Leverage
2026-09-01 10:00:00,BTC,long,100.0,95.0,"[{""price"": 110, ""allocation"": 1.0}]",[],2000.0,,breakout,Closed,110.0,200.0,5.0h,True,110.0,False,,[0],200.0,10
2026-09-02 10:00:00,ETH,short,50.0,0.0,[],[],500.0,,,Open,,0.0,,False,,False,,[],50.0,10
"""


def _write_legacy_files(tmp_path):
    (tmp_path / "trades.csv").write_text(LEGACY_CSV)
    (tmp_path / "portfolio_config.json").write_text(json.dumps({"portfolio_size": 1234.5}))
    (tmp_path / "mode_config.json").write_text(json.dumps({"mode": "planning"}))


class TestLegacyImport:
    def test_imports_csv_and_json_on_first_open(self, data_dir):
        _write_legacy_files(data_dir)

        df = storage.load_trades("live")

        assert list(df["Asset"]) == ["BTC", "ETH"]
        btc = df.iloc[0]
        assert btc["P&L"] == pytest.approx(200)
        assert btc["TP_Hit"]
        assert not df.iloc[1]["TP_Hit"]
        assert json.loads(btc["TPs"]) == [{"price": 110, "allocation": 1.0}]
        assert storage.load_portfolio_size("live") == pytest.approx(1234.5)
        assert storage.load_mode() == "paper"
        assert storage.load_trades("paper").empty

    def test_leaves_source_files_untouched(self, data_dir):
        _write_legacy_files(data_dir)

        storage.load_trades("live")

        assert (data_dir / "trades.csv").read_text() == LEGACY_CSV

    def test_runs_only_once(self, data_dir):
        _write_legacy_files(data_dir)
        storage.load_trades("live")

        storage.clear_trades("live")

        assert storage.load_trades("live").empty

    def test_fresh_install_starts_empty(self, data_dir):
        assert storage.load_trades("live").empty
        assert storage.load_portfolio_size("live") == 0
        assert storage.load_mode() == "live"


class TestTransactions:
    def test_update_and_portfolio_change_are_atomic(self, data_dir):
        storage.save_portfolio_size(1_000, "paper")

        with pytest.raises(KeyError):
            storage.update_trade(999, {"Status": "Closed"}, "paper", portfolio_delta=500)

        assert storage.load_portfolio_size("paper") == 1_000

    def test_update_returns_new_portfolio_size(self, data_dir):
        storage.save_portfolio_size(1_000, "paper")
        trade_id = storage.insert_trade({"Asset": "BTC", "Status": "Open"}, "paper")

        assert storage.update_trade(trade_id, {"Status": "Closed"}, "paper", portfolio_delta=-250) == 750

    def test_trades_are_scoped_to_their_mode(self, data_dir):
        trade_id = storage.insert_trade({"Asset": "BTC", "Status": "Open"}, "paper")

        with pytest.raises(KeyError):
            storage.update_trade(trade_id, {"Status": "Closed"}, "live")
        assert not storage.delete_trade(trade_id, "live")
        assert storage.load_trades("paper").loc[trade_id, "Status"] == "Open"


class TestApiWithStableIds:
    def test_cannot_close_a_paper_trade_from_live_mode(self, client):
        client.put("/api/portfolio?mode=live", json={"portfolio_size": 1_000})
        trade_id = client.post("/api/trades?mode=paper", json={
            "asset": "BTC", "direction": "long", "entry_price": 100, "stop_loss": 95,
            "position_size": 2_000, "take_profits": [], "stop_losses": [],
        }).json()["trade_index"]

        response = client.post("/api/trades/close?mode=live", json={"trade_index": trade_id, "exit_price": 110})

        assert response.status_code == 400
        assert client.get("/api/portfolio?mode=live").json()["portfolio_size"] == 1_000

    def test_ids_survive_deleting_earlier_trades(self, client):
        def add(asset):
            return client.post("/api/trades?mode=paper", json={
                "asset": asset, "direction": "long", "entry_price": 100, "stop_loss": 95,
                "position_size": 2_000, "take_profits": [], "stop_losses": [],
            }).json()["trade_index"]

        btc, eth = add("BTC"), add("ETH")
        client.delete(f"/api/trades/{btc}?mode=paper")

        client.post("/api/trades/close?mode=paper", json={"trade_index": eth, "exit_price": 110})

        closed = client.get("/api/trades/closed?mode=paper").json()["trades"]
        assert [(t["Asset"], t["_index"]) for t in closed] == [("ETH", eth)]

    def test_csv_import_replaces_journal(self, client, data_dir):
        client.post("/api/trades?mode=paper", json={
            "asset": "OLD", "direction": "long", "entry_price": 100, "stop_loss": 95,
            "position_size": 2_000, "take_profits": [], "stop_losses": [],
        })

        response = client.post(
            "/api/trades/import?mode=paper",
            files={"file": ("journal.csv", LEGACY_CSV, "text/csv")},
        )

        assert response.status_code == 200
        assert response.json()["total_trades"] == 2
        trades = client.get("/api/trades?mode=paper").json()["trades"]
        assert [t["Asset"] for t in trades] == ["BTC", "ETH"]
        assert trades[1]["Exit_Price"] == 0.0  # missing numeric values are sent as 0
