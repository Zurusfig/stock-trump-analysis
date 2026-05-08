"""Tab 5 — Asset Comparison: side-by-side, correlation matrix, best per asset."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st
from backtest import StrategyResult

PALETTE = px.colors.qualitative.Plotly


def render_comparison(results: list[StrategyResult]) -> None:
    tickers = list(dict.fromkeys(r.ticker for r in results))
    if len(tickers) < 2:
        st.info("Select at least 2 tickers to compare assets.")
        if tickers:
            # Still show best strategy per ticker
            _best_per_ticker(results, tickers)
        return

    # ── Strategy selector ─────────────────────────────────────────────────────
    all_strategy_names = sorted(
        {r.name for r in results if r.metrics},
        key=lambda n: n,
    )
    selected_strategy = st.selectbox(
        "Compare strategy across assets:", all_strategy_names, key="comp_strat"
    )

    # ── Side-by-side cumulative returns ───────────────────────────────────────
    st.subheader(f"Cumulative Returns — {selected_strategy}")
    cols = st.columns(min(len(tickers), 2))  # max 2 per row — stacks on mobile
    for i, ticker in enumerate(tickers):
        result = next(
            (r for r in results if r.ticker == ticker and r.name == selected_strategy), None
        )
        with cols[i % len(cols)]:
            if result and result.metrics:
                m = result.metrics
                ret = m["total_return_pct"]
                color = "#2ecc71" if ret >= 0 else "#e74c3c"
                st.markdown(
                    f"**{ticker}** &nbsp; "
                    f"<span style='color:{color};font-size:1.3em;font-weight:bold'>{ret:+.2f}%</span>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"Sharpe: {m['sharpe_ratio']:.3f} | "
                    f"Max DD: {m['max_drawdown_pct']:.2f}% | "
                    f"Trades: {m['num_trades']}"
                )
            else:
                st.markdown(f"**{ticker}** — no data")

    # Multi-line chart for the selected strategy across all tickers
    fig = go.Figure()
    for i, ticker in enumerate(tickers):
        result = next(
            (r for r in results if r.ticker == ticker and r.name == selected_strategy), None
        )
        if not result:
            continue
        ec = result.equity_curve.dropna()
        if ec.empty or result.total_invested == 0:
            continue
        pct = (ec / result.total_invested - 1) * 100
        fig.add_trace(go.Scatter(
            x=pct.index, y=pct.values,
            name=ticker, mode="lines",
            line=dict(color=PALETTE[i % len(PALETTE)], width=2.5),
            hovertemplate="%{x|%Y-%m-%d}<br>Return: %{y:.2f}%<extra>" + ticker + "</extra>",
        ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.4)
    fig.update_layout(
        template="plotly_dark", hovermode="x unified",
        legend=dict(orientation="h", y=1.05),
        xaxis_title="Date", yaxis_title="Return (%)",
        margin=dict(l=0, r=0, t=40, b=0), height=380,
    )
    st.plotly_chart(fig, use_container_width=True, config={"responsive": True, "displayModeBar": False, "scrollZoom": False})

    # ── All-strategy return heatmap ───────────────────────────────────────────
    st.subheader("Total Return (%) — Strategy × Asset")
    strat_names = sorted({r.name for r in results if r.metrics})
    heat_data = []
    for strat in strat_names:
        row = {}
        for ticker in tickers:
            result = next(
                (r for r in results if r.ticker == ticker and r.name == strat), None
            )
            row[ticker] = result.metrics.get("total_return_pct", np.nan) if result and result.metrics else np.nan
        heat_data.append(row)

    heat_df = pd.DataFrame(heat_data, index=strat_names)
    fig_heat = go.Figure(go.Heatmap(
        z=heat_df.values,
        x=heat_df.columns.tolist(),
        y=heat_df.index.tolist(),
        colorscale=[[0, "#e74c3c"], [0.5, "#333344"], [1, "#2ecc71"]],
        zmid=0,
        text=[[f"{v:+.1f}%" if not np.isnan(v) else "N/A" for v in row] for row in heat_df.values],
        texttemplate="%{text}",
        hovertemplate="Strategy: %{y}<br>Ticker: %{x}<br>Return: %{z:+.2f}%<extra></extra>",
    ))
    fig_heat.update_layout(
        template="plotly_dark",
        xaxis_title="Ticker", yaxis_title="Strategy",
        margin=dict(l=0, r=0, t=20, b=0),
        height=max(300, len(strat_names) * 50),
    )
    st.plotly_chart(fig_heat, use_container_width=True, config={"responsive": True, "displayModeBar": False, "scrollZoom": False})

    # ── Equity curve correlation ───────────────────────────────────────────────
    st.subheader("Equity Curve Correlation (Daily Returns)")
    ec_map: dict[str, pd.Series] = {}
    for ticker in tickers:
        r = next((x for x in results if x.ticker == ticker and x.name == selected_strategy), None)
        if r:
            ec = r.equity_curve.dropna()
            ec_nz = ec[ec > 0]
            if len(ec_nz) > 10:
                ec_map[ticker] = ec_nz.pct_change().dropna()

    if len(ec_map) >= 2:
        combined = pd.DataFrame(ec_map).dropna()
        corr = combined.corr()
        fig_corr = go.Figure(go.Heatmap(
            z=corr.values,
            x=corr.columns.tolist(),
            y=corr.index.tolist(),
            colorscale="RdBu",
            zmin=-1, zmax=1,
            text=[[f"{v:.2f}" for v in row] for row in corr.values],
            texttemplate="%{text}",
            hovertemplate="%{y} vs %{x}: %{z:.3f}<extra></extra>",
        ))
        fig_corr.update_layout(
            template="plotly_dark",
            margin=dict(l=0, r=0, t=20, b=0), height=300,
        )
        st.plotly_chart(fig_corr, use_container_width=True, config={"responsive": True, "displayModeBar": False, "scrollZoom": False})

    _best_per_ticker(results, tickers)


def _best_per_ticker(results: list[StrategyResult], tickers: list[str]) -> None:
    st.subheader("Best Strategy per Asset")
    cols = st.columns(min(len(tickers), 2))
    for i, ticker in enumerate(tickers):
        tr = [r for r in results if r.ticker == ticker and r.metrics]
        with cols[i]:
            if tr:
                best = max(tr, key=lambda r: r.metrics.get("total_return_pct", -999))
                m = best.metrics
                ret = m["total_return_pct"]
                color = "#2ecc71" if ret >= 0 else "#e74c3c"
                st.markdown(
                    f"### {ticker}\n"
                    f"**{m['strategy']}**\n\n"
                    f"<span style='color:{color};font-size:1.4em'>{ret:+.2f}%</span>",
                    unsafe_allow_html=True,
                )
                st.caption(f"Sharpe {m['sharpe_ratio']:.3f} | {m['num_trades']} trades")
