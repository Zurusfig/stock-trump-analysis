"""Tab 4 — Trade Explorer: filterable log, P&L bars, win/loss pie, calendar."""
from __future__ import annotations

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from backtest import StrategyResult

PALETTE = px.colors.qualitative.Plotly


def render_trades(results: list[StrategyResult], ticker: str) -> None:
    tr = [r for r in results if r.ticker == ticker and r.metrics and r.trades]
    if not tr:
        st.info(f"No trade data available for {ticker}.")
        return

    strategy_names = [r.name for r in tr]
    selected_name = st.selectbox("Select Strategy", strategy_names, key=f"trade_sel_{ticker}")
    result = next(r for r in tr if r.name == selected_name)

    # Build trade DataFrame
    trade_rows = [t.to_dict() for t in result.trades]
    df = pd.DataFrame(trade_rows)
    if df.empty:
        st.info("No trades recorded for this strategy.")
        return

    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    df["return_pct"] = (df["exit_price"] / df["entry_price"] - 1) * 100
    df["hold_days"] = (df["exit_date"] - df["entry_date"]).dt.days
    df["result"] = df["pnl"].apply(lambda x: "Win" if x > 0 else "Loss")

    # ── Summary KPIs — 2×2 grid for mobile ───────────────────────────────────
    wins = (df["pnl"] > 0).sum()
    losses = (df["pnl"] <= 0).sum()
    avg_pnl = df["pnl"].mean()
    total_pnl = df["pnl"].sum()

    km1, km2 = st.columns(2)
    km1.metric("Total Trades", len(df))
    km2.metric("Win Rate", f"{wins / len(df) * 100:.1f}%", f"{wins}W / {losses}L")
    km3, km4 = st.columns(2)
    km3.metric("Avg P&L / Trade", f"${avg_pnl:+,.2f}")
    km4.metric("Total P&L", f"${total_pnl:+,.2f}")

    # ── Filters ──────────────────────────────────────────────────────────────
    with st.expander("🔍 Filter Trades", expanded=False):
        fcol1, fcol2, fcol3 = st.columns([1, 1, 1])
        with fcol1:
            result_filter = st.multiselect("Result", ["Win", "Loss"], default=["Win", "Loss"],
                                            key=f"res_filter_{ticker}")
        with fcol2:
            min_pnl = st.number_input("Min P&L ($)", value=float(df["pnl"].min()),
                                       key=f"min_pnl_{ticker}")
        with fcol3:
            max_pnl = st.number_input("Max P&L ($)", value=float(df["pnl"].max()),
                                       key=f"max_pnl_{ticker}")

    filtered = df[
        df["result"].isin(result_filter) &
        (df["pnl"] >= min_pnl) &
        (df["pnl"] <= max_pnl)
    ].copy()

    # ── Trade log table ───────────────────────────────────────────────────────
    st.subheader(f"Trade Log — {selected_name} on {ticker}")
    display_df = filtered[[
        "entry_date", "exit_date", "entry_price", "exit_price",
        "shares", "pnl", "return_pct", "hold_days", "result",
    ]].copy()
    display_df.columns = [
        "Entry Date", "Exit Date", "Entry $", "Exit $",
        "Shares", "P&L $", "Return %", "Hold Days", "Result",
    ]

    def _color_result(val):
        return "color: #2ecc71" if val == "Win" else "color: #e74c3c"

    def _color_pnl(val):
        if isinstance(val, float):
            return "color: #2ecc71" if val >= 0 else "color: #e74c3c"
        return ""

    styled = (
        display_df.style
        .map(_color_result, subset=["Result"])
        .map(_color_pnl, subset=["P&L $", "Return %"])
        .format({
            "Entry $": "${:.4f}", "Exit $": "${:.4f}",
            "Shares": "{:.4f}",
            "P&L $": "${:+,.4f}",
            "Return %": "{:+.2f}%",
        })
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── P&L bar chart (full width) ────────────────────────────────────────────
    st.subheader("P&L per Trade")
    colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in filtered["pnl"]]
    fig_pnl = go.Figure(go.Bar(
        x=filtered["exit_date"].dt.strftime("%Y-%m-%d"),
        y=filtered["pnl"],
        marker_color=colors,
        hovertemplate="Date: %{x}<br>P&L: $%{y:+,.2f}<extra></extra>",
    ))
    fig_pnl.add_hline(y=0, line_color="gray", opacity=0.5)
    fig_pnl.update_layout(
        template="plotly_dark",
        xaxis_title="Exit Date", yaxis_title="P&L ($)",
        xaxis_tickangle=-45,
        margin=dict(l=0, r=0, t=30, b=80), height=300,
    )
    st.plotly_chart(fig_pnl, use_container_width=True, config={"responsive": True, "displayModeBar": False, "scrollZoom": False})

    # ── Win/loss pie + stats side-by-side (stack on mobile via CSS) ───────────
    pcol1, pcol2 = st.columns([1, 1])
    with pcol1:
        st.subheader("Win / Loss")
        win_count = (filtered["pnl"] > 0).sum()
        loss_count = (filtered["pnl"] <= 0).sum()
        fig_pie = go.Figure(go.Pie(
            labels=["Wins", "Losses"],
            values=[win_count, loss_count],
            marker_colors=["#2ecc71", "#e74c3c"],
            hole=0.45,
            hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
        ))
        fig_pie.update_layout(
            template="plotly_dark",
            margin=dict(l=0, r=0, t=10, b=0), height=280,
            showlegend=True,
            legend=dict(orientation="h", y=-0.15),
        )
        st.plotly_chart(fig_pie, use_container_width=True, config={"responsive": True, "displayModeBar": False, "scrollZoom": False})

    with pcol2:
        st.subheader("Trade Stats")
        st.markdown(f"""
| Metric | Value |
|--------|-------|
| Avg win | ${filtered.loc[filtered['pnl']>0,'pnl'].mean():+,.2f} |
| Avg loss | ${filtered.loc[filtered['pnl']<=0,'pnl'].mean():+,.2f} |
| Best trade | ${filtered['pnl'].max():+,.2f} |
| Worst trade | ${filtered['pnl'].min():+,.2f} |
| Avg hold | {filtered['hold_days'].mean():.1f} days |
""")

    # ── Monthly P&L heatmap ───────────────────────────────────────────────────
    if len(filtered) >= 4:
        st.subheader("Monthly P&L Heatmap")
        heat = filtered.copy()
        heat["month"] = heat["exit_date"].dt.to_period("M").astype(str)
        monthly = heat.groupby("month")["pnl"].sum().reset_index()
        monthly["year"] = monthly["month"].str[:4]
        monthly["mon"] = monthly["month"].str[5:]
        pivot = monthly.pivot(index="year", columns="mon", values="pnl").fillna(0)

        fig_heat = go.Figure(go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            colorscale=[[0, "#e74c3c"], [0.5, "#1A1D27"], [1, "#2ecc71"]],
            zmid=0,
            hovertemplate="Month: %{x}<br>Year: %{y}<br>P&L: $%{z:+,.2f}<extra></extra>",
            text=[[f"${v:+,.0f}" for v in row] for row in pivot.values],
            texttemplate="%{text}",
        ))
        fig_heat.update_layout(
            template="plotly_dark",
            xaxis_title="Month", yaxis_title="Year",
            margin=dict(l=0, r=0, t=30, b=0), height=250,
        )
        st.plotly_chart(fig_heat, use_container_width=True, config={"responsive": True, "displayModeBar": False, "scrollZoom": False})
