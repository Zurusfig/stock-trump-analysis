"""Sidebar controls — returns a config dict consumed by app.py."""
from __future__ import annotations

from datetime import date, timedelta
import streamlit as st
from backtest import STRATEGY_MAP
from utils.data_loader import AVAILABLE_TICKERS

STRATEGY_LABELS = {
    "weekend":    "Weekend (Fri→Mon)",
    "buyhold":    "Buy & Hold",
    "dca":        "Weekly/DCA",
    "macrossover":"MA Crossover",
    "rsi":        "RSI Mean Reversion",
    "monthlydca": "Monthly DCA",
}

STRATEGY_DESCRIPTIONS = {
    "weekend":    "Buy at Friday close, sell at Monday close",
    "buyhold":    "Lump sum at start, hold until end",
    "dca":        "Fixed amount every week/biweek/month",
    "macrossover":"Enter on Golden Cross, exit on Death Cross",
    "rsi":        "Buy oversold (RSI<30), sell overbought (RSI>70)",
    "monthlydca": "$4× capital on first trading day of each month",
}


def render_sidebar() -> dict:
    st.sidebar.image(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a9/Trump_White_House_Portraits_%28cropped%29.jpg/220px-Trump_White_House_Portraits_%28cropped%29.jpg",
        width=60,
    ) if False else None  # placeholder — skip external image in sandbox

    st.sidebar.title("⚙️ Backtest Controls")

    # ── Date range ──────────────────────────────────────────────────────────
    st.sidebar.subheader("📅 Date Range")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input(
            "Start", value=date(2025, 1, 20),
            min_value=date(2020, 1, 1), max_value=date.today() - timedelta(days=30),
            key="start_date",
        )
    with col2:
        end_date = st.date_input(
            "End", value=date.today(),
            min_value=date(2020, 1, 2), max_value=date.today(),
            key="end_date",
        )

    if start_date >= end_date:
        st.sidebar.error("Start date must be before end date.")

    # ── Assets ──────────────────────────────────────────────────────────────
    st.sidebar.subheader("📈 Assets")
    ticker_options = list(AVAILABLE_TICKERS.keys())
    ticker_display = [f"{k} — {v}" for k, v in AVAILABLE_TICKERS.items()]
    default_idx = [0, 1]  # ^GSPC, GLD
    selected_display = st.sidebar.multiselect(
        "Select tickers", ticker_display, default=[ticker_display[i] for i in default_idx],
        key="tickers",
    )
    selected_tickers = [t.split(" — ")[0] for t in selected_display]

    if not selected_tickers:
        st.sidebar.warning("Select at least one ticker.")
        selected_tickers = ["^GSPC"]

    # ── Strategies ──────────────────────────────────────────────────────────
    st.sidebar.subheader("🎯 Strategies")
    selected_strategies: list[str] = []
    for key, label in STRATEGY_LABELS.items():
        desc = STRATEGY_DESCRIPTIONS[key]
        checked = st.sidebar.checkbox(
            label, value=True, key=f"strat_{key}",
            help=desc,
        )
        if checked:
            selected_strategies.append(key)

    if not selected_strategies:
        st.sidebar.warning("Select at least one strategy.")
        selected_strategies = ["buyhold"]

    # ── Capital ─────────────────────────────────────────────────────────────
    st.sidebar.subheader("💵 Capital Settings")
    capital = st.sidebar.number_input(
        "Per-trade capital ($)", min_value=100, max_value=100_000,
        value=1000, step=100, key="capital",
        help="Amount invested per trade signal",
    )
    tx_cost_pct = st.sidebar.slider(
        "Transaction cost (%)", min_value=0.0, max_value=0.5,
        value=0.1, step=0.01, format="%.2f%%", key="tx_cost",
        help="Round-trip cost per trade (0.1% is typical for ETFs)",
    )
    transaction_cost = tx_cost_pct / 100

    # ── Strategy-specific params ─────────────────────────────────────────────
    with st.sidebar.expander("🔧 Advanced Strategy Params", expanded=False):
        st.markdown("**RSI Settings**")
        rsi_oversold = st.slider("Oversold threshold", 10, 45, 30, key="rsi_oversold",
                                  help="Buy signal when RSI falls below this level")
        rsi_overbought = st.slider("Overbought threshold", 55, 90, 70, key="rsi_overbought",
                                    help="Sell signal when RSI rises above this level")
        rsi_period = st.slider("RSI period", 7, 28, 14, key="rsi_period")

        st.markdown("**MA Crossover Settings**")
        ma_short = st.number_input("Short MA window", 5, 100, 50, key="ma_short")
        ma_long = st.number_input("Long MA window", 50, 400, 200, key="ma_long")

        st.markdown("**DCA Settings**")
        dca_frequency = st.selectbox(
            "DCA frequency", ["weekly", "biweekly", "monthly"],
            key="dca_frequency",
            help="How often DCA purchases are made",
        )

    strategy_params = {
        "rsi": {"oversold": rsi_oversold, "overbought": rsi_overbought, "period": rsi_period},
        "macrossover": {"short_window": int(ma_short), "long_window": int(ma_long)},
        "dca": {"frequency": dca_frequency},
    }

    # ── Run button ───────────────────────────────────────────────────────────
    st.sidebar.markdown("---")
    run = st.sidebar.button("▶ Run Backtest", type="primary", use_container_width=True)

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "tickers": selected_tickers,
        "strategies": selected_strategies,
        "capital": float(capital),
        "transaction_cost": transaction_cost,
        "strategy_params": strategy_params,
        "run": run,
    }
