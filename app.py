"""
Trump-Era Market Backtester — Streamlit Dashboard
Launch: streamlit run app.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

# ── Page config (must be first Streamlit call) ───────────────────────────────
st.set_page_config(
    page_title="Trump-Era Market Backtester",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",  # collapsed by default on mobile
)

# ── Ensure project root is on sys.path ───────────────────────────────────────
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest import Backtester, StrategyResult, STRATEGY_MAP
from components.sidebar import render_sidebar
from components.overview_tab import render_overview
from components.performance_tab import render_performance
from components.risk_tab import render_risk
from components.trades_tab import render_trades
from components.comparison_tab import render_comparison
from components.insights_tab import render_insights

# ── Custom CSS (desktop + mobile responsive) ─────────────────────────────────
st.markdown("""
<style>
/* ── Base / desktop ─────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: #1A1D27;
    border: 1px solid #2d3142;
    border-radius: 8px;
    padding: 12px 16px;
}
.stTabs [data-baseweb="tab-list"] {
    gap: 2px;
    overflow-x: auto;
    flex-wrap: nowrap;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar { display: none; }
.stTabs [data-baseweb="tab"] {
    border-radius: 6px 6px 0 0;
    padding: 8px 14px;
    font-weight: 500;
    white-space: nowrap;
    flex-shrink: 0;
}
.header-banner {
    background: linear-gradient(135deg, #1A1D27 0%, #0d1b2a 100%);
    border: 1px solid #2196F3;
    border-radius: 10px;
    padding: 16px 24px;
    margin-bottom: 16px;
}
.stat-ribbon {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 0.82em;
    color: #aaa;
}
.stat-pill {
    background: #2d3142;
    border-radius: 20px;
    padding: 4px 10px;
    color: #eee;
    white-space: nowrap;
}

/* ── Force columns to stack on narrow screens ───────────────────────────── */
@media (max-width: 640px) {
    /* Stack every st.columns row */
    [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 8px !important;
    }
    [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }

    /* Shrink main content padding */
    .block-container {
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
        padding-top: 0.5rem !important;
        max-width: 100% !important;
    }

    /* Header: smaller on phone */
    .header-banner h1 { font-size: 1.25em !important; }
    .header-banner p  { font-size: 0.8em !important; }

    /* Metric cards: bigger value text, full-width */
    [data-testid="metric-container"] {
        padding: 10px 12px;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.3em !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.75em !important;
    }

    /* Touch-friendly buttons */
    [data-testid="stButton"] button {
        min-height: 48px !important;
        font-size: 1em !important;
    }

    /* Touch-friendly select/multiselect */
    [data-testid="stSelectbox"] div[data-baseweb="select"],
    [data-testid="stMultiSelect"] div[data-baseweb="select"] {
        min-height: 44px !important;
    }

    /* Sliders: larger thumb */
    [data-testid="stSlider"] [role="slider"] {
        width: 22px !important;
        height: 22px !important;
    }

    /* Checkboxes: bigger tap targets */
    [data-testid="stCheckbox"] label {
        padding: 6px 0 !important;
        font-size: 0.95em !important;
    }

    /* Scrollable dataframe container */
    [data-testid="stDataFrame"] {
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch;
    }

    /* Tab labels: smaller font so they fit */
    .stTabs [data-baseweb="tab"] {
        padding: 8px 10px !important;
        font-size: 0.78em !important;
    }

    /* Reduce chart top margins */
    .js-plotly-plot .plotly { margin-top: 0 !important; }

    /* Success/info/warning boxes */
    [data-testid="stAlert"] {
        font-size: 0.88em !important;
        padding: 10px 12px !important;
    }

    /* Expanders */
    [data-testid="stExpander"] summary {
        font-size: 0.9em !important;
        padding: 10px 0 !important;
    }

    /* Number inputs */
    [data-testid="stNumberInput"] input {
        height: 44px !important;
        font-size: 1em !important;
    }

    /* Stat ribbon: allow wrap freely */
    .stat-ribbon { gap: 6px; }
    .stat-pill   { font-size: 0.75em; padding: 3px 8px; }
}

/* ── Mid-range tablets (641px – 768px) ──────────────────────────────────── */
@media (min-width: 641px) and (max-width: 768px) {
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100% !important;
    }
    /* 4-col rows → 2x2 */
    [data-testid="stHorizontalBlock"]:has(> [data-testid="column"]:nth-child(4)) {
        flex-wrap: wrap !important;
    }
    [data-testid="stHorizontalBlock"]:has(> [data-testid="column"]:nth-child(4))
    > [data-testid="column"] {
        flex: 1 1 48% !important;
        min-width: 48% !important;
        max-width: 50% !important;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 12px !important;
        font-size: 0.85em !important;
    }
}
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results: list[StrategyResult] = []
if "last_config" not in st.session_state:
    st.session_state.last_config: dict = {}
if "last_run_ts" not in st.session_state:
    st.session_state.last_run_ts: str = ""
if "run_stats" not in st.session_state:
    st.session_state.run_stats: dict = {}


