# Trump-Era Market Backtester

A modular Python backtesting framework and **interactive Streamlit dashboard** that analyses a **"Buy Friday, Sell Monday"** strategy on the S&P 500 (`^GSPC`) and Gold (`GLD`) during Trump's second term (Jan 20, 2025 – present), benchmarked against 5 common investment strategies.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Launch the interactive dashboard (recommended)
streamlit run app.py

# Or run the CLI tool directly
python backtest.py --tickers ^GSPC GLD --transaction-cost 0.001

# Custom date range and capital
python backtest.py --start-date 2025-01-20 --end-date 2025-12-31 --capital 500

# Run only specific strategies
python backtest.py --strategies weekend dca buyhold

# Save output to a specific directory
python backtest.py --output-dir ./results
```

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--start-date` | `2025-01-20` | Backtest start date (YYYY-MM-DD) |
| `--end-date` | Today | Backtest end date (YYYY-MM-DD) |
| `--tickers` | `^GSPC GLD` | Space-separated list of Yahoo Finance tickers |
| `--capital` | `1000` | Capital deployed per trade ($) |
| `--transaction-cost` | `0.001` | Round-trip cost fraction (0.001 = 0.1%) |
| `--strategies` | all | Subset: `weekend buyhold dca macrossover rsi monthlydca` |
| `--output-dir` | `.` | Directory for all output files |
| `--no-plots` | off | Skip matplotlib chart generation |

## Strategies

| Key | Name | Description |
|-----|------|-------------|
| `weekend` | Weekend (Fri→Mon) | Buy at Friday close, sell at Monday close. $1000 per cycle. |
| `buyhold` | Buy & Hold | Single lump-sum purchase at start, hold to end. |
| `dca` | Weekly DCA | Invest $1000 every Monday open regardless of price. |
| `macrossover` | MA Crossover (50/200) | Enter on Golden Cross (50 MA > 200 MA), exit on Death Cross. |
| `rsi` | RSI Mean Reversion | Buy when RSI < 30 (oversold), sell when RSI > 70 (overbought). |
| `monthlydca` | Monthly DCA | Invest $4000 on the first trading day of each month. |

## Output Files

After running, you'll find:

| File | Description |
|------|-------------|
| `comparison_summary.csv` | All metrics for all strategies × tickers |
| `trades_<strategy>_<ticker>.csv` | Individual trade log per strategy |
| `results.md` | Markdown report with winner analysis and insights |
| `cumulative_returns_<ticker>.png` | All 6 equity curves overlaid |
| `return_bar_<ticker>.png` | Bar chart of total returns ranked |
| `drawdown_<ticker>.png` | Drawdown comparison chart |
| `risk_return_<ticker>.png` | Sharpe ratio vs total return scatter |

## Metrics Calculated

- Total P&L ($) and Total Return (%)
- Annualised Return (%)
- Win Rate (% of profitable trades)
- Maximum Drawdown (%)
- Sharpe Ratio (annualised, risk-free rate = 0)
- Sortino Ratio (annualised)
- Number of trades
- Total transaction costs ($)

## Dashboard

The Streamlit dashboard (`app.py`) provides 6 interactive tabs:

| Tab | Contents |
|-----|----------|
| **Overview** | KPI cards (best/worst strategy, spread), ranked leaderboard table |
| **Performance** | Cumulative returns overlay, drawdown chart, daily return histograms |
| **Risk Analysis** | Sharpe vs Return scatter, annualised volatility bar, Sharpe/Sortino comparison |
| **Trade Explorer** | Filterable trade log, P&L bar chart, win/loss pie, monthly P&L heatmap |
| **Asset Comparison** | Cross-asset return heatmap, equity correlation, best strategy per asset |
| **Insights** | Auto-generated narrative insights + download buttons (CSV, ZIP, JSON, MD) |

### Sidebar Controls

- **Date range** — start/end date pickers
- **Assets** — multi-select from `^GSPC`, `GLD`, `QQQ`, `BTC-USD`, `TLT`, `SPY`, `IWM`, `DIA`
- **Strategies** — toggle each strategy on/off
- **Capital** — per-trade amount and transaction cost slider
- **Advanced params** (collapsible):
  - RSI: oversold/overbought thresholds, period
  - MA Crossover: short/long window
  - DCA: frequency (weekly / biweekly / monthly)

### Deployment to Streamlit Cloud

1. Push this repo to GitHub
2. Visit [share.streamlit.io](https://share.streamlit.io) and connect your repo
3. Set **Main file path** to `app.py`
4. Click **Deploy** — free hosting, no config needed

---

## Adding a New Strategy

1. Subclass `Strategy` in `backtest.py`
2. Implement `generate_signals()` and `execute_trades()`
3. Register it in `STRATEGY_MAP`

```python
class MyStrategy(Strategy):
    name = "My Custom Strategy"

    def generate_signals(self) -> pd.DataFrame:
        df = self.df.copy()
        # ... add signal logic ...
        df["signal"] = "buy"  # or "sell" or None
        df["price"] = df["Close"]
        return df[["price", "signal"]]

    def execute_trades(self, signals):
        # ... trade execution logic ...
        return trades, equity_curve, total_invested

# Register:
STRATEGY_MAP["mystrategy"] = MyStrategy
```

Then run: `python backtest.py --strategies mystrategy dca buyhold`

## Dependencies

```
yfinance>=0.2.40
pandas>=2.0.0
numpy>=1.24.0
matplotlib>=3.7.0
tabulate>=0.9.0
ta>=0.11.0
```

## Disclaimer

> This tool is for educational and research purposes only. Past performance does not guarantee future results. Nothing here constitutes financial advice.
