"""Tab 3 — Risk Analysis: scatter plots, volatility, Sharpe vs Sortino."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from backtest import StrategyResult

PALETTE = px.colors.qualitative.Plotly


def render_risk(results: list[StrategyResult], ticker: str) -> None:
    tr = [r for r in results if r.ticker == ticker and r.metrics]
    if not tr:
        st.info(f"No results for {ticker}.")
        return

    # ── Risk-return scatter ──────────────────────────────────────────────────
    st.subheader("Risk-Return Scatter (Sharpe vs Total Return)")

    names, sharpes, returns, trades_cnt, sortinos = [], [], [], [], []
    for r in tr:
        m = r.metrics
        names.append(m["strategy"])
        sharpes.append(m["sharpe_ratio"])
        returns.append(m["total_return_pct"])
        trades_cnt.append(max(m["num_trades"], 1))
        sortinos.append(m["sortino_ratio"])

    fig_scatter = go.Figure()
    for i, (name, sh, ret, nt) in enumerate(zip(names, sharpes, returns, trades_cnt)):
        fig_scatter.add_trace(go.Scatter(
            x=[sh], y=[ret],
            mode="markers+text",
            name=name,
            text=[name],
            textposition="top center",
            marker=dict(
                size=max(12, min(40, nt ** 0.4 * 4)),
                color=PALETTE[i % len(PALETTE)],
                opacity=0.85,
                line=dict(width=1, color="white"),
            ),
            hovertemplate=(
                f"<b>{name}</b><br>"
                "Sharpe: %{x:.3f}<br>"
                "Return: %{y:.2f}%<br>"
                f"Trades: {nt}<extra></extra>"
            ),
        ))
    fig_scatter.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.4)
    fig_scatter.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.4)
    fig_scatter.update_layout(
        template="plotly_dark",
        showlegend=False,
        xaxis_title="Sharpe Ratio",
        yaxis_title="Total Return (%)",
        margin=dict(l=0, r=0, t=40, b=0), height=420,
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    col1, col2 = st.columns(2)

    # ── Volatility (annualised daily std) ────────────────────────────────────
    with col1:
        st.subheader("Annualised Volatility")
        vols = {}
        for r in tr:
            ec = r.equity_curve.dropna()
            ec_nz = ec[ec > 0]
            if len(ec_nz) < 5:
                vols[r.name] = 0.0
                continue
            dr = ec_nz.pct_change().dropna().replace([np.inf, -np.inf], np.nan).dropna()
            vols[r.name] = float(dr.std() * np.sqrt(252) * 100)

        sorted_vols = dict(sorted(vols.items(), key=lambda x: x[1], reverse=True))
        fig_vol = go.Figure(go.Bar(
            x=list(sorted_vols.values()),
            y=list(sorted_vols.keys()),
            orientation="h",
            marker_color=PALETTE[:len(sorted_vols)],
            hovertemplate="%{y}: %{x:.2f}%<extra></extra>",
        ))
        fig_vol.update_layout(
            template="plotly_dark",
            xaxis_title="Annualised Volatility (%)",
            margin=dict(l=0, r=0, t=30, b=0), height=300,
        )
        st.plotly_chart(fig_vol, use_container_width=True)

    # ── Sharpe vs Sortino ─────────────────────────────────────────────────────
    with col2:
        st.subheader("Sharpe vs Sortino")
        fig_ss = go.Figure()
        x_pos = list(range(len(tr)))
        fig_ss.add_trace(go.Bar(
            x=[r.metrics["strategy"] for r in tr],
            y=[r.metrics["sharpe_ratio"] for r in tr],
            name="Sharpe", marker_color="#2196F3", opacity=0.85,
        ))
        fig_ss.add_trace(go.Bar(
            x=[r.metrics["strategy"] for r in tr],
            y=[r.metrics["sortino_ratio"] for r in tr],
            name="Sortino", marker_color="#FF9800", opacity=0.85,
        ))
        fig_ss.update_layout(
            template="plotly_dark", barmode="group",
            xaxis_tickangle=-30,
            margin=dict(l=0, r=0, t=30, b=60), height=300,
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig_ss, use_container_width=True)

    # ── Max drawdown comparison ───────────────────────────────────────────────
    st.subheader("Max Drawdown Comparison")
    sorted_dd = sorted(tr, key=lambda r: r.metrics.get("max_drawdown_pct", 0))
    fig_dd_bar = go.Figure(go.Bar(
        x=[r.metrics["strategy"] for r in sorted_dd],
        y=[r.metrics["max_drawdown_pct"] for r in sorted_dd],
        marker_color=[PALETTE[i % len(PALETTE)] for i in range(len(sorted_dd))],
        hovertemplate="%{x}<br>Max DD: %{y:.2f}%<extra></extra>",
    ))
    fig_dd_bar.update_layout(
        template="plotly_dark",
        yaxis_title="Max Drawdown (%)",
        margin=dict(l=0, r=0, t=30, b=80), height=320,
        xaxis_tickangle=-30,
    )
    st.plotly_chart(fig_dd_bar, use_container_width=True)
