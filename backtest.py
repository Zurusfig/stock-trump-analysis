"""
Weekend Trading Backtester
Analyzes a "Buy Friday, Sell Monday" strategy against 5 benchmark strategies
on S&P 500 (^GSPC) and Gold (GLD) during Trump's second term (Jan 20, 2025 - present).
"""

from __future__ import annotations

import argparse
import warnings
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import yfinance as yf
from tabulate import tabulate

warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import pandas_ta as ta
    TA_AVAILABLE = True
    TA_BACKEND = "pandas_ta"
except ImportError:
    try:
        import ta  # type: ignore
        TA_AVAILABLE = True
        TA_BACKEND = "ta"
    except ImportError:
        TA_AVAILABLE = False
        TA_BACKEND = "none"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def fetch_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Download OHLCV data from Yahoo Finance with basic validation."""
    raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if raw.empty:
        raise ValueError(f"No data returned for {ticker} between {start} and {end}.")
    # Flatten multi-level columns if present
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)
    return df


def next_trading_day(df: pd.DataFrame, ref_date: pd.Timestamp) -> Optional[pd.Timestamp]:
    """Return the first index date >= ref_date that exists in df."""
    future = df.index[df.index >= ref_date]
    return future[0] if len(future) > 0 else None


# ---------------------------------------------------------------------------
# Trade / Result data classes
# ---------------------------------------------------------------------------

class Trade:
    __slots__ = ("entry_date", "exit_date", "entry_price", "exit_price",
                 "shares", "pnl", "cost")

    def __init__(self, entry_date: pd.Timestamp, exit_date: pd.Timestamp,
                 entry_price: float, exit_price: float,
                 shares: float, transaction_cost: float = 0.0):
        self.entry_date = entry_date
        self.exit_date = exit_date
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.shares = shares
        cost_entry = entry_price * shares * transaction_cost
        cost_exit = exit_price * shares * transaction_cost
        self.cost = cost_entry + cost_exit
        self.pnl = (exit_price - entry_price) * shares - self.cost

    def to_dict(self) -> dict:
        return {
            "entry_date": self.entry_date.date(),
            "exit_date": self.exit_date.date(),
            "entry_price": round(self.entry_price, 4),
            "exit_price": round(self.exit_price, 4),
            "shares": round(self.shares, 6),
            "pnl": round(self.pnl, 4),
            "transaction_cost": round(self.cost, 4),
        }


class StrategyResult:
    def __init__(self, name: str, ticker: str, trades: list[Trade],
                 equity_curve: pd.Series, total_invested: float):
        self.name = name
        self.ticker = ticker
        self.trades = trades
        self.equity_curve = equity_curve
        self.total_invested = total_invested
        self.metrics: dict = {}

    def compute_metrics(self) -> None:
        ec = self.equity_curve.dropna()
        if ec.empty or self.total_invested == 0:
            # Still record identifying fields so the result is never an empty dict
            self.metrics = {
                "strategy": self.name, "ticker": self.ticker,
                "total_invested": 0, "final_value": 0, "total_pnl": 0,
                "total_return_pct": 0, "annualised_return_pct": 0,
                "win_rate_pct": "N/A", "max_drawdown_pct": 0,
                "sharpe_ratio": 0, "sortino_ratio": 0,
                "num_trades": len(self.trades), "total_transaction_costs": 0,
            }
            return

        final_value = ec.iloc[-1]
        pnl = final_value - self.total_invested
        total_return_pct = pnl / self.total_invested * 100

        # Annualised return
        n_days = (ec.index[-1] - ec.index[0]).days
        n_years = max(n_days / 365.25, 1 / 365.25)
        annualised = ((final_value / self.total_invested) ** (1 / n_years) - 1) * 100

        # Daily returns for risk metrics (skip leading zeros to avoid inf pct_change)
        daily_ret = ec[ec > 0].pct_change().dropna()
        daily_ret = daily_ret.replace([np.inf, -np.inf], np.nan).dropna()

        # Sharpe (annualised, rf=0)
        if daily_ret.std() > 0:
            sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252)
        else:
            sharpe = 0.0

        # Sortino
        downside = daily_ret[daily_ret < 0]
        if len(downside) > 0 and downside.std() > 0:
            sortino = (daily_ret.mean() / downside.std()) * np.sqrt(252)
        else:
            sortino = 0.0

        # Max drawdown
        rolling_max = ec.cummax()
        drawdown = (ec - rolling_max) / rolling_max * 100
        max_dd = drawdown.min()

        # Win rate
        if self.trades:
            wins = sum(1 for t in self.trades if t.pnl > 0)
            win_rate = wins / len(self.trades) * 100
        else:
            win_rate = float("nan")

        total_cost = sum(t.cost for t in self.trades)

        self.metrics = {
            "strategy": self.name,
            "ticker": self.ticker,
            "total_invested": round(self.total_invested, 2),
            "final_value": round(final_value, 2),
            "total_pnl": round(pnl, 2),
            "total_return_pct": round(total_return_pct, 2),
            "annualised_return_pct": round(annualised, 2),
            "win_rate_pct": round(win_rate, 2) if not np.isnan(win_rate) else "N/A",
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "num_trades": len(self.trades),
            "total_transaction_costs": round(total_cost, 2),
        }


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class Strategy(ABC):
    """Abstract base for all trading strategies."""

    name: str = "AbstractStrategy"

    def __init__(self, df: pd.DataFrame, ticker: str,
                 capital_per_trade: float = 1000.0,
                 transaction_cost: float = 0.001):
        self.df = df.copy()
        self.ticker = ticker
        self.capital_per_trade = capital_per_trade
        self.transaction_cost = transaction_cost

    @abstractmethod
    def generate_signals(self) -> pd.DataFrame:
        """Return a DataFrame with at least 'signal' and 'price' columns."""

    @abstractmethod
    def execute_trades(self, signals: pd.DataFrame) -> tuple[list[Trade], pd.Series, float]:
        """Return (trades, equity_curve, total_invested)."""

    def calculate_metrics(self) -> StrategyResult:
        signals = self.generate_signals()
        trades, equity_curve, total_invested = self.execute_trades(signals)
        result = StrategyResult(self.name, self.ticker, trades, equity_curve, total_invested)
        result.compute_metrics()
        return result


# ---------------------------------------------------------------------------
# Strategy 1: Weekend (Buy Friday Close → Sell Monday Close)
# ---------------------------------------------------------------------------

class WeekendStrategy(Strategy):
    name = "Weekend (Fri→Mon)"

    def generate_signals(self) -> pd.DataFrame:
        df = self.df.copy()
        df["weekday"] = df.index.dayofweek  # 0=Mon … 4=Fri
        fridays = df[df["weekday"] == 4].copy()
        fridays["signal"] = "buy"
        fridays["price"] = fridays["Close"]
        return fridays[["price", "signal"]]

    def execute_trades(self, signals: pd.DataFrame) -> tuple[list[Trade], pd.Series, float]:
        trades: list[Trade] = []
        portfolio_value: dict[pd.Timestamp, float] = {}
        total_invested = 0.0
        cumulative_cash = 0.0  # tracks realised P&L + unused capital

        for fri_date, row in signals.iterrows():
            buy_price = float(row["price"])
            if buy_price <= 0:
                continue

            # Find the next Monday (or subsequent trading day)
            next_monday = fri_date + timedelta(days=3)
            sell_date = next_trading_day(self.df, next_monday)
            if sell_date is None or sell_date == fri_date:
                continue

            sell_price = float(self.df.loc[sell_date, "Close"])
            shares = self.capital_per_trade / buy_price
            trade = Trade(fri_date, sell_date, buy_price, sell_price,
                          shares, self.transaction_cost)
            trades.append(trade)
            total_invested += self.capital_per_trade
            cumulative_cash += self.capital_per_trade + trade.pnl
            portfolio_value[sell_date] = cumulative_cash

        if not portfolio_value:
            idx = self.df.index
            equity = pd.Series(np.nan, index=idx)
            return trades, equity, total_invested

        # Build continuous equity curve by forward-filling sell points
        idx = self.df.index
        equity = pd.Series(np.nan, index=idx)
        for dt, val in portfolio_value.items():
            if dt in equity.index:
                equity.loc[dt] = val
        equity = equity.ffill()
        # Before first trade settles, set to 0
        first_settle = min(portfolio_value.keys())
        equity.loc[equity.index < first_settle] = 0.0
        return trades, equity, total_invested


# ---------------------------------------------------------------------------
# Strategy 2: Buy & Hold
# ---------------------------------------------------------------------------

class BuyHoldStrategy(Strategy):
    name = "Buy & Hold"

    def generate_signals(self) -> pd.DataFrame:
        first_row = self.df.iloc[[0]].copy()
        first_row["price"] = first_row["Open"]
        first_row["signal"] = "buy"
        return first_row[["price", "signal"]]

    def execute_trades(self, signals: pd.DataFrame) -> tuple[list[Trade], pd.Series, float]:
        # Determine total capital = same as weekly DCA would deploy
        # We use the same lump sum = capital_per_trade (user decides scale via --capital)
        entry_date = signals.index[0]
        entry_price = float(signals.iloc[0]["price"])
        total_invested = self.capital_per_trade

        shares = total_invested / entry_price

        # Equity curve = shares * Close each day
        equity = self.df["Close"] * shares
        equity = equity.loc[equity.index >= entry_date]

        # Record a single "open" trade (exit = last date)
        exit_date = self.df.index[-1]
        exit_price = float(self.df.iloc[-1]["Close"])
        trade = Trade(entry_date, exit_date, entry_price, exit_price,
                      shares, self.transaction_cost)
        return [trade], equity, total_invested


# ---------------------------------------------------------------------------
# Strategy 3: Weekly DCA (buy Monday open every week)
# ---------------------------------------------------------------------------

class DCAStrategy(Strategy):
    name = "Weekly DCA"

    def __init__(self, df: pd.DataFrame, ticker: str,
                 capital_per_trade: float = 1000.0,
                 transaction_cost: float = 0.001,
                 frequency: str = "weekly"):
        super().__init__(df, ticker, capital_per_trade, transaction_cost)
        self.frequency = frequency  # "weekly", "biweekly", "monthly"
        freq_label = {"weekly": "Weekly", "biweekly": "Biweekly", "monthly": "Monthly"}.get(frequency, "Weekly")
        self.name = f"{freq_label} DCA"

    def generate_signals(self) -> pd.DataFrame:
        df = self.df.copy()
        df["weekday"] = df.index.dayofweek

        if self.frequency == "monthly":
            df["year_month"] = df.index.to_period("M")
            first_days = df.groupby("year_month").apply(lambda g: g.index[0]).values
            mask = df.index.isin(first_days)
        elif self.frequency == "biweekly":
            mondays = df[df["weekday"] == 0].copy()
            # Every other Monday
            mask = df.index.isin(mondays.index[::2])
        else:  # weekly
            mask = df["weekday"] == 0

        signals = df[mask].copy()
        signals["price"] = signals["Open"]
        signals["signal"] = "buy"
        return signals[["price", "signal"]]

    def execute_trades(self, signals: pd.DataFrame) -> tuple[list[Trade], pd.Series, float]:
        trades: list[Trade] = []
        total_invested = 0.0
        total_shares = 0.0
        purchase_records: list[tuple[pd.Timestamp, float, float]] = []

        for dt, row in signals.iterrows():
            price = float(row["price"])
            if price <= 0:
                continue
            cost = self.capital_per_trade * (1 + self.transaction_cost)
            shares = self.capital_per_trade / price
            total_shares += shares
            total_invested += self.capital_per_trade
            purchase_records.append((dt, price, shares))

        # Single notional "trade" from first buy to last day
        if not purchase_records:
            return [], pd.Series(dtype=float), 0.0

        entry_date = purchase_records[0][0]
        exit_date = self.df.index[-1]
        exit_price = float(self.df.iloc[-1]["Close"])
        entry_price = purchase_records[0][1]

        for dt, price, shares in purchase_records:
            t = Trade(dt, exit_date, price, exit_price, shares, self.transaction_cost)
            trades.append(t)

        # Equity curve: cumulative shares held * close price each day
        share_series = pd.Series(0.0, index=self.df.index)
        for dt, price, shares in purchase_records:
            share_series.loc[dt:] += shares

        equity = share_series * self.df["Close"]
        equity.loc[equity.index < entry_date] = 0.0
        return trades, equity, total_invested


# ---------------------------------------------------------------------------
# Shared equity-curve helper for position-based strategies
# ---------------------------------------------------------------------------

def _position_equity_curve(df: pd.DataFrame, trades: list[Trade]) -> pd.Series:
    """
    Build an equity curve for strategies that hold one position at a time.
    Portfolio value = sum of realised capital so far + market value of open position.
    """
    equity = pd.Series(np.nan, index=df.index)
    realised = 0.0  # cash accumulated from closed trades

    for trade in trades:
        capital_deployed = trade.entry_price * trade.shares  # ≈ capital_per_trade
        mask = (df.index >= trade.entry_date) & (df.index <= trade.exit_date)
        # Current market value of the position
        mkt_value = capital_deployed + (df.loc[mask, "Close"] - trade.entry_price) * trade.shares
        equity.loc[mask] = (realised + mkt_value).values
        # After the trade closes, realised grows by net proceeds minus costs
        realised += capital_deployed + trade.pnl

    equity = equity.ffill().fillna(0.0)
    return equity


# ---------------------------------------------------------------------------
# Strategy 4: Moving Average Crossover (50/200)
# ---------------------------------------------------------------------------

class MACrossoverStrategy(Strategy):
    name = "MA Crossover (50/200)"

    def __init__(self, df: pd.DataFrame, ticker: str,
                 capital_per_trade: float = 1000.0,
                 transaction_cost: float = 0.001,
                 short_window: int = 50, long_window: int = 200):
        super().__init__(df, ticker, capital_per_trade, transaction_cost)
        self.short_window = short_window
        self.long_window = long_window
        self.name = f"MA Crossover ({short_window}/{long_window})"

    def generate_signals(self) -> pd.DataFrame:
        df = self.df.copy()
        df["ma_short"] = df["Close"].rolling(self.short_window).mean()
        df["ma_long"] = df["Close"].rolling(self.long_window).mean()
        df["prev_short"] = df["ma_short"].shift(1)
        df["prev_long"] = df["ma_long"].shift(1)

        # Golden cross: short MA crosses above long MA
        df["golden"] = (df["ma_short"] > df["ma_long"]) & (df["prev_short"] <= df["prev_long"])
        # Death cross: short MA crosses below long MA
        df["death"] = (df["ma_short"] < df["ma_long"]) & (df["prev_short"] >= df["prev_long"])

        df["signal"] = None
        df.loc[df["golden"], "signal"] = "buy"
        df.loc[df["death"], "signal"] = "sell"
        df["price"] = df["Close"]
        return df[["price", "signal", "ma_short", "ma_long"]]

    def execute_trades(self, signals: pd.DataFrame) -> tuple[list[Trade], pd.Series, float]:
        trades: list[Trade] = []
        total_invested = 0.0
        position: Optional[tuple[pd.Timestamp, float, float]] = None  # (date, price, shares)

        for dt, row in signals.iterrows():
            sig = row["signal"]
            price = float(row["price"])
            if price <= 0:
                continue

            if sig == "buy" and position is None:
                shares = self.capital_per_trade / price
                total_invested += self.capital_per_trade
                position = (dt, price, shares)

            elif sig == "sell" and position is not None:
                entry_dt, entry_price, shares = position
                trade = Trade(entry_dt, dt, entry_price, price,
                              shares, self.transaction_cost)
                trades.append(trade)
                position = None

        # Close open position at end
        if position is not None:
            entry_dt, entry_price, shares = position
            exit_dt = self.df.index[-1]
            exit_price = float(self.df.iloc[-1]["Close"])
            trade = Trade(entry_dt, exit_dt, entry_price, exit_price,
                          shares, self.transaction_cost)
            trades.append(trade)
            position = None

        equity = self._build_equity_curve(trades, signals)
        return trades, equity, total_invested

    def _build_equity_curve(self, trades: list[Trade], signals: pd.DataFrame) -> pd.Series:
        return _position_equity_curve(self.df, trades)


# ---------------------------------------------------------------------------
# Strategy 5: RSI Mean Reversion
# ---------------------------------------------------------------------------

class RSIStrategy(Strategy):
    name = "RSI Mean Reversion"

    def __init__(self, df: pd.DataFrame, ticker: str,
                 capital_per_trade: float = 1000.0,
                 transaction_cost: float = 0.001,
                 oversold: int = 30, overbought: int = 70, period: int = 14):
        super().__init__(df, ticker, capital_per_trade, transaction_cost)
        self.oversold = oversold
        self.overbought = overbought
        self.period = period
        self.name = f"RSI ({oversold}/{overbought})"

    def generate_signals(self) -> pd.DataFrame:
        df = self.df.copy()
        com = self.period - 1

        if TA_AVAILABLE and TA_BACKEND == "pandas_ta":
            df["rsi"] = ta.rsi(df["Close"], length=self.period)
        elif TA_AVAILABLE and TA_BACKEND == "ta":
            import ta as ta_lib  # type: ignore
            rsi_indicator = ta_lib.momentum.RSIIndicator(close=df["Close"], window=self.period)
            df["rsi"] = rsi_indicator.rsi()
        else:
            # Pure-pandas Wilder RSI (no external dependency)
            delta = df["Close"].diff()
            gain = delta.clip(lower=0)
            loss = (-delta.clip(upper=0))
            avg_gain = gain.ewm(com=com, min_periods=self.period).mean()
            avg_loss = loss.ewm(com=com, min_periods=self.period).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            df["rsi"] = 100 - 100 / (1 + rs)

        df["signal"] = None
        df.loc[df["rsi"] < self.oversold, "signal"] = "buy"
        df.loc[df["rsi"] > self.overbought, "signal"] = "sell"
        df["price"] = df["Close"]
        return df[["price", "signal", "rsi"]]

    def execute_trades(self, signals: pd.DataFrame) -> tuple[list[Trade], pd.Series, float]:
        trades: list[Trade] = []
        total_invested = 0.0
        position: Optional[tuple[pd.Timestamp, float, float]] = None

        for dt, row in signals.iterrows():
            sig = row["signal"]
            price = float(row["price"])
            if price <= 0 or np.isnan(price):
                continue

            if sig == "buy" and position is None:
                shares = self.capital_per_trade / price
                total_invested += self.capital_per_trade
                position = (dt, price, shares)

            elif sig == "sell" and position is not None:
                entry_dt, entry_price, shares = position
                trade = Trade(entry_dt, dt, entry_price, price,
                              shares, self.transaction_cost)
                trades.append(trade)
                position = None

        if position is not None:
            entry_dt, entry_price, shares = position
            exit_dt = self.df.index[-1]
            exit_price = float(self.df.iloc[-1]["Close"])
            trade = Trade(entry_dt, exit_dt, entry_price, exit_price,
                          shares, self.transaction_cost)
            trades.append(trade)

        equity = self._build_equity_curve(trades)
        return trades, equity, total_invested

    def _build_equity_curve(self, trades: list[Trade]) -> pd.Series:
        return _position_equity_curve(self.df, trades)


# ---------------------------------------------------------------------------
# Strategy 6: Monthly DCA
# ---------------------------------------------------------------------------

class MonthlyDCAStrategy(Strategy):
    name = "Monthly DCA"

    def generate_signals(self) -> pd.DataFrame:
        df = self.df.copy()
        df["year_month"] = df.index.to_period("M")
        # First trading day per month
        first_days = df.groupby("year_month").apply(lambda g: g.index[0]).values
        mask = df.index.isin(first_days)
        monthly = df[mask].copy()
        monthly["price"] = monthly["Open"]
        monthly["signal"] = "buy"
        return monthly[["price", "signal"]]

    def execute_trades(self, signals: pd.DataFrame) -> tuple[list[Trade], pd.Series, float]:
        # $4000/month ≈ same total as $1000/week
        monthly_capital = self.capital_per_trade * 4
        trades: list[Trade] = []
        total_invested = 0.0
        total_shares = 0.0
        purchase_records: list[tuple[pd.Timestamp, float, float]] = []

        for dt, row in signals.iterrows():
            price = float(row["price"])
            if price <= 0:
                continue
            shares = monthly_capital / price
            total_shares += shares
            total_invested += monthly_capital
            purchase_records.append((dt, price, shares))

        if not purchase_records:
            return [], pd.Series(dtype=float), 0.0

        exit_date = self.df.index[-1]
        exit_price = float(self.df.iloc[-1]["Close"])
        for dt, price, shares in purchase_records:
            t = Trade(dt, exit_date, price, exit_price, shares, self.transaction_cost)
            trades.append(t)

        share_series = pd.Series(0.0, index=self.df.index)
        for dt, price, shares in purchase_records:
            share_series.loc[dt:] += shares

        equity = share_series * self.df["Close"]
        equity.loc[equity.index < purchase_records[0][0]] = 0.0
        return trades, equity, total_invested


# ---------------------------------------------------------------------------
# Backtester
# ---------------------------------------------------------------------------

STRATEGY_MAP: dict[str, type[Strategy]] = {
    "weekend": WeekendStrategy,
    "buyhold": BuyHoldStrategy,
    "dca": DCAStrategy,
    "macrossover": MACrossoverStrategy,
    "rsi": RSIStrategy,
    "monthlydca": MonthlyDCAStrategy,
}


class Backtester:
    def __init__(self, tickers: list[str], start_date: str, end_date: str,
                 capital: float = 1000.0, transaction_cost: float = 0.001,
                 strategies: Optional[list[str]] = None,
                 strategy_params: Optional[dict] = None):
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.capital = capital
        self.transaction_cost = transaction_cost
        self.strategy_keys = strategies or list(STRATEGY_MAP.keys())
        self.strategy_params = strategy_params or {}
        self.results: list[StrategyResult] = []

    def _build_strategy(self, key: str, df: pd.DataFrame, ticker: str) -> Strategy:
        """Instantiate a strategy with any user-provided extra params."""
        cls = STRATEGY_MAP[key]
        extra = self.strategy_params.get(key, {})
        return cls(df, ticker, self.capital, self.transaction_cost, **extra)

    def run(self, progress_callback=None) -> list[StrategyResult]:
        self.results = []
        total_steps = len(self.tickers) * len(self.strategy_keys)
        step = 0

        for ticker in self.tickers:
            print(f"\n  Fetching data for {ticker}...")
            try:
                df = fetch_data(ticker, self.start_date, self.end_date)
            except ValueError as e:
                print(f"  [WARN] {e}")
                step += len(self.strategy_keys)
                if progress_callback:
                    progress_callback(step / total_steps, f"Skipped {ticker}: no data")
                continue

            print(f"  {ticker}: {len(df)} trading days ({df.index[0].date()} → {df.index[-1].date()})")

            for key in self.strategy_keys:
                cls = STRATEGY_MAP.get(key)
                if cls is None:
                    print(f"  [WARN] Unknown strategy '{key}', skipping.")
                    step += 1
                    continue

                try:
                    strategy = self._build_strategy(key, df, ticker)
                    print(f"    Running {strategy.name}...")
                    if progress_callback:
                        progress_callback(step / total_steps, f"{ticker} — {strategy.name}")
                    result = strategy.calculate_metrics()
                    self.results.append(result)
                except Exception as exc:
                    print(f"    [ERROR] {key} failed: {exc}")
                finally:
                    step += 1

        if progress_callback:
            progress_callback(1.0, "Done")
        return self.results

    def print_summary(self) -> None:
        if not self.results:
            print("No results to display.")
            return

        for ticker in self.tickers:
            ticker_results = [r for r in self.results if r.ticker == ticker]
            if not ticker_results:
                continue

            print(f"\n{'='*80}")
            print(f"  RESULTS FOR {ticker}")
            print(f"{'='*80}")

            rows = []
            headers = ["Strategy", "Invested $", "Final $", "P&L $",
                       "Return %", "Ann. Return %", "Win Rate %",
                       "Max DD %", "Sharpe", "Sortino", "Trades", "Costs $"]

            sorted_results = sorted(ticker_results,
                                    key=lambda r: r.metrics.get("total_return_pct", -999),
                                    reverse=True)

            for r in sorted_results:
                m = r.metrics
                if not m:
                    continue
                rows.append([
                    m["strategy"],
                    f"{m['total_invested']:,.0f}",
                    f"{m['final_value']:,.0f}",
                    f"{m['total_pnl']:+,.0f}",
                    f"{m['total_return_pct']:+.2f}%",
                    f"{m['annualised_return_pct']:+.2f}%",
                    f"{m['win_rate_pct']}" if m["win_rate_pct"] == "N/A"
                    else f"{m['win_rate_pct']:.1f}%",
                    f"{m['max_drawdown_pct']:.2f}%",
                    f"{m['sharpe_ratio']:.3f}",
                    f"{m['sortino_ratio']:.3f}",
                    str(m["num_trades"]),
                    f"{m['total_transaction_costs']:,.2f}",
                ])

            print(tabulate(rows, headers=headers, tablefmt="rounded_outline"))

    def export_trades(self, output_dir: Path = Path(".")) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for result in self.results:
            if not result.trades:
                continue
            name_slug = result.name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
            ticker_slug = result.ticker.replace("^", "")
            path = output_dir / f"trades_{name_slug}_{ticker_slug}.csv"
            df = pd.DataFrame([t.to_dict() for t in result.trades])
            df.to_csv(path, index=False)

    def export_summary(self, path: Path = Path("comparison_summary.csv")) -> None:
        rows = [r.metrics for r in self.results if r.metrics]
        if not rows:
            return
        pd.DataFrame(rows).to_csv(path, index=False)
        print(f"\n  Summary saved to {path}")


# ---------------------------------------------------------------------------
# Visualizer
# ---------------------------------------------------------------------------

COLORS = ["#2196F3", "#FF5722", "#4CAF50", "#9C27B0", "#FF9800", "#00BCD4"]


class Visualizer:
    def __init__(self, results: list[StrategyResult], output_dir: Path = Path(".")):
        self.results = results
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _ticker_results(self, ticker: str) -> list[StrategyResult]:
        return [r for r in self.results if r.ticker == ticker]

    def plot_cumulative_returns(self, ticker: str) -> None:
        tr = self._ticker_results(ticker)
        if not tr:
            return

        fig, ax = plt.subplots(figsize=(14, 7))
        for i, result in enumerate(tr):
            ec = result.equity_curve.dropna()
            if ec.empty:
                continue
            # Normalise so all start at 0 % return
            invested = result.total_invested if result.total_invested > 0 else 1
            pct = (ec / invested - 1) * 100
            ax.plot(pct.index, pct.values, label=result.name,
                    color=COLORS[i % len(COLORS)], linewidth=1.8)

        ax.axhline(0, color="gray", linestyle="--", linewidth=0.8)
        ax.set_title(f"Cumulative Returns — {ticker}", fontsize=14, fontweight="bold")
        ax.set_xlabel("Date")
        ax.set_ylabel("Return (%)")
        ax.legend(loc="upper left", fontsize=9)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        path = self.output_dir / f"cumulative_returns_{ticker.replace('^','')}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        print(f"  Saved: {path}")

    def plot_return_bar(self, ticker: str) -> None:
        tr = self._ticker_results(ticker)
        if not tr:
            return

        names = [r.metrics.get("strategy", r.name) for r in tr if r.metrics]
        returns = [r.metrics.get("total_return_pct", 0) for r in tr if r.metrics]
        if not names:
            return

        sorted_pairs = sorted(zip(returns, names), reverse=True)
        returns_s, names_s = zip(*sorted_pairs)

        fig, ax = plt.subplots(figsize=(10, 6))
        bar_colors = [COLORS[i % len(COLORS)] for i in range(len(names_s))]
        bars = ax.barh(names_s, returns_s, color=bar_colors, edgecolor="white")
        ax.axvline(0, color="gray", linewidth=0.8)
        for bar, val in zip(bars, returns_s):
            ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                    f"{val:+.2f}%", va="center", fontsize=9)
        ax.set_title(f"Total Return Comparison — {ticker}", fontsize=13, fontweight="bold")
        ax.set_xlabel("Total Return (%)")
        ax.grid(axis="x", alpha=0.3)
        fig.tight_layout()
        path = self.output_dir / f"return_bar_{ticker.replace('^','')}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        print(f"  Saved: {path}")

    def plot_drawdown(self, ticker: str) -> None:
        tr = self._ticker_results(ticker)
        if not tr:
            return

        fig, ax = plt.subplots(figsize=(14, 6))
        for i, result in enumerate(tr):
            ec = result.equity_curve.dropna()
            if ec.empty or ec.max() == 0:
                continue
            rolling_max = ec.cummax()
            dd = (ec - rolling_max) / rolling_max * 100
            ax.fill_between(dd.index, dd.values, 0,
                             alpha=0.3, color=COLORS[i % len(COLORS)], label=result.name)
            ax.plot(dd.index, dd.values, color=COLORS[i % len(COLORS)],
                    linewidth=1.0, alpha=0.8)

        ax.set_title(f"Drawdown Comparison — {ticker}", fontsize=14, fontweight="bold")
        ax.set_xlabel("Date")
        ax.set_ylabel("Drawdown (%)")
        ax.legend(loc="lower left", fontsize=9)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        path = self.output_dir / f"drawdown_{ticker.replace('^','')}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        print(f"  Saved: {path}")

    def plot_risk_return(self, ticker: str) -> None:
        tr = [r for r in self._ticker_results(ticker) if r.metrics]
        if not tr:
            return

        fig, ax = plt.subplots(figsize=(9, 7))
        for i, result in enumerate(tr):
            m = result.metrics
            x = m.get("sharpe_ratio", 0)
            y = m.get("total_return_pct", 0)
            ax.scatter(x, y, color=COLORS[i % len(COLORS)], s=120, zorder=5)
            ax.annotate(m["strategy"], (x, y),
                        textcoords="offset points", xytext=(8, 4), fontsize=8)

        ax.axhline(0, color="gray", linestyle="--", linewidth=0.8)
        ax.axvline(0, color="gray", linestyle="--", linewidth=0.8)
        ax.set_title(f"Risk-Return Scatter (Sharpe vs Total Return) — {ticker}",
                     fontsize=12, fontweight="bold")
        ax.set_xlabel("Sharpe Ratio")
        ax.set_ylabel("Total Return (%)")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        path = self.output_dir / f"risk_return_{ticker.replace('^','')}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        print(f"  Saved: {path}")

    def plot_all(self) -> None:
        tickers = list(dict.fromkeys(r.ticker for r in self.results))
        for ticker in tickers:
            print(f"\n  Generating charts for {ticker}...")
            self.plot_cumulative_returns(ticker)
            self.plot_return_bar(ticker)
            self.plot_drawdown(ticker)
            self.plot_risk_return(ticker)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def generate_markdown_report(results: list[StrategyResult], output_path: Path) -> None:
    lines = [
        "# Backtest Results Report",
        f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}",
        "\n---\n",
        "## Overview",
        "\nThis report compares 6 trading strategies on S&P 500 (^GSPC) and Gold (GLD) "
        "during Trump's second term (Jan 20, 2025 onward).",
        "\n---\n",
    ]

    tickers = list(dict.fromkeys(r.ticker for r in results))

    for ticker in tickers:
        ticker_results = [r for r in results if r.ticker == ticker and r.metrics]
        if not ticker_results:
            continue

        sorted_r = sorted(ticker_results,
                          key=lambda r: r.metrics.get("total_return_pct", -999),
                          reverse=True)

        lines.append(f"## {ticker}\n")

        # Table header
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

        winner = sorted_r[0]
        lines.append(f"\n### Winner: **{winner.name}**")
        m = winner.metrics
        lines.append(
            f"\nThe top-performing strategy for {ticker} was **{winner.name}** "
            f"with a total return of **{m['total_return_pct']:+.2f}%** "
            f"({m['annualised_return_pct']:+.2f}% annualised), "
            f"a Sharpe ratio of **{m['sharpe_ratio']:.3f}**, "
            f"and a maximum drawdown of **{m['max_drawdown_pct']:.2f}%**."
        )

        # Weekend strategy analysis
        weekend = next((r for r in ticker_results if "Weekend" in r.name), None)
        if weekend:
            wm = weekend.metrics
            lines.append(f"\n### Weekend Strategy Analysis ({ticker})")
            lines.append(
                f"\nThe Weekend (Buy Friday / Sell Monday) strategy achieved "
                f"**{wm['total_return_pct']:+.2f}%** total return across "
                f"**{wm['num_trades']} trades** with a win rate of "
                f"**{wm['win_rate_pct']}%** and Sharpe ratio of **{wm['sharpe_ratio']:.3f}**."
            )
            rank_pos = next((i + 1 for i, r in enumerate(sorted_r) if "Weekend" in r.name), "N/A")
            lines.append(f"It ranked **#{rank_pos}** out of {len(sorted_r)} strategies.")

        lines.append("\n---\n")

    lines.append("## Key Insights\n")
    lines.append(
        "- The **Weekend strategy** exploits potential gap dynamics between Friday close "
        "and Monday open, capturing weekend news sentiment.\n"
        "- **DCA strategies** reduce timing risk through systematic investing regardless of price.\n"
        "- **MA Crossover** tends to perform well in trending markets but lags in choppy conditions.\n"
        "- **RSI Mean Reversion** works best in range-bound markets; it may underperform during strong trends.\n"
        "- **Buy & Hold** often outperforms active strategies over longer time horizons due to "
        "lower transaction costs and full market exposure.\n"
    )

    lines.append("## Disclaimer\n")
    lines.append(
        "> Past performance is not indicative of future results. "
        "This analysis is for educational purposes only and does not constitute financial advice."
    )

    output_path.write_text("\n".join(lines))
    print(f"\n  Report saved to {output_path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Weekend Trading Backtester — Trump Term II Analysis",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--start-date", default="2025-01-20",
                        help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=date.today().isoformat(),
                        help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument("--tickers", nargs="+", default=["^GSPC", "GLD"],
                        help="Tickers to analyse")
    parser.add_argument("--capital", type=float, default=1000.0,
                        help="Capital per trade ($)")
    parser.add_argument("--transaction-cost", type=float, default=0.001,
                        help="Transaction cost as fraction (e.g. 0.001 = 0.1%%)")
    parser.add_argument("--strategies", nargs="+",
                        choices=list(STRATEGY_MAP.keys()),
                        default=list(STRATEGY_MAP.keys()),
                        help="Strategies to run (default: all)")
    parser.add_argument("--output-dir", default=".",
                        help="Directory for output files")
    parser.add_argument("--no-plots", action="store_true",
                        help="Skip generating plots")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "="*60)
    print("  WEEKEND TRADING BACKTESTER")
    print(f"  Period  : {args.start_date} → {args.end_date}")
    print(f"  Tickers : {', '.join(args.tickers)}")
    print(f"  Capital : ${args.capital:,.0f}/trade")
    print(f"  Tx Cost : {args.transaction_cost*100:.2f}%")
    print(f"  Strategies: {', '.join(args.strategies)}")
    print("="*60)

    backtester = Backtester(
        tickers=args.tickers,
        start_date=args.start_date,
        end_date=args.end_date,
        capital=args.capital,
        transaction_cost=args.transaction_cost,
        strategies=args.strategies,
    )

    print("\nRunning backtests...")
    results = backtester.run()

    if not results:
        print("\n[ERROR] No results generated. Check tickers and date range.")
        return

    backtester.print_summary()

    print("\nExporting trade logs...")
    backtester.export_trades(output_dir)
    backtester.export_summary(output_dir / "comparison_summary.csv")

    if not args.no_plots:
        print("\nGenerating visualisations...")
        viz = Visualizer(results, output_dir)
        viz.plot_all()

    print("\nGenerating markdown report...")
    generate_markdown_report(results, output_dir / "results.md")

    print("\n" + "="*60)
    print("  Done! Check the output directory for all files.")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
