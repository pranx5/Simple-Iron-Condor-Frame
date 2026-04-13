from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .config import UNDERLYINGS
from .math_utils import normal_cdf, one_sd_dollars, pl_at_expiry_per_share, pop_profit_zone, round_strike
from .storage import TradeStore
from .yahoo_client import fetch_yahoo_quote


DASH = "-"


def _parse_float(text: str) -> Optional[float]:
    t = (text or "").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _fmt_num(n: Optional[float], d: int = 2) -> str:
    if n is None:
        return DASH
    return f"{n:,.{d}f}"


def _fmt_money(n: Optional[float]) -> str:
    if n is None:
        return DASH
    sign = "-" if n < 0 else ""
    return f"{sign}${abs(n):,.2f}"


def _fmt_pct(n: Optional[float]) -> str:
    if n is None:
        return DASH
    return f"{n:.1f}%"


def _iso_to_local(iso_str: str) -> Optional[datetime]:
    if not iso_str:
        return None
    fixed = iso_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(fixed).astimezone()
    except ValueError:
        return None


class PayoffCanvas(FigureCanvasQTAgg):
    def __init__(self) -> None:
        fig = Figure(figsize=(10, 4.2), dpi=100)
        self.ax = fig.add_subplot(111)
        super().__init__(fig)
        fig.tight_layout()

    def draw_empty(self) -> None:
        self.ax.clear()
        self.ax.set_facecolor("#0f172a")
        self.figure.set_facecolor("#0f172a")
        self.ax.text(0.5, 0.5, "Set underlying price to draw diagram.", ha="center", va="center", color="#cbd5e1")
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.draw_idle()

    def draw_payoff(self, ctx: dict[str, Any]) -> None:
        self.ax.clear()
        self.ax.set_facecolor("#0f172a")
        self.figure.set_facecolor("#0f172a")

        p0 = ctx["p0"]
        x_min = p0 * 0.97
        x_max = p0 * 1.03
        samples = 220

        xs = [x_min + i * (x_max - x_min) / samples for i in range(samples + 1)]
        ys = [
            pl_at_expiry_per_share(
                x,
                ctx["lp_k"],
                ctx["sp_k"],
                ctx["sc_k"],
                ctx["lc_k"],
                ctx["sp_r"],
                ctx["lp_p"],
                ctx["sc_r"],
                ctx["lc_p"],
            )
            * 100.0
            * ctx["contracts"]
            for x in xs
        ]

        y_min = min(0.0, min(ys))
        y_max = max(0.0, max(ys))
        pad_y = max(80.0, (y_max - y_min) * 0.08)
        y_min -= pad_y
        y_max += pad_y

        sigma = ctx.get("sigma")
        if sigma and sigma > 0:
            self.ax.axvspan(p0 - sigma, p0 + sigma, color="#60a5fa", alpha=0.15)

        lbe = ctx["lbe"]
        ube = ctx["ube"]
        left, right = min(lbe, ube), max(lbe, ube)

        self.ax.axvspan(x_min, left, color="#ef4444", alpha=0.14)
        self.ax.axvspan(left, right, color="#22c55e", alpha=0.20)
        self.ax.axvspan(right, x_max, color="#ef4444", alpha=0.14)

        self.ax.plot(xs, ys, color="#60a5fa", linewidth=2.2)
        self.ax.axhline(0, color="#64748b", linewidth=1)

        for k in (ctx["lp_k"], ctx["sp_k"], ctx["sc_k"], ctx["lc_k"]):
            self.ax.axvline(k, color="#94a3b8", linestyle="--", linewidth=1, alpha=0.75)

        self.ax.axvline(lbe, color="#f59e0b", linestyle=":", linewidth=1.4)
        self.ax.axvline(ube, color="#f59e0b", linestyle=":", linewidth=1.4)
        self.ax.axvline(p0, color="#60a5fa", linewidth=1.4)

        self.ax.set_xlim(x_min, x_max)
        self.ax.set_ylim(y_min, y_max)
        self.ax.tick_params(colors="#cbd5e1", labelsize=9)
        for spine in self.ax.spines.values():
            spine.set_color("#334155")

        self.ax.set_title("P/L at Expiration (0DTE)", color="#e2e8f0", fontsize=11)
        self.ax.set_xlabel("Underlying Price", color="#cbd5e1", fontsize=9)
        self.ax.set_ylabel("P/L ($)", color="#cbd5e1", fontsize=9)
        self.draw_idle()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("0DTE Iron Condor - Desktop")
        self.resize(1380, 920)

        self.store = TradeStore()
        self.cached_trades: list[dict[str, Any]] = []

        self.state = {
            "name": "SPX",
            "ticker": UNDERLYINGS["SPX"]["ticker"],
            "wing": UNDERLYINGS["SPX"]["wing"],
            "iv_default": UNDERLYINGS["SPX"]["iv_default"],
            "price": None,
            "quote_as_of_sec": None,
            "quote_source": None,
            "live_ok": True,
        }

        self._build_ui()
        self._wire_events()
        self._refresh_step_button_labels()

        self.iv_edit.setText(str(self.state["iv_default"]))
        self._recompute_suggestions()
        self._update_metrics()
        self._refresh_price()
        self._load_trades()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)

        header = QHBoxLayout()
        header.addWidget(QLabel("Underlying:"))

        self.ticker_combo = QComboBox()
        self.ticker_combo.addItem("SPX (^SPX)", "SPX")
        self.ticker_combo.addItem("QQQ", "QQQ")
        header.addWidget(self.ticker_combo)

        self.refresh_btn = QPushButton("Refresh Price")
        header.addWidget(self.refresh_btn)

        self.price_lbl = QLabel("Spot: -")
        self.price_lbl.setStyleSheet("font-weight:600;")
        header.addWidget(self.price_lbl)

        self.price_asof_lbl = QLabel("")
        self.price_asof_lbl.setStyleSheet("color:#64748b;")
        header.addWidget(self.price_asof_lbl, 1)

        main.addLayout(header)

        row = QHBoxLayout()

        left = QVBoxLayout()
        left.addWidget(self._build_suggestion_group())
        left.addWidget(self._build_legs_group())
        left.addWidget(self._build_metrics_group())

        right = QVBoxLayout()
        right.addWidget(self._build_chart_group(), 2)
        right.addWidget(self._build_trade_group(), 3)

        row.addLayout(left, 1)
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        row.addWidget(sep)
        row.addLayout(right, 1)
        main.addLayout(row, 1)

    def _build_suggestion_group(self) -> QGroupBox:
        box = QGroupBox("Starting Point (Suggestions)")
        lay = QVBoxLayout(box)

        top = QGridLayout()

        self.override_edit = QLineEdit()
        self.override_edit.setPlaceholderText("Override spot (optional)")
        top.addWidget(QLabel("Override Spot ($):"), 0, 0)
        top.addWidget(self.override_edit, 0, 1)

        self.iv_edit = QLineEdit()
        self.iv_edit.setPlaceholderText("IV %")
        top.addWidget(QLabel("IV %:"), 1, 0)
        top.addWidget(self.iv_edit, 1, 1)

        self.contracts_spin = QSpinBox()
        self.contracts_spin.setRange(1, 500)
        self.contracts_spin.setValue(1)
        top.addWidget(QLabel("Contracts:"), 2, 0)
        top.addWidget(self.contracts_spin, 2, 1)

        lay.addLayout(top)

        self.aggr_lbl = QLabel("Aggressiveness: 1.00 x intraday 1SD")
        lay.addWidget(self.aggr_lbl)

        self.aggr_slider = QSlider(Qt.Horizontal)
        self.aggr_slider.setRange(25, 100)
        self.aggr_slider.setSingleStep(5)
        self.aggr_slider.setValue(100)
        lay.addWidget(self.aggr_slider)

        self.band_lbl = QLabel("Suggested short band: +/-$- -> -")
        self.prob_lbl = QLabel("Approx inside probability: -")
        self.band_lbl.setStyleSheet("color:#b91c1c;font-weight:600;")
        self.prob_lbl.setStyleSheet("color:#b91c1c;font-weight:600;")
        lay.addWidget(self.band_lbl)
        lay.addWidget(self.prob_lbl)

        g = QGridLayout()
        self.sug_sp_edit = QLineEdit()
        self.sug_sc_edit = QLineEdit()
        self.sug_lp_edit = QLineEdit()
        self.sug_lc_edit = QLineEdit()
        g.addWidget(QLabel("Suggested Short Put"), 0, 0)
        g.addWidget(self.sug_sp_edit, 0, 1)
        g.addWidget(QLabel("Suggested Short Call"), 0, 2)
        g.addWidget(self.sug_sc_edit, 0, 3)
        g.addWidget(QLabel("Suggested Long Put"), 1, 0)
        g.addWidget(self.sug_lp_edit, 1, 1)
        g.addWidget(QLabel("Suggested Long Call"), 1, 2)
        g.addWidget(self.sug_lc_edit, 1, 3)
        lay.addLayout(g)

        shift_row = QHBoxLayout()
        self.btn_puts_down = QPushButton("Puts -5")
        self.btn_puts_up = QPushButton("Puts +5")
        self.btn_calls_down = QPushButton("Calls -5")
        self.btn_calls_up = QPushButton("Calls +5")
        shift_row.addWidget(self.btn_puts_down)
        shift_row.addWidget(self.btn_puts_up)
        shift_row.addWidget(self.btn_calls_down)
        shift_row.addWidget(self.btn_calls_up)
        shift_row.addStretch(1)
        lay.addLayout(shift_row)

        lay.addWidget(QLabel("Thinkorswim-style order preview"))
        self.suggested_ticket_table = QTableWidget(4, 8)
        self.suggested_ticket_table.setHorizontalHeaderLabels(
            ["Spread", "Side", "Qty", "Pos Effect", "Symbol", "Exp", "Strike", "Type"]
        )
        self.suggested_ticket_table.verticalHeader().setVisible(False)
        self.suggested_ticket_table.setSelectionMode(QTableWidget.NoSelection)
        self.suggested_ticket_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.suggested_ticket_table.horizontalHeader().setStretchLastSection(True)
        self.suggested_ticket_table.setFixedHeight(170)
        lay.addWidget(self.suggested_ticket_table)

        self.apply_suggest_btn = QPushButton("Apply Suggestions to Legs")
        lay.addWidget(self.apply_suggest_btn)
        return box

    def _build_legs_group(self) -> QGroupBox:
        box = QGroupBox("Legs and Premiums (Manual)")
        lay = QGridLayout(box)

        self.strike_error_lbl = QLabel("")
        self.strike_error_lbl.setStyleSheet("color:#b91c1c;font-weight:600;")
        lay.addWidget(self.strike_error_lbl, 0, 0, 1, 4)

        self.sp_k_edit = QLineEdit()
        self.lp_k_edit = QLineEdit()
        self.sc_k_edit = QLineEdit()
        self.lc_k_edit = QLineEdit()

        self.sp_p_edit = QLineEdit()
        self.lp_p_edit = QLineEdit()
        self.sc_p_edit = QLineEdit()
        self.lc_p_edit = QLineEdit()

        lay.addWidget(QLabel("Short Put Strike"), 1, 0)
        lay.addWidget(self.sp_k_edit, 1, 1)
        lay.addWidget(QLabel("Short Put Premium ($/sh)"), 1, 2)
        lay.addWidget(self.sp_p_edit, 1, 3)

        lay.addWidget(QLabel("Long Put Strike"), 2, 0)
        lay.addWidget(self.lp_k_edit, 2, 1)
        lay.addWidget(QLabel("Long Put Premium ($/sh)"), 2, 2)
        lay.addWidget(self.lp_p_edit, 2, 3)

        lay.addWidget(QLabel("Short Call Strike"), 3, 0)
        lay.addWidget(self.sc_k_edit, 3, 1)
        lay.addWidget(QLabel("Short Call Premium ($/sh)"), 3, 2)
        lay.addWidget(self.sc_p_edit, 3, 3)

        lay.addWidget(QLabel("Long Call Strike"), 4, 0)
        lay.addWidget(self.lc_k_edit, 4, 1)
        lay.addWidget(QLabel("Long Call Premium ($/sh)"), 4, 2)
        lay.addWidget(self.lc_p_edit, 4, 3)

        return box

    def _build_metrics_group(self) -> QGroupBox:
        box = QGroupBox("Position Metrics")
        form = QFormLayout(box)

        self.metric_labels: dict[str, QLabel] = {}
        for key, label in [
            ("net", "Net Credit ($/sh)"),
            ("max_profit", "Max Profit"),
            ("max_loss", "Max Loss"),
            ("lbe", "Lower Breakeven"),
            ("ube", "Upper Breakeven"),
            ("zone", "Profit Zone Width"),
            ("rr", "Risk / Reward"),
            ("pop", "Est. PoP (Profit Zone)"),
        ]:
            v = QLabel(DASH)
            v.setStyleSheet("font-weight:600;")
            form.addRow(label + ":", v)
            self.metric_labels[key] = v

        return box

    def _build_chart_group(self) -> QGroupBox:
        box = QGroupBox("Payoff Chart")
        lay = QVBoxLayout(box)
        self.chart = PayoffCanvas()
        lay.addWidget(self.chart)
        return box

    def _build_trade_group(self) -> QGroupBox:
        box = QGroupBox("Trade Log (Disk Backed)")
        lay = QVBoxLayout(box)

        self.trade_status_lbl = QLabel("")
        self.trade_status_lbl.setStyleSheet("color:#334155;")
        lay.addWidget(self.trade_status_lbl)

        self.trade_legs_input = QTextEdit()
        self.trade_legs_input.setPlaceholderText("6465 CALL\n6470 CALL\n6390 PUT\n6385 PUT")
        self.trade_legs_input.setFixedHeight(90)
        lay.addWidget(QLabel("Legs (4 lines: strike then CALL/PUT)"))
        lay.addWidget(self.trade_legs_input)

        form = QGridLayout()
        self.trade_break_l_edit = QLineEdit()
        self.trade_break_u_edit = QLineEdit()
        self.trade_max_p_edit = QLineEdit()
        self.trade_max_l_edit = QLineEdit()
        self.trade_contracts_line = QLineEdit()
        self.trade_notes_edit = QLineEdit()

        form.addWidget(QLabel("Lower BE"), 0, 0)
        form.addWidget(self.trade_break_l_edit, 0, 1)
        form.addWidget(QLabel("Upper BE"), 0, 2)
        form.addWidget(self.trade_break_u_edit, 0, 3)

        form.addWidget(QLabel("Max Profit"), 1, 0)
        form.addWidget(self.trade_max_p_edit, 1, 1)
        form.addWidget(QLabel("Max Loss"), 1, 2)
        form.addWidget(self.trade_max_l_edit, 1, 3)

        form.addWidget(QLabel("Contracts and Symbol"), 2, 0)
        form.addWidget(self.trade_contracts_line, 2, 1)
        self.trade_contracts_line.setPlaceholderText("3 SPX")
        form.addWidget(QLabel("Notes"), 2, 2)
        form.addWidget(self.trade_notes_edit, 2, 3)

        lay.addLayout(form)

        btns = QHBoxLayout()
        self.save_trade_btn = QPushButton("Save Trade")
        self.delete_trade_btn = QPushButton("Delete Selected")
        btns.addWidget(self.save_trade_btn)
        btns.addWidget(self.delete_trade_btn)

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All", "all")
        self.filter_combo.addItem("Today", "today")
        self.filter_combo.addItem("Yesterday", "yesterday")
        self.filter_combo.addItem("Last 7 Days", "last7")
        self.filter_combo.addItem("Last 30 Days", "last30")
        self.filter_combo.setCurrentIndex(3)
        btns.addWidget(QLabel("Filter:"))
        btns.addWidget(self.filter_combo)
        btns.addStretch(1)
        lay.addLayout(btns)

        self.trade_table = QTableWidget(0, 6)
        self.trade_table.setHorizontalHeaderLabels(["Saved", "Qty x Sym", "Legs", "BE Range", "P/L", "Notes"])
        self.trade_table.horizontalHeader().setStretchLastSection(True)
        self.trade_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.trade_table.setSelectionMode(QTableWidget.SingleSelection)
        lay.addWidget(self.trade_table)

        return box

    def _wire_events(self) -> None:
        self.ticker_combo.currentIndexChanged.connect(self._on_ticker_change)
        self.refresh_btn.clicked.connect(self._refresh_price)
        self.apply_suggest_btn.clicked.connect(self._apply_suggestions_to_legs)

        self.sug_sp_edit.textChanged.connect(self._sync_wings_from_suggested_shorts)
        self.sug_sc_edit.textChanged.connect(self._sync_wings_from_suggested_shorts)
        self.sug_sp_edit.textChanged.connect(self._on_suggested_inputs_changed)
        self.sug_sc_edit.textChanged.connect(self._on_suggested_inputs_changed)
        self.sug_lp_edit.textChanged.connect(self._on_suggested_inputs_changed)
        self.sug_lc_edit.textChanged.connect(self._on_suggested_inputs_changed)

        self.btn_puts_down.clicked.connect(lambda: self._shift_suggested_side("puts", -1))
        self.btn_puts_up.clicked.connect(lambda: self._shift_suggested_side("puts", 1))
        self.btn_calls_down.clicked.connect(lambda: self._shift_suggested_side("calls", -1))
        self.btn_calls_up.clicked.connect(lambda: self._shift_suggested_side("calls", 1))

        for w in [
            self.override_edit,
            self.iv_edit,
            self.sp_k_edit,
            self.lp_k_edit,
            self.sc_k_edit,
            self.lc_k_edit,
            self.sp_p_edit,
            self.lp_p_edit,
            self.sc_p_edit,
            self.lc_p_edit,
        ]:
            w.textChanged.connect(self._on_inputs_changed)

        self.contracts_spin.valueChanged.connect(self._on_inputs_changed)
        self.aggr_slider.valueChanged.connect(self._on_inputs_changed)

        self.save_trade_btn.clicked.connect(self._save_trade)
        self.delete_trade_btn.clicked.connect(self._delete_selected_trade)
        self.filter_combo.currentIndexChanged.connect(self._render_trade_list)

    def _on_inputs_changed(self) -> None:
        self._recompute_suggestions()
        self._update_metrics()

    def _on_suggested_inputs_changed(self) -> None:
        self._update_suggested_ticket_preview()

    def _suggested_step(self) -> int:
        wing = int(self.state["wing"])
        return 5 if wing >= 5 else 1

    def _refresh_step_button_labels(self) -> None:
        step = self._suggested_step()
        self.btn_puts_down.setText(f"Puts -{step}")
        self.btn_puts_up.setText(f"Puts +{step}")
        self.btn_calls_down.setText(f"Calls -{step}")
        self.btn_calls_up.setText(f"Calls +{step}")

    def _shift_suggested_side(self, side: str, direction: int) -> None:
        step = self._suggested_step() * direction

        def shift_edit(edit: QLineEdit) -> None:
            v = _parse_float(edit.text())
            if v is None:
                return
            edit.setText(str(int(round(v + step))))

        if side == "puts":
            shift_edit(self.sug_sp_edit)
            shift_edit(self.sug_lp_edit)
        else:
            shift_edit(self.sug_sc_edit)
            shift_edit(self.sug_lc_edit)

    def _on_ticker_change(self) -> None:
        key = self.ticker_combo.currentData()
        cfg = UNDERLYINGS[key]
        self.state["name"] = key
        self.state["ticker"] = cfg["ticker"]
        self.state["wing"] = cfg["wing"]
        self.state["iv_default"] = cfg["iv_default"]
        self._refresh_step_button_labels()
        self.iv_edit.setText(str(cfg["iv_default"]))
        self._refresh_price()

    def _effective_price(self) -> Optional[float]:
        override = _parse_float(self.override_edit.text())
        if override is not None and override > 0:
            return override
        p = self.state.get("price")
        if isinstance(p, (int, float)) and p > 0:
            return float(p)
        return None

    def _update_price_label(self) -> None:
        p = self.state.get("price")
        o = _parse_float(self.override_edit.text())
        if o is not None and o > 0:
            self.price_lbl.setText(f"Spot: {_fmt_num(o, 2)} (override)")
            self.price_asof_lbl.setText("Using override spot for calculator and chart.")
            return

        if p is None:
            self.price_lbl.setText("Spot: -")
            self.price_asof_lbl.setText("No live quote. Enter override spot.")
            return

        self.price_lbl.setText(f"Spot: {_fmt_num(float(p), 2)}")
        as_of = self.state.get("quote_as_of_sec")
        src = self.state.get("quote_source")
        src_label = "quote snapshot" if src == "quote" else "last 1m bar"
        if as_of:
            dt = datetime.fromtimestamp(int(as_of)).astimezone()
            self.price_asof_lbl.setText(f"Yahoo {src_label} as of {dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        else:
            self.price_asof_lbl.setText("Yahoo time stamp unavailable.")

    def _refresh_price(self) -> None:
        self.refresh_btn.setEnabled(False)
        self.price_asof_lbl.setText("Refreshing quote...")
        try:
            q = fetch_yahoo_quote(self.state["ticker"])
            self.state["price"] = q.price
            self.state["quote_as_of_sec"] = q.as_of_sec
            self.state["quote_source"] = q.source
            self.state["live_ok"] = True
        except Exception as exc:
            self.state["price"] = None
            self.state["quote_as_of_sec"] = None
            self.state["quote_source"] = None
            self.state["live_ok"] = False
            QMessageBox.warning(self, "Quote Fetch Failed", f"Could not fetch Yahoo quote.\n\n{exc}\n\nUse override spot.")
        finally:
            self.refresh_btn.setEnabled(True)

        self._update_price_label()
        self._recompute_suggestions()
        if self._legs_strikes_empty():
            self._apply_suggestions_to_legs()
        self._update_metrics()

    def _legs_strikes_empty(self) -> bool:
        for w in [self.lp_k_edit, self.sp_k_edit, self.sc_k_edit, self.lc_k_edit]:
            v = _parse_float(w.text())
            if v is not None:
                return False
        return True

    def _sync_wings_from_suggested_shorts(self) -> None:
        wing = int(self.state["wing"])
        ssp = _parse_float(self.sug_sp_edit.text())
        ssc = _parse_float(self.sug_sc_edit.text())
        self.sug_lp_edit.blockSignals(True)
        self.sug_lc_edit.blockSignals(True)
        self.sug_lp_edit.setText("" if ssp is None else str(int(round(ssp - wing))))
        self.sug_lc_edit.setText("" if ssc is None else str(int(round(ssc + wing))))
        self.sug_lp_edit.blockSignals(False)
        self.sug_lc_edit.blockSignals(False)

    def _recompute_suggestions(self) -> None:
        p = self._effective_price()
        iv = _parse_float(self.iv_edit.text())
        aggr = self.aggr_slider.value() / 100.0
        aggr = max(0.25, min(1.0, aggr))
        self.aggr_lbl.setText(f"Aggressiveness: {aggr:.2f} x intraday 1SD")

        if p is None or iv is None or iv <= 0:
            self.sug_sp_edit.setText("")
            self.sug_sc_edit.setText("")
            self.sug_lp_edit.setText("")
            self.sug_lc_edit.setText("")
            self.band_lbl.setText("Suggested short band: +/-$- -> -")
            self.prob_lbl.setText("Approx inside probability: -")
            self._update_suggested_ticket_preview()
            return

        sd = one_sd_dollars(p, iv)
        if sd is None:
            return

        band = sd * aggr
        low = p - band
        high = p + band
        wing = int(self.state["wing"])

        ssp = round_strike(low, wing)
        ssc = round_strike(high, wing)
        slp = ssp - wing
        slc = ssc + wing

        for w, v in [
            (self.sug_sp_edit, ssp),
            (self.sug_sc_edit, ssc),
            (self.sug_lp_edit, slp),
            (self.sug_lc_edit, slc),
        ]:
            w.blockSignals(True)
            w.setText(str(v))
            w.blockSignals(False)

        inside_pct = (normal_cdf(aggr) - normal_cdf(-aggr)) * 100.0
        self.band_lbl.setText(f"Suggested short band: +/-${band:,.2f} -> ${low:,.2f} to ${high:,.2f}")
        self.prob_lbl.setText(f"Approx inside probability: {inside_pct:.0f}% (normal approx)")
        self._update_suggested_ticket_preview()

    def _exp_label(self) -> str:
        return datetime.now().strftime("%d %b %y").upper() + " (Weeklys)"

    def _update_suggested_ticket_preview(self) -> None:
        qty = int(self.contracts_spin.value())
        symbol = self.state["name"]
        exp = self._exp_label()

        sc = _parse_float(self.sug_sc_edit.text())
        lc = _parse_float(self.sug_lc_edit.text())
        sp = _parse_float(self.sug_sp_edit.text())
        lp = _parse_float(self.sug_lp_edit.text())

        rows = [
            ("IRON CONDOR", "SELL", f"-{qty}", "AUTO", symbol, exp, sc, "CALL"),
            ("", "BUY", f"+{qty}", "AUTO", symbol, exp, lc, "CALL"),
            ("", "SELL", f"-{qty}", "AUTO", symbol, exp, sp, "PUT"),
            ("", "BUY", f"+{qty}", "AUTO", symbol, exp, lp, "PUT"),
        ]

        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                if isinstance(val, (int, float)):
                    cell_text = _fmt_num(float(val), 0)
                else:
                    cell_text = str(val if val is not None else DASH)
                item = QTableWidgetItem(cell_text)
                self.suggested_ticket_table.setItem(r, c, item)

        self.suggested_ticket_table.resizeColumnsToContents()

    def _apply_suggestions_to_legs(self) -> None:
        mapping = [
            (self.sp_k_edit, self.sug_sp_edit),
            (self.lp_k_edit, self.sug_lp_edit),
            (self.sc_k_edit, self.sug_sc_edit),
            (self.lc_k_edit, self.sug_lc_edit),
        ]
        for leg, sug in mapping:
            v = sug.text().strip()
            if v:
                leg.setText(v)
        self._update_metrics()

    def _clear_metrics(self) -> None:
        for lbl in self.metric_labels.values():
            lbl.setText(DASH)

    def _update_metrics(self) -> None:
        self._update_price_label()

        sp_k = _parse_float(self.sp_k_edit.text())
        lp_k = _parse_float(self.lp_k_edit.text())
        sc_k = _parse_float(self.sc_k_edit.text())
        lc_k = _parse_float(self.lc_k_edit.text())

        sp_r = _parse_float(self.sp_p_edit.text())
        lp_p = _parse_float(self.lp_p_edit.text())
        sc_r = _parse_float(self.sc_p_edit.text())
        lc_p = _parse_float(self.lc_p_edit.text())

        contracts = int(self.contracts_spin.value())

        vals = [sp_k, lp_k, sc_k, lc_k, sp_r, lp_p, sc_r, lc_p]
        if any(v is None for v in vals):
            self.strike_error_lbl.setText("")
            self._clear_metrics()
            self.chart.draw_empty()
            return

        assert sp_k is not None and lp_k is not None and sc_k is not None and lc_k is not None
        assert sp_r is not None and lp_p is not None and sc_r is not None and lc_p is not None

        if not (lp_k < sp_k < sc_k < lc_k):
            self.strike_error_lbl.setText(
                "Strikes must be ordered: long put < short put < short call < long call."
            )
            self._clear_metrics()
            self.chart.draw_empty()
            return

        self.strike_error_lbl.setText("")

        net = sp_r + sc_r - lp_p - lc_p
        put_w = sp_k - lp_k
        call_w = lc_k - sc_k
        max_loss_per_share = max(put_w, call_w) - net

        max_profit = net * 100.0 * contracts
        max_loss = max(0.0, max_loss_per_share) * 100.0 * contracts
        lbe = sp_k - net
        ube = sc_k + net
        zone = ube - lbe
        rr = (max_loss / max_profit) if max_profit > 0 else None

        p0 = self._effective_price()
        iv = _parse_float(self.iv_edit.text())
        sigma = one_sd_dollars(p0, iv) if (p0 is not None and iv is not None and iv > 0) else None
        pop = pop_profit_zone(p0, sigma, lbe, ube) if (p0 is not None and sigma is not None) else None

        self.metric_labels["net"].setText(_fmt_money(net))
        self.metric_labels["max_profit"].setText(_fmt_money(max_profit))
        self.metric_labels["max_loss"].setText(_fmt_money(max_loss))
        self.metric_labels["lbe"].setText(_fmt_num(lbe, 2))
        self.metric_labels["ube"].setText(_fmt_num(ube, 2))
        self.metric_labels["zone"].setText(_fmt_num(zone, 2))
        self.metric_labels["rr"].setText(_fmt_num(rr, 2) if rr is not None else DASH)
        self.metric_labels["pop"].setText(_fmt_pct(pop * 100.0) if pop is not None else DASH)

        if p0 is None:
            self.chart.draw_empty()
            return

        self.chart.draw_payoff(
            {
                "lp_k": lp_k,
                "sp_k": sp_k,
                "sc_k": sc_k,
                "lc_k": lc_k,
                "sp_r": sp_r,
                "lp_p": lp_p,
                "sc_r": sc_r,
                "lc_p": lc_p,
                "contracts": contracts,
                "lbe": lbe,
                "ube": ube,
                "p0": p0,
                "sigma": sigma,
            }
        )

    def _parse_trade_legs(self, text: str) -> tuple[Optional[list[dict[str, Any]]], Optional[str], Optional[str]]:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) != 4:
            return None, None, "Enter exactly four non-empty legs lines."

        legs = []
        rx = re.compile(r"^(\d+(?:\.\d+)?)\s+(CALL|PUT)$", re.IGNORECASE)
        for i, line in enumerate(lines, start=1):
            m = rx.match(line)
            if not m:
                return None, None, f'Line {i} must look like "6465 CALL" or "6390 PUT".'
            legs.append({"strike": float(m.group(1)), "right": m.group(2).upper()})

        return legs, "\n".join(lines), None

    def _parse_contracts_line(self, text: str) -> tuple[Optional[int], Optional[str], Optional[str]]:
        t = (text or "").strip()
        m = re.match(r"^(\d+)\s+(.+)$", t)
        if not m:
            return None, None, 'Use format: number then symbol, e.g. "3 SPX".'
        qty = int(m.group(1))
        symbol = re.sub(r"\s+", "", m.group(2)).strip()[:32]
        if qty < 1:
            return None, None, "Contract count must be a positive integer."
        if not symbol:
            return None, None, "Symbol missing after count."
        return qty, symbol, None

    def _save_trade(self) -> None:
        legs, legs_text, err = self._parse_trade_legs(self.trade_legs_input.toPlainText())
        if err:
            self.trade_status_lbl.setText(err)
            self.trade_status_lbl.setStyleSheet("color:#b91c1c;")
            return

        qty, sym, err2 = self._parse_contracts_line(self.trade_contracts_line.text())
        if err2:
            self.trade_status_lbl.setText(err2)
            self.trade_status_lbl.setStyleSheet("color:#b91c1c;")
            return

        body = {
            "legsText": legs_text,
            "legs": legs,
            "breakEvenLower": self.trade_break_l_edit.text(),
            "breakEvenUpper": self.trade_break_u_edit.text(),
            "maxProfit": self.trade_max_p_edit.text(),
            "maxLoss": self.trade_max_l_edit.text(),
            "contractsQty": qty,
            "contractsSymbol": sym,
            "notes": self.trade_notes_edit.text(),
        }

        self.store.add_trade(body)
        self.trade_status_lbl.setText("Trade saved to data/trades.json")
        self.trade_status_lbl.setStyleSheet("color:#166534;")

        self.trade_legs_input.clear()
        self.trade_break_l_edit.clear()
        self.trade_break_u_edit.clear()
        self.trade_max_p_edit.clear()
        self.trade_max_l_edit.clear()
        self.trade_contracts_line.clear()
        self.trade_notes_edit.clear()

        self._load_trades()

    def _trade_matches_filter(self, saved_at_iso: str, filter_key: str) -> bool:
        dt = _iso_to_local(saved_at_iso)
        if dt is None:
            return False
        now = datetime.now().astimezone()

        start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_yesterday = start_today - timedelta(days=1)
        start_7 = start_today - timedelta(days=7)
        start_30 = start_today - timedelta(days=30)

        if filter_key == "all":
            return True
        if filter_key == "today":
            return dt.date() == start_today.date()
        if filter_key == "yesterday":
            return dt.date() == start_yesterday.date()
        if filter_key == "last7":
            return dt >= start_7
        if filter_key == "last30":
            return dt >= start_30
        return True

    def _load_trades(self) -> None:
        self.cached_trades = self.store.list_sorted()
        self._render_trade_list()

    def _render_trade_list(self) -> None:
        key = self.filter_combo.currentData()
        rows = [t for t in self.cached_trades if self._trade_matches_filter(str(t.get("savedAt", "")), key)]

        self.trade_table.setRowCount(len(rows))
        for row_idx, tr in enumerate(rows):
            dt = _iso_to_local(str(tr.get("savedAt", "")))
            when = dt.strftime("%Y-%m-%d %H:%M") if dt else "-"

            qty_sym = f"{tr.get('contractsQty', '-') } x {tr.get('contractsSymbol', '-') }"
            legs = tr.get("legs") or []
            legs_str = " | ".join([f"{l.get('strike')} {l.get('right')}" for l in legs])

            be_l = tr.get("breakEvenLower")
            be_u = tr.get("breakEvenUpper")
            be_str = f"{_fmt_num(be_l, 2) if isinstance(be_l, (int, float)) else '-'} - {_fmt_num(be_u, 2) if isinstance(be_u, (int, float)) else '-'}"

            mp = tr.get("maxProfit")
            ml = tr.get("maxLoss")
            pl_str = f"{_fmt_money(mp if isinstance(mp, (int, float)) else None)} / {_fmt_money(ml if isinstance(ml, (int, float)) else None)}"

            notes = str(tr.get("notes", ""))

            items = [
                QTableWidgetItem(when),
                QTableWidgetItem(qty_sym),
                QTableWidgetItem(legs_str),
                QTableWidgetItem(be_str),
                QTableWidgetItem(pl_str),
                QTableWidgetItem(notes),
            ]
            for col, item in enumerate(items):
                item.setData(Qt.UserRole, tr.get("id"))
                self.trade_table.setItem(row_idx, col, item)

        self.trade_table.resizeColumnsToContents()

    def _delete_selected_trade(self) -> None:
        selected = self.trade_table.selectionModel().selectedRows()
        if not selected:
            self.trade_status_lbl.setText("Select a trade row to delete.")
            self.trade_status_lbl.setStyleSheet("color:#b91c1c;")
            return

        row = selected[0].row()
        item = self.trade_table.item(row, 0)
        if not item:
            return
        trade_id = item.data(Qt.UserRole)
        if not trade_id:
            return

        ok = self.store.delete_trade(str(trade_id))
        if ok:
            self.trade_status_lbl.setText("Trade deleted.")
            self.trade_status_lbl.setStyleSheet("color:#166534;")
            self._load_trades()
        else:
            self.trade_status_lbl.setText("Trade id not found.")
            self.trade_status_lbl.setStyleSheet("color:#b91c1c;")
