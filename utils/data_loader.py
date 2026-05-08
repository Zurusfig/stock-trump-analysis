"""Cached data-fetching layer for the Streamlit dashboard."""
from __future__ import annotations

import streamlit as st
import pandas as pd
import yfinance as yf


AVAILABLE_TICKERS = {
    "^GSPC": "S&P 500",
    "GLD": "Gold ETF",
    "QQQ": "Nasdaq 100",
    "BTC-USD": "Bitcoin",
    "TLT": "20yr Treasury Bonds",
    "SPY": "S&P 500 ETF",
    "IWM": "Russell 2000",
    "DIA": "Dow Jones",
}


@st.cache_data(ttl=3600, show_spinner=False)
def load_price_data(ticker: str, start: str, end: str) -> pd.DataFrame | None:
    """Download OHLCV data, cached for 1 hour."""
    try:
        raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
        if raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)
        return df
    except Exception:
        return None


def validate_ticker(ticker: str, start: str, end: str) -> bool:
    """Return True if data is available for the ticker/date range."""
    df = load_price_data(ticker, start, end)
    return df is not None and not df.empty
