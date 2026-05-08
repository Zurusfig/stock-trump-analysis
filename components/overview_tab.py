"""Tab 1 — Overview: KPI cards + leaderboard table + winner callout."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from backtest import StrategyResult


def _fmt(val: float, prefix: str = "", suffix: str = "", signed: bool = False) -> str:
    sign = "+" if signed and val >= 0 else ""
    return f"{prefix}{sign}{val:,.2f}{suffix}"


def render_overview(results: list[StrategyResult], ticker: str) -> None:
    tr = [r for r in results if r.ticker == ticker and r.metrics]
    if not tr:
        st.info(f"No results available for {ticker}.")
        return

    sorted_r = sorted(tr, key=lambda r: r.metrics.get("total_return_pct", -999), reverse=True)
    best = sorted_r[0]
    worst = sorted_r[-1]

    # ── KPI grid — 2×2 so it stacks cleanly on mobile ───────────────────────
    bm = best.metrics
    wm = worst.metrics
    spread = bm["total_return_pct"] - wm["total_return_pct"]
    trading_days = max((len(r.equity_curve.dropna()) for r in tr), default=0)

    row1_c1, row1_c2 = st.columns(2)
    row1_c1.metric(
        "🥇 Best Strategy",
        bm["strategy"],
        f"{bm['total_return_pct']:+.2f}%",
    )
    row1_c2.metric(
        "📉 Worst Strategy",
        wm["strategy"],
        f"{wm['total_return_pct']:+.2f}%",
        delta_color="inverse",
    )

    row2_c1, row2_c2 = st.columns(2)
    row2_c1.metric("↔️ Return Spread", f"{spread:.1f} pp")
    row2_c2.metric("📅 Trading Days", f"{trading_days:,}")

    st.markdown("---")

    # ── Winner callout (broken into two lines so it wraps cleanly) ───────────
    st.success(
        f"**Winner for {ticker}:** {bm['strategy']}  \n"
        f"Return **{bm['total_return_pct']:+.2f}%** · "
        f"Sharpe **{bm['sharpe_ratio']:.3f}** · "
        f"Max DD **{bm['max_drawdown_pct']:.2f}%** · "
        f"{bm['num_trades']} trades"
    )

    # ── Leaderboard table ────────────────────────────────────────────────────
    st.subheader(f"Strategy Leaderboard — {ticker}")

    rows = []
    for rank, r in enumerate(sorted_r, 1):
        m = r.metrics
        win_rate = m["win_rate_pct"]
        rows.append({
            "Rank": rank,
            "Strategy": m["strategy"],
            "Invested $": m["total_invested"],
            "Final Value $": m["final_value"],
            "P&L $": m["total_pnl"],
            "Return %": m["total_return_pct"],
            "Ann. Return %": m["annualised_return_pct"],
            "Win Rate %": win_rate if win_rate != "N/A" else None,
            "Max DD %": m["max_drawdown_pct"],
            "Sharpe": m["sharpe_ratio"],
            "Sortino": m["sortino_ratio"],
            "Trades": m["num_trades"],
            "Costs $": m["total_transaction_costs"],
        })

    df = pd.DataFrame(rows)

    def _color_return(val):
        if isinstance(val, (int, float)):
            color = "#2ecc71" if val >= 0 else "#e74c3c"
            return f"color: {color}; font-weight: bold"
        return ""

    styled = (
        df.style
        .applymap(_color_return, subset=["Return %", "Ann. Return %", "P&L $"])
        .format({
            "Invested $": "${:,.0f}",
            "Final Value $": "${:,.0f}",
            "P&L $": "${:+,.0f}",
            "Return %": "{:+.2f}%",
            "Ann. Return %": "{:+.2f}%",
            "Win Rate %": lambda v: f"{v:.1f}%" if v is not None else "N/A",
            "Max DD %": "{:.2f}%",
            "Sharpe": "{:.3f}",
            "Sortino": "{:.3f}",
            "Costs $": "${:,.2f}",
        }, na_rep="N/A")
        .set_properties(**{"text-align": "right"})
        .set_table_styles([{
            "selector": "th",
            "props": [("text-align", "center"), ("font-weight", "bold")],
        }])
    )

    st.dataframe(styled, use_container_width=True, hide_index=True)
