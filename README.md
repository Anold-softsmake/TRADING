# Amin FX-Inspired XAU/USD Research Bot

This project is a professional, modular research system for testing whether publicly observable Amin FX-style concepts can be converted into objective, statistically validated XAU/USD rules.

It is not Amin FX's proprietary strategy and does not claim to reproduce private trade rules.

## Current Scope: Phase 1

Phase 1 implements detection only:

- Swing highs/lows
- HH, HL, LH, LL labels
- BOS, CHoCH, MSS events
- Buy-side and sell-side liquidity pools
- Liquidity sweeps
- Order Blocks
- Fair Value Gaps
- Confluence scoring
- Candidate entry zones and invalidation levels

No live trading, demo trading, MT5 execution, or order placement exists in Phase 1.

## Required CSV Format

CSV files must include:

```text
timestamp,open,high,low,close
```

Optional fields such as volume and spread can be added later.

## Run

```bash
python main.py --m15 data/xauusd_m15.csv --h1 data/xauusd_h1.csv --h4 data/xauusd_h4.csv
```

## Phase 2 Backtest

```bash
python main.py --mode backtest --m15 data/xauusd_m15.csv --h1 data/xauusd_h1.csv --h4 data/xauusd_h4.csv
```

The historical backtester simulates:

- Candidate entry-zone fills after Phase 1 confirmation
- Invalidation-based stop loss
- TP1/TP2/TP3 partial exits
- Optional breakeven after TP1
- Fixed percent risk per setup
- Daily trade, daily loss, weekly loss, and consecutive-loss limits

Same-candle SL/TP ambiguity is conservative by default: if SL and TP are both reachable in the same candle, the stop is assumed first.

## Phase 3 Optimization

```bash
python main.py --mode optimize --m15 data/xauusd_m15.csv --h1 data/xauusd_h1.csv --h4 data/xauusd_h4.csv
```

Phase 3 adds ranked grid experiments and a sensitivity summary. The default grid tests:

- Confluence threshold
- Sweep displacement requirement
- OB/FVG overlap requirement
- Entry location
- Single TP versus TP1/TP2/TP3
- Breakeven versus no automatic breakeven

Run core component comparisons with:

```bash
python main.py --mode compare --m15 data/xauusd_m15.csv --h1 data/xauusd_h1.csv --h4 data/xauusd_h4.csv
```

Optimization results are research diagnostics, not proof of profitability. Any fragile result must be rejected or sent to out-of-sample validation.

## Phase 4 Out-of-Sample Validation

Run chronological train/validation/test validation:

```bash
python main.py --mode validate --m15 data/xauusd_m15.csv
```

Run walk-forward validation:

```bash
python main.py --mode walk-forward --m15 data/xauusd_m15.csv --train-bars 500 --validation-bars 200 --step-bars 200
```

The validation workflow:

- Optimizes only on the training split
- Applies the selected parameters to validation and test splits
- Reports objective decay from train to test
- Flags insufficient trade sample size
- Flags out-of-sample profit factor at or below breakeven

The test split must not be used for parameter selection.

## Look-Ahead Controls

- Swings are usable only after right-side confirmation candles close.
- Structure events are confirmed only at the break candle close.
- FVGs are known only after the third candle closes.
- Order Blocks are confirmed only after displacement and structure confirmation.
- The Phase 2 backtester must feed candles sequentially and only expose closed higher-timeframe candles.

## Phase 5 Demo Bot

The demo bot reads closed M15/H1/H4 candles from MetaTrader 5, scores the latest setup, then either logs a dry-run signal or submits a **demo** market order.

```bash
python main.py --mode demo --once
python main.py --mode demo
```

Rules:

- `execution.mode` must stay `DEMO`
- `execution.allow_live` must stay `false`
- `execution.dry_run: true` logs signals without sending orders
- Set `dry_run: false` only after you have a connected MT5 **demo** account
- Create `config/KILL_SWITCH` containing `ON` to block all new orders

Optional environment variables: `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_PATH`.

Install the Windows-only broker package when you are ready to connect:

```bash
pip install MetaTrader5
```

## TradingView Link

The bot receives TradingView alerts over a webhook. Chart logic lives in `tradingview/amin_xauusd.pine`. Risk limits, kill switch, and demo execution stay in Python.

1. Open `tradingview/amin_xauusd.pine` in TradingView Pine Editor and add it to **XAUUSD, 15 minutes**.
2. Set the Pine *Webhook secret* input to the same value as `tradingview.secret` in `config/settings.yaml` (or `TRADINGVIEW_WEBHOOK_SECRET`).
3. Start the webhook:

```bash
python main.py --mode tradingview
```

4. Expose it with a tunnel so TradingView can reach your PC:

```bash
ngrok http 8787
```

5. On the chart: **Alert** → condition **Amin XAUUSD TV Bridge** → *Any alert() function call* → webhook URL `https://YOUR-NGROK/webhook`.
6. Leave `execution.dry_run: true` until alerts look correct in `logs/demo_signals.jsonl`.

A local health check is `http://127.0.0.1:8787/health`.

## Safety

Live trading is refused. Demo mode is the only supported execution path. Keep `allow_live: false`.
