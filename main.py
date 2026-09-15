from __future__ import annotations

import argparse

import pandas as pd

from backtesting.comparisons import compare_core_variants
from backtesting.engine import HistoricalBacktestEngine
from backtesting.optimizer import default_phase3_grid, grid_search, summarize_sensitivity
from backtesting.out_of_sample import run_out_of_sample_validation, run_walk_forward_validation
from backtesting.reports import format_comparison_results, format_grid_results, format_out_of_sample_result, format_walk_forward_result
from execution.demo_bot import DemoTradingBot
from strategies.amin_xauusd_strategy import AminXauusdPhase1Strategy, load_settings
from tradingview.webhook import PINE_PATH, serve_tradingview_webhook


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 1 Amin FX-inspired XAU/USD research analysis.")
    parser.add_argument("--mode", choices=["analyze", "backtest", "optimize", "compare", "validate", "walk-forward", "demo", "tradingview"], default="analyze")
    parser.add_argument("--m15", help="Path to M15 OHLC CSV with timestamp, open, high, low, close columns.")
    parser.add_argument("--h1", help="Optional H1 OHLC CSV.")
    parser.add_argument("--h4", help="Optional H4 OHLC CSV.")
    parser.add_argument("--config", default="config/settings.yaml", help="Path to settings YAML.")
    parser.add_argument("--train-bars", type=int, default=500, help="Walk-forward training bars.")
    parser.add_argument("--validation-bars", type=int, default=200, help="Walk-forward validation bars.")
    parser.add_argument("--step-bars", type=int, default=200, help="Walk-forward step bars.")
    parser.add_argument("--once", action="store_true", help="Evaluate the demo bot once and exit.")
    args = parser.parse_args()

    settings = load_settings(args.config)
    if args.mode == "tradingview":
        print(f"Pine script: {PINE_PATH}")
        print("Add it to a TradingView XAUUSD M15 chart, then create an alert with webhook URL.")
        serve_tradingview_webhook(settings)
        return
    if args.mode == "demo":
        bot = DemoTradingBot(settings)
        result = bot.run(once=args.once, poll_seconds=int(settings.get("execution", {}).get("poll_seconds", 15)))
        if result:
            print(f"{result['status']}: {result['reason']}")
            decision = result["details"].get("decision")
            if decision:
                print(f"signal: {decision}")
        return

    if not args.m15:
        parser.error("--m15 is required unless --mode demo or --mode tradingview")
    m15 = pd.read_csv(args.m15, parse_dates=["timestamp"])
    h1 = pd.read_csv(args.h1, parse_dates=["timestamp"]) if args.h1 else None
    h4 = pd.read_csv(args.h4, parse_dates=["timestamp"]) if args.h4 else None

    if args.mode == "backtest":
        result = HistoricalBacktestEngine(settings).run(m15, h1, h4)
        print("Backtest Summary")
        for key, value in result.metrics.items():
            print(f"{key}: {value}")
        print(f"rejected_signals: {len(result.rejected_signals)}")
        return

    if args.mode == "optimize":
        results = grid_search(m15, settings, default_phase3_grid(), h1, h4)
        print(format_grid_results(results))
        print("")
        print("Sensitivity Summary")
        for key, value in summarize_sensitivity(results).items():
            print(f"{key}: {value}")
        return

    if args.mode == "compare":
        results = compare_core_variants(m15, settings, h1, h4)
        print(format_comparison_results(results))
        return

    if args.mode == "validate":
        result = run_out_of_sample_validation(m15, settings, default_phase3_grid())
        print(format_out_of_sample_result(result))
        return

    if args.mode == "walk-forward":
        result = run_walk_forward_validation(m15, settings, default_phase3_grid(), args.train_bars, args.validation_bars, args.step_bars)
        print(format_walk_forward_result(result))
        return

    strategy = AminXauusdPhase1Strategy(settings)
    decision = strategy.latest_decision(m15, h1, h4)
    print(strategy.explain(decision))


if __name__ == "__main__":
    main()
