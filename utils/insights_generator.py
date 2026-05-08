"""Auto-generate narrative insights from backtest results."""
from __future__ import annotations

import pandas as pd
from backtest import StrategyResult


def generate_insights(results: list[StrategyResult]) -> dict[str, list[str]]:
    """Return a dict of ticker -> list of insight strings."""
    insights: dict[str, list[str]] = {}

    tickers = list(dict.fromkeys(r.ticker for r in results))
    for ticker in tickers:
        tr = [r for r in results if r.ticker == ticker and r.metrics]
        if not tr:
            continue

        sorted_r = sorted(tr, key=lambda r: r.metrics.get("total_return_pct", -999), reverse=True)
        ticker_insights: list[str] = []

        best = sorted_r[0]
        worst = sorted_r[-1]
        bm = best.metrics
        wm = worst.metrics

        # Winner
        ticker_insights.append(
            f"**{bm['strategy']}** was the top performer for {ticker} with a total return of "
            f"**{bm['total_return_pct']:+.2f}%** ({bm['annualised_return_pct']:+.2f}% annualised)."
        )

        # Loser
        ticker_insights.append(
            f"**{wm['strategy']}** was the weakest performer with **{wm['total_return_pct']:+.2f}%** total return."
        )

        # Return spread
        spread = bm["total_return_pct"] - wm["total_return_pct"]
        ticker_insights.append(
            f"The strategy spread (best minus worst) was **{spread:.1f} percentage points**, "
            f"highlighting significant divergence in outcomes."
        )

        # Weekend vs Buy & Hold
        weekend = next((r for r in tr if "Weekend" in r.name or "Fri" in r.name), None)
        buyhold = next((r for r in tr if "Buy" in r.name and "Hold" in r.name), None)
        if weekend and buyhold:
            wkd_ret = weekend.metrics.get("total_return_pct", 0)
            bh_ret = buyhold.metrics.get("total_return_pct", 0)
            if wkd_ret > bh_ret:
                ticker_insights.append(
                    f"The Weekend (Fri→Mon) strategy **outperformed** Buy & Hold by "
                    f"**{wkd_ret - bh_ret:.2f}pp** ({wkd_ret:+.2f}% vs {bh_ret:+.2f}%)."
                )
            else:
                ticker_insights.append(
                    f"Buy & Hold **outperformed** the Weekend strategy by "
                    f"**{bh_ret - wkd_ret:.2f}pp** ({bh_ret:+.2f}% vs {wkd_ret:+.2f}%)."
                )

        # Best Sharpe
        best_sharpe = max(tr, key=lambda r: r.metrics.get("sharpe_ratio", 0))
        bs = best_sharpe.metrics
        ticker_insights.append(
            f"**{bs['strategy']}** had the best risk-adjusted return with a Sharpe ratio of **{bs['sharpe_ratio']:.3f}**."
        )

        # Worst drawdown
        worst_dd = min(tr, key=lambda r: r.metrics.get("max_drawdown_pct", 0))
        wd = worst_dd.metrics
        ticker_insights.append(
            f"**{wd['strategy']}** suffered the deepest peak-to-trough decline at **{wd['max_drawdown_pct']:.2f}%**."
        )

        # DCA comparison
        dca = next((r for r in tr if "DCA" in r.name and "Monthly" not in r.name), None)
        monthly_dca = next((r for r in tr if "Monthly DCA" in r.name), None)
        if dca and monthly_dca:
            d_ret = dca.metrics.get("total_return_pct", 0)
            m_ret = monthly_dca.metrics.get("total_return_pct", 0)
            winner_label = dca.metrics["strategy"] if d_ret > m_ret else monthly_dca.metrics["strategy"]
            ticker_insights.append(
                f"Between DCA variants, **{winner_label}** came out ahead "
                f"({d_ret:+.2f}% weekly vs {m_ret:+.2f}% monthly)."
            )

        # Transaction cost observation
        high_cost = max(tr, key=lambda r: r.metrics.get("total_transaction_costs", 0))
        hc = high_cost.metrics
        if hc.get("total_transaction_costs", 0) > 0:
            ticker_insights.append(
                f"**{hc['strategy']}** incurred the highest transaction costs: "
                f"**${hc['total_transaction_costs']:,.2f}** across {hc['num_trades']} trades."
            )

        insights[ticker] = ticker_insights

    return insights
