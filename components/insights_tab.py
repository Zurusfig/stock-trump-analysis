"""Tab 6 — Insights & Report: auto-generated insights + download buttons."""
from __future__ import annotations

import io
import json
from datetime import datetime

import pandas as pd
import streamlit as st
from backtest import StrategyResult
from utils.insights_generator import generate_insights


def render_insights(results: list[StrategyResult], config: dict) -> None:
    tickers = list(dict.fromkeys(r.ticker for r in results))
    insights = generate_insights(results)

    st.subheader("🔍 Auto-Generated Insights")
    for ticker in tickers:
        ticker_insights = insights.get(ticker, [])
        if not ticker_insights:
            continue
        with st.expander(f"📊 {ticker} Insights", expanded=True):
            for insight in ticker_insights:
                st.markdown(f"- {insight}")

    st.markdown("---")
    st.subheader("📥 Export & Downloads")

    # ── Download: comparison CSV ──────────────────────────────────────────────
    metrics_rows = [r.metrics for r in results if r.metrics]
    if metrics_rows:
        summary_df = pd.DataFrame(metrics_rows)
        csv_bytes = summary_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Download Summary CSV",
            data=csv_bytes,
            file_name="comparison_summary.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # ── Download: trade logs ZIP ──────────────────────────────────────────────
    import zipfile

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for result in results:
            if not result.trades:
                continue
            name_slug = result.name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_").replace("→", "_")
            ticker_slug = result.ticker.replace("^", "")
            df = pd.DataFrame([t.to_dict() for t in result.trades])
            zf.writestr(f"trades_{name_slug}_{ticker_slug}.csv", df.to_csv(index=False))
    zip_buffer.seek(0)
    st.download_button(
        label="⬇️ Download All Trade Logs (ZIP)",
        data=zip_buffer,
        file_name="trade_logs.zip",
        mime="application/zip",
        use_container_width=True,
    )

    # ── Download: full results JSON ───────────────────────────────────────────
    json_payload = {
        "generated_at": datetime.now().isoformat(),
        "config": {k: str(v) for k, v in config.items() if k != "run"},
        "results": [r.metrics for r in results if r.metrics],
    }
    json_bytes = json.dumps(json_payload, indent=2, default=str).encode("utf-8")
    st.download_button(
        label="⬇️ Download Full Results JSON",
        data=json_bytes,
        file_name="backtest_results.json",
        mime="application/json",
        use_container_width=True,
    )

    # ── Download: markdown report ─────────────────────────────────────────────
    report = _build_markdown_report(results, config, insights)
    st.download_button(
        label="⬇️ Download Markdown Report",
        data=report.encode("utf-8"),
        file_name="results.md",
        mime="text/markdown",
        use_container_width=True,
    )

    # ── Preview report ────────────────────────────────────────────────────────
    with st.expander("📄 Preview Markdown Report"):
        st.markdown(report)


def _build_markdown_report(results: list[StrategyResult],
                            config: dict,
                            insights: dict[str, list[str]]) -> str:
    tickers = list(dict.fromkeys(r.ticker for r in results))
    lines = [
        "# Backtest Results Report",
        f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Period:** {config.get('start_date')} → {config.get('end_date')}",
        f"**Capital per trade:** ${config.get('capital', 0):,.0f}",
        f"**Transaction cost:** {float(config.get('transaction_cost', 0)) * 100:.2f}%",
        "\n---\n",
    ]

    for ticker in tickers:
        tr = [r for r in results if r.ticker == ticker and r.metrics]
        if not tr:
            continue
        sorted_r = sorted(tr, key=lambda r: r.metrics.get("total_return_pct", -999), reverse=True)

        lines.append(f"## {ticker}\n")
        lines.append("| Rank | Strategy | Return % | Ann. Return % | Sharpe | Max DD % | Trades |")
        lines.append("|------|----------|----------|---------------|--------|----------|--------|")
        for rank, r in enumerate(sorted_r, 1):
            m = r.metrics
            lines.append(
                f"| {rank} | {m['strategy']} | {m['total_return_pct']:+.2f}% "
                f"| {m['annualised_return_pct']:+.2f}% "
                f"| {m['sharpe_ratio']:.3f} "
                f"| {m['max_drawdown_pct']:.2f}% "
                f"| {m['num_trades']} |"
            )

        lines.append(f"\n### Insights\n")
        for insight in insights.get(ticker, []):
            lines.append(f"- {insight}")
        lines.append("\n---\n")

    lines.append("## Disclaimer\n")
    lines.append(
        "> Past performance is not indicative of future results. "
        "This analysis is for educational purposes only."
    )
    return "\n".join(lines)
