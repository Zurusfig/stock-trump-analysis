"""Tab 2 — Performance Charts: cumulative returns, drawdown, distributions."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from backtest import StrategyResult

PALETTE = px.colors.qualitative.Plotly


def _equity_pct(result: StrategyResult) -> pd.Series:
    ec = result.equity_curve.dropna()
    if ec.empty or result.total_invested == 0:
        return pd.Series(dtype=float)
    return (ec / result.total_invested - 1) * 100


def render_performance(results: list[StrategyResult], ticker: str) -> None:
    tr = [r for r in results if r.ticker == ticker and r.metrics]
    if not tr:
        st.info(f"No results for {ticker}.")
        return

    # ── Cumulative returns ───────────────────────────────────────────────────
    st.subheader("Cumulative Returns")
    fig_cum = go.Figure()
    for i, r in enumerate(tr):
        pct = _equity_pct(r)
        if pct.empty:
            continue
        fig_cum.add_trace(go.Scatter(
            x=pct.index, y=pct.values,
            name=r.name, mode="lines",
            line=dict(color=PALETTE[i % len(PALETTE)], width=2),
            hovertemplate="%{x|%Y-%m-%d}<br>Return: %{y:.2f}%<extra>" + r.name + "</extra>",
        ))
    fig_cum.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig_cum.update_layout(
        template="plotly_dark",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis_title="Date", yaxis_title="Return (%)",
        margin=dict(l=0, r=0, t=40, b=0),
        height=420,
    )
    st.plotly_chart(fig_cum, use_container_width=True, config={"responsive": True, "displayModeBar": False, "scrollZoom": False})

    # ── Drawdown ──────────────────────────────────────────────────────────────
    st.subheader("Drawdown Over Time")
    fig_dd = go.Figure()
    for i, r in enumerate(tr):
        ec = r.equity_curve.dropna()
        if ec.empty or ec.max() == 0:
            continue
        rolling_max = ec.cummax()
        dd = (ec - rolling_max) / rolling_max * 100
        fig_dd.add_trace(go.Scatter(
            x=dd.index, y=dd.values,
            name=r.name, mode="lines",
            fill="tozeroy",
            line=dict(color=PALETTE[i % len(PALETTE)], width=1.5),
            fillcolor=f"rgba{tuple(list(px.colors.hex_to_rgb(PALETTE[i % len(PALETTE)])) + [0.15])}",
            hovertemplate="%{x|%Y-%m-%d}<br>DD: %{y:.2f}%<extra>" + r.name + "</extra>",
        ))
    fig_dd.add_hline(y=0, line_color="gray", opacity=0.3)
    fig_dd.update_layout(
        template="plotly_dark", hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis_title="Date", yaxis_title="Drawdown (%)",
        margin=dict(l=0, r=0, t=40, b=0), height=380,
    )
    st.plotly_chart(fig_dd, use_container_width=True, config={"responsive": True, "displayModeBar": False, "scrollZoom": False})

    # ── Daily return distributions ────────────────────────────────────────────
    st.subheader("Daily Return Distribution")
    fig_hist = go.Figure()
    for i, r in enumerate(tr):
        ec = r.equity_curve.dropna()
        ec_nz = ec[ec > 0]
        if len(ec_nz) < 5:
            continue
        daily_ret = ec_nz.pct_change().dropna().replace([np.inf, -np.inf], np.nan).dropna() * 100
        fig_hist.add_trace(go.Histogram(
            x=daily_ret.values, name=r.name,
            opacity=0.65, nbinsx=50,
            marker_color=PALETTE[i % len(PALETTE)],
            hovertemplate="Return: %{x:.2f}%<br>Count: %{y}<extra>" + r.name + "</extra>",
        ))
    fig_hist.update_layout(
        barmode="overlay", template="plotly_dark",
        xaxis_title="Daily Return (%)", yaxis_title="Frequency",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=0, r=0, t=40, b=0), height=350,
    )
    st.plotly_chart(fig_hist, use_container_width=True, config={"responsive": True, "displayModeBar": False, "scrollZoom": False})
