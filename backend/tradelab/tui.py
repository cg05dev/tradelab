"""TradeLab Terminal User Interface."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button, DataTable, Footer, Header, Input, Label, Select, Static, TabbedContent, TabPane,
)
from textual.widget import Widget
import json

from tradelab import core


class PortfolioBar(Widget):
    """Slim header bar with portfolio, mode, and stats."""

    DEFAULT_CSS = """
    PortfolioBar {
        dock: top;
        height: 1;
        padding: 0 1;
        background: $primary 10%;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._mode = core.load_mode()

    def refresh_stats(self) -> None:
        self._mode = core.load_mode()
        portfolio = core.load_portfolio_size(self._mode)
        overview = core.get_analytics_overview(self._mode)

        total_pnl = overview.get("total_pnl", 0) or 0
        win_rate = overview.get("win_rate", 0) or 0
        open_count = overview.get("open_trades", 0) or 0

        pnl_color = "green" if total_pnl >= 0 else "red"
        pnl_sign = "+" if total_pnl >= 0 else ""
        mode_label = "[yellow]PAPER[/]" if self._mode == "paper" else "[green]LIVE[/]"

        price = core.get_current_price("BTC")
        price_str = f"  [bold]BTC[/] ${price:,.0f}" if price else ""

        self.query_one("#bar-label", Static).update(
            f"[bold]${portfolio:,.2f}[/]  "
            f"[{pnl_color}]{pnl_sign}${total_pnl:,.2f}[/{pnl_color}]  "
            f"WR {win_rate:.0f}%  "
            f"Open {open_count}  "
            f"{mode_label}"
            f"{price_str}"
        )

    def compose(self) -> ComposeResult:
        yield Static(id="bar-label")


class TradeDetailsPanel(Widget):
    """Right-side panel showing live trade calculations and details."""

    DEFAULT_CSS = """
    TradeDetailsPanel {
        width: 1fr;
        height: auto;
        padding: 0 1;
        border: panel $accent;
    }
    #details-content {
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(id="details-content")

    def update_details(self, entry, sl, leverage, direction, risk_pct, tps, sls, mode) -> None:
        portfolio = core.load_portfolio_size(mode)

        if entry <= 0:
            self.show_placeholder()
            return

        MAINTENANCE_MARGIN = 0.0125
        leverage = float(leverage) if leverage else 1.0
        liq_price = entry * (1 - (1/leverage) + MAINTENANCE_MARGIN) if direction == 'long' else entry * (1 + (1/leverage) - MAINTENANCE_MARGIN)

        pos_result = core.calculate_position_size(entry, sl, leverage, direction, risk_pct, mode)
        rr_result = core.calculate_risk_reward(entry, sl, tps, direction)
        pnl_result = core.calculate_profit_loss(
            entry, sl, pos_result.get("position_size_dollars", 0),
            tps, sls, direction, leverage,
        )

        pos_dollars = pos_result.get("position_size_dollars", 0)
        pos_units = pos_result.get("position_size_units", 0)
        margin_req = pos_result.get("margin_required", 0)
        risk_amount = pos_result.get("risk_amount", 0)
        rr_ratio = rr_result.get("rr_ratio", 0)

        estimated_profit = sum(tp.get("profit_amount", 0) for tp in (pnl_result.get("take_profits") or []))
        
        def fmt_exact(val: float) -> str:
            if val < 1:
                return f"{val:,.6f}".rstrip('0').rstrip('.')
            return f"{val:,.2f}"

        entry_str = fmt_exact(entry)
        liq_str = fmt_exact(liq_price)

        lines = []
        lines.append("")
        lines.append(f"  [bold]Entry Price[/]         [white]${entry_str}[/]")
        lines.append(f"  [bold]Liquidation Price[/]   [orange3]${liq_str}[/]")
        lines.append("")
        lines.append(f"  [bold]Position Size[/]       [white]${pos_dollars:,.2f}[/] [dim]({pos_units:.6f} BTC)[/]")
        lines.append(f"  [bold]Margin Required[/]     [white]${margin_req:,.2f}[/]")
        lines.append("")
        lines.append(f"  [bold]Risk/Reward Ratio[/]   [white]1:{rr_ratio:.2f}[/]")
        lines.append(f"  [bold]Risk Amount ({risk_pct}%)[/]   [white]${risk_amount:,.2f}[/]")
        lines.append("")
        
        sl_item = next((s for s in (pnl_result.get("stop_losses") or []) if not s.get("is_liquidation")), None)
        est_loss_sl = sl_item["loss_amount"] if sl_item else risk_amount
        
        lines.append(f"  [bold]Estimated Loss (SL)[/] [red]${est_loss_sl:,.2f}[/]")
        
        tps_list = pnl_result.get("take_profits") or []
        if len(tps_list) > 0 and estimated_profit > 0:
            lines.append("  [bold]Estimated Profit[/]")
            for tp in tps_list:
                if tp["price"] > 0 and tp["allocation"] > 0:
                    lines.append(f"    [dim]TP{tp['index']+1} (${tp['price']:,.2f}):[/] [green]${tp['profit_amount']:,.2f}[/]")
            lines.append(f"    [dim]Total:[/] [bold green]${estimated_profit:,.2f}[/]")
        else:
            lines.append("  [bold]Estimated Profit[/]    [dim]N/A[/]")

        self.query_one("#details-content", Static).update("\n".join(lines))

    def show_placeholder(self) -> None:
        lines = []
        lines.append("")
        lines.append("  [bold]Entry Price[/]         [dim]N/A[/]")
        lines.append("  [bold]Liquidation Price[/]   [dim]N/A[/]")
        lines.append("")
        lines.append("  [bold]Position Size[/]       [dim]N/A[/]")
        lines.append("  [bold]Margin Required[/]     [dim]N/A[/]")
        lines.append("")
        lines.append("  [bold]Risk/Reward Ratio[/]   [dim]N/A[/]")
        lines.append("  [bold]Risk Amount[/]         [dim]N/A[/]")
        lines.append("")
        lines.append("  [bold]Estimated Loss (SL)[/] [dim]N/A[/]")
        lines.append("  [bold]Estimated Profit[/]    [dim]N/A[/]")
        self.query_one("#details-content", Static).update("\n".join(lines))


class ModeToggleScreen(ModalScreen):
    CSS = """
    ModeToggleScreen { align: center middle; }
    #mode-dialog {
        padding: 2; border: thick $primary; width: 50; height: auto;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="mode-dialog"):
            yield Label("[bold]Toggle Trading Mode[/bold]")
            yield Label("")
            current = core.load_mode()
            yield Label(f"Current: [bold]{current.upper()}[/bold]")
            yield Label("")
            with Horizontal():
                yield Button("Paper", variant="primary" if current == "live" else "default", id="mode-paper-btn")
                yield Button("Live", variant="primary" if current == "paper" else "default", id="mode-live-btn")
                yield Button("Cancel", variant="default", id="mode-cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "mode-paper-btn":
            core.save_mode("paper")
            self.dismiss("paper")
        elif event.button.id == "mode-live-btn":
            core.save_mode("live")
            self.dismiss("live")
        else:
            self.dismiss(None)


class RiskEditScreen(ModalScreen):
    CSS = """
    RiskEditScreen { align: center middle; }
    #risk-dialog {
        padding: 2; border: thick $primary; width: 50; height: auto;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        current_size = core.load_portfolio_size()
        current_risk = core.load_risk_pct()
        with Container(id="risk-dialog"):
            yield Label("[bold]Adjust Risk Parameters[/bold]")
            yield Label(f"Portfolio: ${current_size:,.2f} | Risk: {current_risk}%")
            yield Label("")
            yield Label("New portfolio size ($):")
            yield Input(value=str(current_size), id="risk-size-input")
            yield Label("New risk percentage (%):")
            yield Input(value=str(current_risk), id="risk-pct-input")
            with Horizontal():
                yield Button("Save", variant="success", id="risk-save-btn")
                yield Button("Cancel", variant="default", id="risk-cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "risk-save-btn":
            try:
                new_size = float(self.query_one("#risk-size-input", Input).value)
                new_risk = float(self.query_one("#risk-pct-input", Input).value)
                core.save_portfolio_config(new_size, new_risk)
                self.dismiss(True)
            except ValueError:
                self.dismiss(False)
        else:
            self.dismiss(False)


class CloseTradeScreen(ModalScreen):
    CSS = """
    CloseTradeScreen { align: center middle; }
    #close-dialog {
        padding: 2; border: thick $primary; width: 60; height: auto;
        background: $surface;
    }
    """

    def __init__(self, trade: dict, trade_index: int, mode: str):
        super().__init__()
        self.trade = trade
        self.trade_index = trade_index
        self.mode = mode

    def compose(self) -> ComposeResult:
        asset = self.trade.get("Asset", "")
        direction = self.trade.get("Direction", "").upper()
        entry = self.trade.get("Entry", 0) or 0
        pos_size = self.trade.get("Position_Size", 0) or 0
        leverage = self.trade.get("Leverage", 1) or 1
        margin = self.trade.get("Margin", 0) or 0

        coin = str(asset).split('/')[0].split('-')[0]
        current_price = core.get_current_price(coin)

        dir_color = "green" if direction == "LONG" else "red"

        with Container(id="close-dialog"):
            yield Label(f"[bold]Close {asset}[/] [{dir_color}]{direction}[/{dir_color}]")
            yield Label(f"Entry ${entry:,.2f} | Size ${pos_size:,.2f} | {leverage}x | Margin ${margin:,.2f}")
            if current_price:
                liq = core.calculate_liquidation_price(entry, leverage, direction.lower())
                direction_lower = direction.lower()
                if direction_lower == 'long':
                    upnl = (current_price - entry) * (pos_size / entry) if entry else 0
                else:
                    upnl = (entry - current_price) * (pos_size / entry) if entry else 0
                pnl_color = "green" if upnl >= 0 else "red"
                yield Label(f"Current: ${current_price:,.2f} | Liq: ${liq:,.2f} | uP&L: [{pnl_color}]${upnl:+,.2f}[/{pnl_color}]")
            yield Label("")
            yield Label("")
            with Horizontal():
                yield Button("[bold]Close Trade[/bold]", variant="success", id="confirm-close-btn")
                yield Button("Cancel", variant="default", id="cancel-close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-close-btn":
            try:
                asset = self.trade.get("Asset", "")
                coin = str(asset).split('/')[0].split('-')[0]
                exit_price = core.get_current_price(coin)
                if not exit_price:
                    raise ValueError("Could not fetch latest market price from API.")
                core.close_trade(self.trade_index, exit_price, self.mode)
                self.dismiss(True)
            except ValueError as e:
                self.query_one("#close-dialog", Container).mount(Label(f"[red]Error: {e}[/]"))
        else:
            self.dismiss(False)


class TradeDetailScreen(ModalScreen):
    CSS = """
    TradeDetailScreen { align: center middle; }
    #detail-dialog {
        padding: 1 2; border: thick $primary; width: 80; height: auto; max-height: 30;
        background: $surface;
    }
    """

    def __init__(self, trade: dict):
        super().__init__()
        self.trade = trade

    def compose(self) -> ComposeResult:
        asset = self.trade.get("Asset", "")
        direction = (self.trade.get("Direction") or "long").lower()
        entry = self.trade.get("Entry", 0) or 0
        sl = self.trade.get("SL", 0) or 0
        pos_size = self.trade.get("Position_Size", 0) or 0
        margin = self.trade.get("Margin", 0) or 0
        leverage = self.trade.get("Leverage", 1) or 1
        pnl = self.trade.get("P&L", 0) or 0
        tps_raw = self.trade.get("TPs", "[]")
        sls_raw = self.trade.get("SLs", "[]")
        thesis = self.trade.get("Thesis", "") or ""
        date = self.trade.get("Date", "")

        try:
            tps = json.loads(tps_raw) if isinstance(tps_raw, str) else (tps_raw or [])
        except (json.JSONDecodeError, TypeError):
            tps = []
        try:
            sls = json.loads(sls_raw) if isinstance(sls_raw, str) else (sls_raw or [])
        except (json.JSONDecodeError, TypeError):
            sls = []

        coin = asset.split('-')[0] if '-' in str(asset) else asset
        current_price = core.get_current_price(coin)
        dir_color = "green" if direction == "long" else "red"
        liq_price = core.calculate_liquidation_price(entry, leverage, direction)

        with Container(id="detail-dialog"):
            yield Label(f"[bold]{asset}[/] [{dir_color}]{direction.upper()}[/{dir_color}]  |  {date[:16] if date else ''}")
            yield Label("")

            if current_price:
                upnl = core.calculate_unrealized_pnl(self.trade, current_price)
                pnl_pct = (upnl / margin * 100) if (upnl is not None and margin and margin > 0) else None
                if upnl is not None:
                    upnl_color = "green" if upnl >= 0 else "red"
                    upnl_sign = "+" if upnl >= 0 else ""
                    pct_str = f" ({upnl_sign}{pnl_pct:.1f}%)" if pnl_pct is not None else ""
                    yield Label(f"  [bold]Current[/]     ${current_price:,.2f}    [bold]uP&L[/] [{upnl_color}]{upnl_sign}${upnl:,.2f}{pct_str}[/{upnl_color}]")
            yield Label(f"  [bold]Entry[/]       ${entry:,.2f}    [bold]Liq[/] ${liq_price:,.2f}")
            yield Label(f"  [bold]Size[/]        ${pos_size:,.2f}    [bold]Margin[/] ${margin:,.2f}    [bold]Lev[/] {leverage}x")
            if sl and sl > 0:
                yield Label(f"  [bold]Stop Loss[/]   ${sl:,.2f}")
            yield Label("")

            if tps:
                yield Label("  [bold]Take Profits[/]")
                for i, tp in enumerate(tps):
                    tp_price = tp.get("price", 0) if isinstance(tp, dict) else 0
                    tp_alloc = tp.get("allocation", 0) if isinstance(tp, dict) else 0
                    alloc_pct = f"{tp_alloc * 100:.0f}%" if tp_alloc <= 1 else f"{tp_alloc:.0f}%"
                    tp_pnl = 0
                    if tp_price and entry and pos_size and tp_alloc:
                        alloc_size = pos_size * (tp_alloc if tp_alloc <= 1 else tp_alloc / 100)
                        if direction == 'long':
                            tp_pnl = (tp_price - entry) / entry * alloc_size
                        else:
                            tp_pnl = (entry - tp_price) / entry * alloc_size
                    profit_color = "green" if tp_pnl >= 0 else "red"
                    yield Label(f"    TP{i+1}  ${tp_price:>9,.2f}  {alloc_pct:>4}  [{profit_color}]${tp_pnl:>+,.2f}[/{profit_color}]")
                yield Label("")

            if sls:
                yield Label("  [bold]Stop Losses[/]")
                for i, sl_item in enumerate(sls):
                    sl_price = sl_item.get("price", 0) if isinstance(sl_item, dict) else 0
                    sl_alloc = sl_item.get("allocation", 0) if isinstance(sl_item, dict) else 0
                    alloc_pct = f"{sl_alloc * 100:.0f}%" if sl_alloc <= 1 else f"{sl_alloc:.0f}%"
                    yield Label(f"    SL{i+1}  ${sl_price:>9,.2f}  {alloc_pct:>4}  [red]loss[/]")
                yield Label("")

            if thesis:
                yield Label(f"  [bold]Thesis[/]  {thesis}")

            yield Label("")
            yield Button("Close", variant="default", id="detail-close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


class TPHitScreen(ModalScreen):
    CSS = """
    TPHitScreen { align: center middle; }
    #tp-dialog {
        padding: 2; border: thick $primary; width: 50; height: auto;
        background: $surface;
    }
    """

    def __init__(self, trade: dict, trade_index: int, mode: str):
        super().__init__()
        self.trade = trade
        self.trade_index = trade_index
        self.mode = mode

    def compose(self) -> ComposeResult:
        tps_raw = self.trade.get("TPs", "[]")
        try:
            tps = json.loads(tps_raw) if isinstance(tps_raw, str) else (tps_raw or [])
        except (json.JSONDecodeError, TypeError):
            tps = []

        hit_tps_raw = self.trade.get("Hit_TPs", "[]")
        try:
            hit_tps = json.loads(hit_tps_raw) if isinstance(hit_tps_raw, str) else (hit_tps_raw or [])
        except (json.JSONDecodeError, TypeError):
            hit_tps = []

        with Container(id="tp-dialog"):
            yield Label("[bold]Take Profit Hit[/bold]")
            yield Label(f"Trade: {self.trade.get('Asset', '')} @ ${self.trade.get('Entry', 0):,.2f}")
            yield Label("")

            if not tps:
                yield Label("[dim]No take profits configured[/dim]")
            else:
                for i, tp in enumerate(tps):
                    tp_price = tp.get("price", 0) if isinstance(tp, dict) else 0
                    tp_alloc = tp.get("allocation", 0) if isinstance(tp, dict) else 0
                    alloc_str = f"{tp_alloc*100:.0f}%" if tp_alloc <= 1 else f"{tp_alloc:.0f}%"
                    is_hit = i in hit_tps
                    if is_hit:
                        yield Label(f"  TP{i+1}: ${tp_price:,.2f} ({alloc_str}) [green]HIT[/green]")
                    else:
                        with Horizontal():
                            yield Label(f"  TP{i+1}: ${tp_price:,.2f} ({alloc_str})")
                            yield Button("Mark Hit", variant="success", id=f"tp-{i}")

            yield Label("")
            yield Button("Cancel", variant="default", id="tp-cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("tp-"):
            tp_index = int(event.button.id.split("-")[1])
            tps_raw = self.trade.get("TPs", "[]")
            try:
                tps = json.loads(tps_raw) if isinstance(tps_raw, str) else (tps_raw or [])
            except (json.JSONDecodeError, TypeError):
                tps = []

            if tp_index < len(tps):
                tp = tps[tp_index]
                tp_price = tp.get("price", 0) if isinstance(tp, dict) else 0
                tp_alloc = tp.get("allocation", 0) if isinstance(tp, dict) else 0
                if tp_alloc > 1:
                    tp_alloc = tp_alloc / 100
                try:
                    core.partial_close_trade(self.trade_index, tp_price, tp_alloc, tp_index, self.mode)
                    self.dismiss(True)
                except Exception:
                    self.dismiss(False)
        elif event.button.id == "tp-cancel-btn":
            self.dismiss(None)


class SLHitScreen(ModalScreen):
    CSS = """
    SLHitScreen { align: center middle; }
    #sl-dialog {
        padding: 2; border: thick $primary; width: 50; height: auto;
        background: $surface;
    }
    """

    def __init__(self, trade: dict, trade_index: int, mode: str):
        super().__init__()
        self.trade = trade
        self.trade_index = trade_index
        self.mode = mode

    def compose(self) -> ComposeResult:
        sls_raw = self.trade.get("SLs", "[]")
        try:
            sls = json.loads(sls_raw) if isinstance(sls_raw, str) else (sls_raw or [])
        except (json.JSONDecodeError, TypeError):
            sls = []

        sl_price = self.trade.get("SL", 0) or 0

        with Container(id="sl-dialog"):
            yield Label("[bold]Stop Loss Hit[/bold]")
            yield Label(f"Trade: {self.trade.get('Asset', '')} @ ${self.trade.get('Entry', 0):,.2f}")
            yield Label("")

            if sls:
                for i, sl_item in enumerate(sls):
                    sl_item_price = sl_item.get("price", 0) if isinstance(sl_item, dict) else 0
                    sl_item_alloc = sl_item.get("allocation", 0) if isinstance(sl_item, dict) else 0
                    alloc_str = f"{sl_item_alloc*100:.0f}%" if sl_item_alloc <= 1 else f"{sl_item_alloc:.0f}%"
                    with Horizontal():
                        yield Label(f"  SL{i+1}: ${sl_item_price:,.2f} ({alloc_str}) ")
                        yield Button("Mark Hit", variant="error", id=f"sl-{i}")
            elif sl_price and sl_price > 0:
                with Horizontal():
                    yield Label(f"  SL: ${sl_price:,.2f} (100%)")
                    yield Button("Mark Hit", variant="error", id="sl-single")
            else:
                yield Label("[dim]No stop loss configured[/dim]")

            yield Label("")
            yield Button("Cancel", variant="default", id="sl-cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("sl-"):
            sls_raw = self.trade.get("SLs", "[]")
            try:
                sls = json.loads(sls_raw) if isinstance(sls_raw, str) else (sls_raw or [])
            except (json.JSONDecodeError, TypeError):
                sls = []

            if event.button.id == "sl-single":
                sl_price = self.trade.get("SL", 0) or 0
                if sl_price > 0:
                    try:
                        core.stop_loss_hit(self.trade_index, sl_price, 1.0, 0, self.mode)
                        self.dismiss(True)
                    except Exception:
                        self.dismiss(False)
            else:
                sl_index = int(event.button.id.split("-")[1])
                if sl_index < len(sls):
                    sl_item = sls[sl_index]
                    sl_price = sl_item.get("price", 0) if isinstance(sl_item, dict) else 0
                    sl_alloc = sl_item.get("allocation", 0) if isinstance(sl_item, dict) else 0
                    if sl_alloc > 1:
                        sl_alloc = sl_alloc / 100
                    try:
                        core.stop_loss_hit(self.trade_index, sl_price, sl_alloc, sl_index, self.mode)
                        self.dismiss(True)
                    except Exception:
                        self.dismiss(False)
        elif event.button.id == "sl-cancel-btn":
            self.dismiss(None)


class TradeLabTUI(App):
    """TradeLab - Terminal Trading Journal & Risk Management."""

    CSS = """
    Screen { background: #09090b; }

    .field-row { layout: horizontal; height: auto; padding: 1 2; }
    .field-label { width: auto; color: #71717a; padding: 0 2 0 0; }
    .field-input { 
        width: 20; height: 1; border: none; 
        background: #27272a; color: #e4e4e7; padding: 0 1; 
    }
    .field-input:focus { background: #3f3f46; }
    .field-select { width: 20; height: 1; border: none; background: #27272a; color: #e4e4e7; }
    .field-select:focus { background: #3f3f46; }
    .field-select > SelectCurrent { height: 1; border: none; padding: 0 1; }
    .field-spacer { width: 4; }
    .field-input-thesis { width: 1fr; height: 1; border: none; background: #27272a; color: #e4e4e7; padding: 0 1; }
    .field-input-thesis:focus { background: #3f3f46; }

    .dir-btn { height: 1; min-width: 8; border: none; }
    #btn-long.success { background: #10b981; color: #022c22; text-style: bold; }
    #btn-short.error { background: #ef4444; color: #450a0a; text-style: bold; }

    .lev-btn { height: 1; min-width: 3; border: none; background: #3f3f46; color: #e4e4e7; }
    .lev-btn:focus { background: #52525b; }
    .lev-input { width: 6; height: 1; border: none; background: #27272a; color: #e4e4e7; padding: 0 1; margin: 0 0; }

    .tp-row { layout: horizontal; height: auto; padding: 1 2; }
    .tp-label { width: auto; color: #71717a; padding: 0 2 0 0; }
    .tp-price { width: 16; height: 1; margin-right: 1; border: none; background: #27272a; color: #e4e4e7; padding: 0 1; }
    .tp-alloc { width: 5; height: 1; margin-right: 0; border: none; background: #27272a; color: #e4e4e7; padding: 0 1; }
    .tp-pct { color: #71717a; width: 2; height: 1; }
    .tp-btn { height: 1; min-width: 3; border: none; }
    .tp-add { background: #3f3f46; color: #22c55e; }
    .tp-remove { background: #3f3f46; color: #ef4444; }
    #tp-row-2, #tp-row-3, #tp-row-4 { display: none; }

    #dashboard-view { height: 1fr; padding: 0; background: #09090b; }
    #dashboard-top { height: 60%; }

    #trade-form-panel { 
        width: 2fr; border: solid #27272a;
        border-title-color: #6366f1; border-title-background: #18181b;
        height: 1fr; padding: 1 2; margin-right: 1; background: #18181b; 
    }
    #trade-details-panel { 
        width: 1fr; height: 1fr; border: solid #27272a;
        border-title-color: #a1a1aa; border-title-background: #18181b;
        background: #18181b; padding: 1 2; 
    }
    #open-trades-container { 
        height: 1fr; border: solid #27272a;
        border-title-color: #10b981; border-title-background: #18181b;
        margin-top: 1; background: #18181b; 
    }

    #add-trade-btn { width: 100%; margin-top: 1; border: none; background: #6366f1; color: white; text-style: bold; }
    
    DataTable { height: 1fr; border: none; }
    .metric-card { padding: 0 1; border: round $primary; margin: 0; height: auto; }
    .action-row { height: auto; padding: 0 1; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("m", "toggle_mode", "Mode", show=True),
        Binding("p", "edit_portfolio", "Risk", show=True),
        Binding("r", "refresh_price", "Price", show=True),
    ]

    TITLE = "TradeLab"

    def __init__(self):
        super().__init__()
        self._mode = core.load_mode()
        self._price_timer = None
        self._leverage = 10

    def compose(self) -> ComposeResult:
        yield Header(icon="T")
        yield PortfolioBar()

        with TabbedContent(initial="dashboard"):
            with TabPane("Dashboard", id="dashboard"):
                with Vertical(id="dashboard-view"):
                    with Horizontal(id="dashboard-top"):
                        # ----- Order Entry Form (Top-Left) -----
                        with VerticalScroll(id="trade-form-panel") as form_panel:
                            form_panel.border_title = "Order Entry"
                            with Horizontal(classes="field-row"):
                                yield Label("Asset", classes="field-label")
                                yield Select(
                                    [("BTC/USDT", "BTC/USDT")],
                                    value="BTC/USDT",
                                    id="trade-asset",
                                    classes="field-select"
                                )
                                yield Label("", classes="field-spacer")
                                yield Label("Direction", classes="field-label")
                                yield Button("Long", id="btn-long", variant="success", classes="dir-btn")
                                yield Button("Short", id="btn-short", variant="default", classes="dir-btn")
                            with Horizontal(classes="field-row"):
                                yield Label("Leverage", classes="field-label")
                                yield Button("−", id="lev-down", classes="lev-btn")
                                yield Input(value="10", id="trade-leverage", classes="lev-input")
                                yield Button("+", id="lev-up", classes="lev-btn")
                            with Horizontal(classes="field-row"):
                                yield Label("Stop Loss", classes="field-label")
                                yield Input(placeholder="0.00", id="trade-sl", classes="field-input")
                            with Horizontal(id="tp-row-1", classes="tp-row"):
                                yield Label("TP1", classes="tp-label")
                                yield Input(placeholder="Price", id="tp1-price", classes="tp-price")
                                yield Input(value="100", id="tp1-alloc", classes="tp-alloc")
                                yield Label("%", classes="tp-pct")
                                yield Button("+", id="add-tp-btn", classes="tp-btn tp-add")
                            with Horizontal(id="tp-row-2", classes="tp-row"):
                                yield Label("TP2", classes="tp-label")
                                yield Input(placeholder="Price", id="tp2-price", classes="tp-price")
                                yield Input(value="", id="tp2-alloc", classes="tp-alloc")
                                yield Label("%", classes="tp-pct")
                                yield Button("-", id="remove-tp-2", classes="tp-btn tp-remove")
                            with Horizontal(id="tp-row-3", classes="tp-row"):
                                yield Label("TP3", classes="tp-label")
                                yield Input(placeholder="Price", id="tp3-price", classes="tp-price")
                                yield Input(value="", id="tp3-alloc", classes="tp-alloc")
                                yield Label("%", classes="tp-pct")
                                yield Button("-", id="remove-tp-3", classes="tp-btn tp-remove")
                            with Horizontal(id="tp-row-4", classes="tp-row"):
                                yield Label("TP4", classes="tp-label")
                                yield Input(placeholder="Price", id="tp4-price", classes="tp-price")
                                yield Input(value="", id="tp4-alloc", classes="tp-alloc")
                                yield Label("%", classes="tp-pct")
                                yield Button("-", id="remove-tp-4", classes="tp-btn tp-remove")
                            with Horizontal(classes="field-row"):
                                yield Label("Thesis", classes="field-label")
                                yield Input(placeholder="Optional", id="trade-thesis", classes="field-input-thesis")
                            
                            with Horizontal():
                                yield Button("Add Trade", variant="success", id="add-trade-btn")

                        # ----- Trade Details (Top-Right) -----
                        details_panel = TradeDetailsPanel(id="trade-details-panel")
                        details_panel.border_title = "Trade Details & Risk"
                        yield details_panel

                    # ----- Open Trades (Bottom Full Width) -----
                    with Vertical(id="open-trades-container") as open_trades:
                        open_trades.border_title = "Active Positions"
                        yield DataTable(id="open-trades-table")

            with TabPane("Analytics", id="analytics"):
                with VerticalScroll():
                    with Horizontal(classes="action-row"):
                        yield Button("Refresh", variant="primary", id="refresh-analytics-btn")
                        yield Select(
                            [("All", "all"), ("7D", "7d"), ("30D", "30d"),
                             ("90D", "90d"), ("YTD", "ytd"), ("1Y", "1y")],
                            value="all",
                            id="analytics-timeframe",
                        )
                    with Horizontal():
                        yield Static("", id="metric-total", classes="metric-card")
                        yield Static("", id="metric-win-rate", classes="metric-card")
                        yield Static("", id="metric-pnl", classes="metric-card")
                        yield Static("", id="metric-avg-win", classes="metric-card")
                        yield Static("", id="metric-avg-loss", classes="metric-card")
                    yield Label("Closed Trades", classes="metric-label section-title")
                    yield DataTable(id="closed-trades-table")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_open_trades()
        self._refresh_analytics()
        self._refresh_portfolio()
        self._refresh_details()
        self._price_timer = self.set_interval(15, self._refresh_portfolio)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "calc-btn":
            self._calculate_trade()
        elif btn_id == "add-trade-btn":
            self._add_trade()
        elif btn_id == "refresh-analytics-btn":
            self._refresh_analytics()
        elif btn_id == "fetch-price-btn":
            self._fetch_price_into_entry()
        elif btn_id == "add-tp-btn":
            self._add_tp_row()
        elif btn_id == "remove-tp-2":
            self._remove_tp_row(2)
        elif btn_id == "remove-tp-3":
            self._remove_tp_row(3)
        elif btn_id == "remove-tp-4":
            self._remove_tp_row(4)
        elif btn_id == "btn-long":
            self.query_one("#btn-long", Button).variant = "success"
            self.query_one("#btn-short", Button).variant = "default"
            self._refresh_details()
        elif btn_id == "btn-short":
            self.query_one("#btn-long", Button).variant = "default"
            self.query_one("#btn-short", Button).variant = "error"
            self._refresh_details()
        elif btn_id == "lev-up":
            self._adjust_leverage(1)
        elif btn_id == "lev-down":
            self._adjust_leverage(-1)

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        if event.data_table.id == "open-trades-table":
            if event.coordinate.column == 11:
                trades = core.get_open_trades(self._mode)
                try:
                    row_key = event.data_table.get_row_at(event.coordinate.row)
                    local_idx = int(row_key[0])
                    trade = trades[local_idx]
                    global_idx = trade.get('_index', local_idx)
                    self.push_screen(CloseTradeScreen(trade, global_idx, self._mode), self._on_trade_action)
                except Exception:
                    pass

    def _add_tp_row(self) -> None:
        self.visible_tps = getattr(self, "visible_tps", 1)
        if self.visible_tps < 4:
            self.visible_tps += 1
            row = self.query_one(f"#tp-row-{self.visible_tps}")
            row.styles.display = "block"
            self._rebalance_tps()

    def _remove_tp_row(self, target_row: int) -> None:
        self.visible_tps = getattr(self, "visible_tps", 1)
        if target_row > self.visible_tps or target_row <= 1:
            return
        # Clear all rows from target_row onward, then show only the right count
        for i in range(target_row, 5):
            try:
                self.query_one(f"#tp{i}-price", Input).value = ""
                self.query_one(f"#tp{i}-alloc", Input).value = ""
                row = self.query_one(f"#tp-row-{i}")
                row.styles.display = "none"
            except Exception:
                pass
        self.visible_tps = target_row - 1
        # Ensure at least row 1 is visible
        if self.visible_tps < 1:
            self.visible_tps = 1
        self._rebalance_tps()

    def _rebalance_tps(self, changed_id=None) -> None:
        if getattr(self, "_rebalancing", False):
            return
        self._rebalancing = True
        try:
            visible_tps = getattr(self, "visible_tps", 1)
            if visible_tps == 1:
                self.query_one("#tp1-alloc", Input).value = "100"
                return

            tps = []
            changed_val = None
            for i in range(1, visible_tps + 1):
                val_str = self.query_one(f"#tp{i}-alloc", Input).value.replace("%", "").strip()
                try:
                    val = float(val_str)
                except ValueError:
                    val = 0
                tps.append({"id": f"tp{i}-alloc", "val": val})
                if changed_id == f"tp{i}-alloc":
                    changed_val = val

            if changed_id and changed_val is not None:
                remaining = 100 - changed_val
                others = visible_tps - 1
                if others > 0:
                    base = remaining // others
                    remainder = remaining - (base * others)
                    other_idx = 0
                    for tp in tps:
                        if tp["id"] != changed_id:
                            val = base + (1 if other_idx < remainder else 0)
                            self.query_one(f"#{tp['id']}", Input).value = f"{val:.0f}"
                            other_idx += 1
            else:
                base = 100 // visible_tps
                remainder = 100 - (base * visible_tps)
                for idx, tp in enumerate(tps):
                    val = base + (1 if idx < remainder else 0)
                    self.query_one(f"#{tp['id']}", Input).value = f"{val:.0f}"
        finally:
            self._rebalancing = False

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "trade-asset":
            self._fetch_price_into_entry()
        elif event.input.id and "-alloc" in event.input.id:
            self._rebalance_tps(changed_id=event.input.id)
        elif event.input.id == "trade-leverage":
            try:
                val = int(event.input.value.strip())
                self._leverage = max(1, min(125, val))
            except (ValueError, TypeError):
                pass
        self._refresh_details()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "analytics-timeframe":
            self._refresh_analytics()

    def _fetch_price_into_entry(self) -> None:
        try:
            asset = self.query_one("#trade-asset", Select).value
            if not asset: return
            coin = str(asset).split('/')[0].split('-')[0]
            price = core.get_current_price(coin)
            if price:
                self.current_price = price
                self._refresh_details()
            else:
                self.current_price = 0
                self.query_one("#trade-details-panel", TradeDetailsPanel).show_placeholder()
        except Exception:
            pass

    def _get_leverage(self) -> int:
        try:
            val = int(self.query_one("#trade-leverage", Input).value.strip())
            if val > 0:
                self._leverage = min(val, 125)
                return self._leverage
        except (ValueError, TypeError):
            pass
        return self._leverage

    def _adjust_leverage(self, delta: int) -> None:
        self._leverage = max(1, min(125, self._leverage + delta))
        self.query_one("#trade-leverage", Input).value = str(self._leverage)
        self._refresh_details()

    def _refresh_details(self) -> None:
        entry = getattr(self, "current_price", 0.0)
        sl = self._parse_float("trade-sl")
        leverage = self._get_leverage()
        risk_pct = core.load_risk_pct(self._mode)
        direction = "long" if self.query_one("#btn-long", Button).variant == "success" else "short"
        tps = self._collect_take_profits()
        sls = self._collect_stop_losses()
        self.query_one("#trade-details-panel", TradeDetailsPanel).update_details(
            entry, sl, leverage, direction, risk_pct, tps, sls, self._mode
        )

    def _parse_float(self, widget_id: str, default: float = 0.0) -> float:
        try:
            widget = self.query_one(f"#{widget_id}")
            if hasattr(widget, "value"):
                val = widget.value
            else:
                val = str(widget.renderable)
            val = val.replace("%", "").strip()
            return float(val) if val else default
        except (ValueError, TypeError, Exception):
            return default

    def _parse_int(self, widget_id: str, default: int = 1) -> int:
        try:
            val = self.query_one(f"#{widget_id}", Input).value.strip()
            return int(val) if val else default
        except (ValueError, TypeError):
            return default

    def _calculate_trade(self) -> None:
        self._refresh_details()

    def _collect_take_profits(self) -> list:
        tps = []
        for i in range(1, 5):
            price = self._parse_float(f"tp{i}-price")
            alloc = self._parse_float(f"tp{i}-alloc", 0)
            if alloc > 0 and alloc <= 100:
                alloc_decimal = alloc / 100
            elif price > 0:
                alloc_decimal = 0.25
            else:
                continue
            if price > 0:
                tps.append({"price": price, "allocation": alloc_decimal})
        return tps

    def _collect_stop_losses(self) -> list:
        return []

    def _add_trade(self) -> None:
        try:
            asset = self.query_one("#trade-asset", Select).value
        except Exception:
            return
        direction = "long" if self.query_one("#btn-long", Button).variant == "success" else "short"
        entry = getattr(self, "current_price", 0.0)
        sl = self._parse_float("trade-sl")
        leverage = self._get_leverage()
        thesis = self.query_one("#trade-thesis", Input).value.strip()

        if not asset:
            return
        if entry <= 0:
            return

        risk_pct = core.load_risk_pct(self._mode)
        pos_result = core.calculate_position_size(entry, sl, leverage, direction, risk_pct, self._mode)
        position_size = pos_result.get("position_size_dollars", 0)
        margin = pos_result.get("margin_required", 0)

        take_profits = self._collect_take_profits()
        stop_losses = self._collect_stop_losses()

        try:
            core.add_trade(
                asset=asset, direction=direction, entry_price=entry,
                stop_loss=sl, position_size=position_size,
                take_profits=take_profits, stop_losses=stop_losses,
                thesis=thesis or None, margin=margin, leverage=leverage,
                mode=self._mode,
            )
            self._refresh_open_trades()
            self._refresh_portfolio()
        except ValueError:
            pass

    def _get_selected_trade(self) -> tuple:
        table = self.query_one("#open-trades-table", DataTable)
        try:
            row_key = table.get_row_at(table.cursor_row)
        except Exception:
            return None, None
        if not row_key:
            return None, None
        try:
            trade_idx = int(row_key[0])
        except (ValueError, IndexError, TypeError):
            return None, None
        trades = core.get_open_trades(self._mode)
        if trade_idx < 0 or trade_idx >= len(trades):
            return None, None
        return trades[trade_idx], trade_idx

    def _refresh_open_trades(self) -> None:
        table = self.query_one("#open-trades-table", DataTable)
        table.clear(columns=True)
        table.add_columns("#", "Asset", "Dir", "Entry", "Current", "Size", "Margin", "Lev", "uP&L", "Liq", "Date", "Action")

        trades = core.get_open_trades(self._mode)
        if not trades:
            return

        for i, trade in enumerate(trades):
            asset = trade.get("Asset", "")
            direction = (trade.get("Direction", "") or "long").lower()
            entry = trade.get("Entry", 0) or 0
            pos_size = trade.get("Position_Size", 0) or 0
            margin = trade.get("Margin", 0) or 0
            leverage = trade.get("Leverage", 1) or 1

            coin = str(asset).split('/')[0].split('-')[0]
            current_price = core.get_current_price(coin)
            unrealized = core.calculate_unrealized_pnl(trade, current_price)
            liq_price = core.calculate_liquidation_price(entry, leverage, direction)

            upnl_str = f"${unrealized:+,.2f}" if unrealized is not None else "--"
            current_str = f"${current_price:,.2f}" if current_price else "--"

            table.add_row(
                str(i), asset, direction.upper()[:3],
                f"${entry:,.2f}" if entry else "",
                current_str,
                f"${pos_size:,.2f}" if pos_size else "",
                f"${margin:,.2f}" if margin else "",
                f"{leverage}x",
                upnl_str,
                f"${liq_price:,.2f}" if liq_price else "",
                trade.get("Date", "")[:10] if trade.get("Date") else "",
                "[bold red]❌ Close[/]"
            )

    def _close_selected_trade(self) -> None:
        trade, trade_idx = self._get_selected_trade()
        if trade is None:
            return
        self.push_screen(CloseTradeScreen(trade, trade_idx, self._mode), self._on_trade_action)

    def _show_trade_details(self) -> None:
        trade, _ = self._get_selected_trade()
        if trade is None:
            return
        self.push_screen(TradeDetailScreen(trade))

    def _on_trade_action(self, result) -> None:
        self._refresh_open_trades()
        self._refresh_analytics()
        self._refresh_portfolio()

    def _refresh_portfolio(self) -> None:
        try:
            self.query_one("PortfolioBar", PortfolioBar).refresh_stats()
            self._fetch_price_into_entry()
            self._refresh_open_trades()
        except Exception:
            pass

    def _refresh_analytics(self) -> None:
        mode = self._mode
        try:
            timeframe = self.query_one("#analytics-timeframe", Select).value
        except Exception:
            timeframe = "all"

        overview = core.get_analytics_overview(mode)
        metrics = core.get_analytics_metrics(timeframe, mode)

        total = overview.get("total_trades", 0)
        open_t = overview.get("open_trades", 0)
        wins = overview.get("winning_trades", 0)
        losses = overview.get("losing_trades", 0)

        self.query_one("#metric-total", Static).update(
            f"[bold]Trades[/bold] {total}\nOpen {open_t} | W {wins} | L {losses}"
        )

        win_rate = metrics.get("win_rate", 0)
        self.query_one("#metric-win-rate", Static).update(f"[bold]Win Rate[/bold]\n{win_rate:.1f}%")

        total_pnl = metrics.get("total_pnl", 0)
        pnl_color = "green" if total_pnl >= 0 else "red"
        self.query_one("#metric-pnl", Static).update(
            f"[bold]P&L[/bold]\n[{pnl_color}]${total_pnl:,.2f}[/{pnl_color}]"
        )

        avg_win = metrics.get("avg_win", 0)
        avg_loss = metrics.get("avg_loss", 0)
        self.query_one("#metric-avg-win", Static).update(f"[bold]Avg Win[/bold]\n[green]+${avg_win:,.2f}[/green]")
        self.query_one("#metric-avg-loss", Static).update(f"[bold]Avg Loss[/bold]\n[red]-${abs(avg_loss):,.2f}[/red]")

        self._refresh_closed_trades_table()

    def _refresh_closed_trades_table(self) -> None:
        table = self.query_one("#closed-trades-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Date", "Asset", "Dir", "Entry", "Exit", "P&L", "Lev", "Hold")

        result = core.get_closed_trades(sort="date_desc", mode=self._mode, limit=50)
        trades = result.get("trades", [])
        if not trades:
            return

        for trade in trades:
            pnl = trade.get("P&L", 0) or 0
            pnl_str = f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"
            table.add_row(
                trade.get("Date", "")[:10] if trade.get("Date") else "",
                trade.get("Asset", ""),
                trade.get("Direction", "").upper()[:3],
                f"${trade.get('Entry', 0):,.2f}" if trade.get("Entry") else "",
                f"${trade.get('Exit_Price', 0):,.2f}" if trade.get("Exit_Price") else "",
                pnl_str,
                f"{trade.get('Leverage', 1)}x",
                trade.get("Hold_Time", ""),
            )

    def action_toggle_mode(self) -> None:
        self.push_screen(ModeToggleScreen(), self._on_mode_changed)

    def _on_mode_changed(self, result) -> None:
        if result:
            self._mode = result
        self._refresh_open_trades()
        self._refresh_analytics()
        self._refresh_portfolio()

    def action_edit_portfolio(self) -> None:
        self.push_screen(RiskEditScreen(), self._on_portfolio_edited)

    def _on_portfolio_edited(self, result) -> None:
        self._refresh_portfolio()
        self._refresh_analytics()

    def action_refresh_price(self) -> None:
        self._refresh_portfolio()


def main():
    app = TradeLabTUI()
    app.run()


if __name__ == "__main__":
    main()