def run_backtest(config: dict) -> None:
    """Run backtester with progress feedback and store results in session state."""
    tickers = config["tickers"]
    strategies = config["strategies"]
    total_steps = len(tickers) * len(strategies)

    st.markdown("---")
    progress_bar = st.progress(0, text="Initialising backtest…")
    status_text = st.empty()

    def progress_cb(frac: float, msg: str) -> None:
        progress_bar.progress(min(frac, 1.0), text=msg)
        status_text.caption(msg)

    t0 = time.time()
    backtester = Backtester(
        tickers=tickers,
        start_date=config["start_date"],
        end_date=config["end_date"],
        capital=config["capital"],
        transaction_cost=config["transaction_cost"],
        strategies=strategies,
        strategy_params=config.get("strategy_params", {}),
    )

    try:
        results = backtester.run(progress_callback=progress_cb)
    except Exception as exc:
        progress_bar.empty()
        status_text.empty()
        st.error(f"Backtest failed: {exc}")
        return

    elapsed = time.time() - t0
    progress_bar.empty()
    status_text.empty()

    if not results:
        st.warning(
            "No results were generated. This usually means the ticker data couldn't be "
            "fetched (network restriction in this environment). "
            "Run locally with `streamlit run app.py` to get live data."
        )
        return

    st.session_state.results = results
    st.session_state.last_config = config
    st.session_state.last_run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.run_stats = {
        "elapsed": elapsed,
        "total_trades": sum(len(r.trades) for r in results),
        "trading_days": max(
            (len(r.equity_curve.dropna()) for r in results), default=0
        ),
        "strategies_run": len({r.name for r in results}),
    }
    st.success(f"Backtest complete in {elapsed:.1f}s — {len(results)} strategy-ticker combinations.")


# ── Sidebar ───────────────────────────────────────────────────────────────────
config = render_sidebar()

# ── Header banner ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="header-banner">
    <h1 style="margin:0;font-size:1.8em">📈 Trump-Era Market Backtester</h1>
    <p style="margin:4px 0 0 0;color:#aaa;font-size:0.9em">
        Analysing trading strategies from January 20, 2025 — Trump's second term
    </p>
</div>
""", unsafe_allow_html=True)

# Quick-stats ribbon (shown once a run is complete)
if st.session_state.run_stats:
    s = st.session_state.run_stats
    lc = st.session_state.last_config
    st.markdown(
        f"""<div class="stat-ribbon">
        <span class="stat-pill">📅 {lc.get('start_date','?')} → {lc.get('end_date','?')}</span>
        <span class="stat-pill">📊 {s['trading_days']:,} trading days</span>
        <span class="stat-pill">🔄 {s['total_trades']:,} trades simulated</span>
        <span class="stat-pill">🎯 {s['strategies_run']} strategies</span>
        <span class="stat-pill">🕐 Last run: {st.session_state.last_run_ts}</span>
        </div>""",
        unsafe_allow_html=True,
    )
    st.markdown("")

# ── Trigger run ───────────────────────────────────────────────────────────────
if config["run"]:
    run_backtest(config)

# ── Main content ──────────────────────────────────────────────────────────────
results = st.session_state.results

if not results:
    # Landing state
    st.markdown("### Getting Started")
    lp1, lp2 = st.columns(2)
    with lp1:
        st.info("**1. Configure** your parameters in the sidebar — date range, assets, strategies.")
        st.info("**2. Click ▶ Run Backtest** to fetch data and run all selected strategies.")
    with lp2:
        st.info("**3. Explore** results across 6 interactive tabs: overview, charts, risk, trades, comparison, and insights.")

    st.markdown("---")
    st.markdown("#### Strategies Available")
    strategy_info = {
        "🗓️ Weekend (Fri→Mon)": "Buy at Friday close, sell at Monday close. Captures weekend sentiment gaps.",
        "📌 Buy & Hold": "Single lump-sum at the start, hold to end. The passive baseline.",
        "💰 Weekly/Biweekly DCA": "Dollar-cost average at a fixed frequency, smoothing entry price risk.",
        "📉 MA Crossover": "Golden cross (50/200 MA) entry, death cross exit. Trend-following.",
        "🔄 RSI Mean Reversion": "Buy oversold (RSI < 30), sell overbought (RSI > 70). Counter-trend.",
        "📆 Monthly DCA": "Larger monthly purchases on the first trading day of each month.",
    }
    c1, c2 = st.columns(2)
    for i, (name, desc) in enumerate(strategy_info.items()):
        col = c1 if i % 2 == 0 else c2
        col.markdown(f"**{name}**  \n{desc}")

    st.stop()

# ── Ticker selector (when multiple tickers run) ───────────────────────────────
tickers = list(dict.fromkeys(r.ticker for r in results))
if len(tickers) > 1:
    active_ticker = st.selectbox(
        "Active asset (for per-asset tabs):", tickers,
        key="active_ticker", help="Overview, Performance, Risk, and Trade tabs show one asset at a time.",
    )
else:
    active_ticker = tickers[0]

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_labels = [
    "🏠 Overview",
    "📊 Charts",
    "⚠️ Risk",
    "🔎 Trades",
    "🆚 Compare",
    "💡 Insights",
]
tabs = st.tabs(tab_labels)

with tabs[0]:
    render_overview(results, active_ticker)

with tabs[1]:
    render_performance(results, active_ticker)

with tabs[2]:
    render_risk(results, active_ticker)

with tabs[3]:
    render_trades(results, active_ticker)

with tabs[4]:
    render_comparison(results)

with tabs[5]:
    render_insights(results, st.session_state.last_config)
