# 📈 Stock/Market Backtesting Platform

A backtesting **engine written from scratch** (no backtesting library) with a FastAPI service and a small chart UI.

## Features (all implemented)
CSV import (Yahoo-style) · synthetic data generator · 4 strategies (SMA crossover, RSI mean-reversion, Donchian breakout, buy & hold) · event-loop engine with commission + slippage · total return, CAGR, volatility, Sharpe, max drawdown (+ duration), trades, win rate, avg win/loss, profit factor · benchmark vs buy & hold · strategy comparison · interactive SVG charts · CSV export.

> It does **not** predict markets. Backtests describe the past and overfit easily; the point of the project is the data-processing and simulation system.

## Run it
```bash
cd backtester
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://localhost:8000, click **Generate synthetic "DEMO"**, then **Run** or **Compare all**. API docs: `/docs`. Tests: `pytest -q`. Data lives in `prices.db` (override with `BACKTEST_DB=/path/file.db`).

**Real data:** download a CSV from Yahoo Finance (Historical Data → Download), then upload it in the UI or:
```bash
curl -X POST "localhost:8000/data/upload?symbol=AAPL" -F file=@AAPL.csv
curl -X POST localhost:8000/backtest -H 'content-type: application/json' \
  -d '{"symbol":"AAPL","strategy":"sma_cross","params":{"fast":50,"slow":200},"cash":10000}'
```
(The sandbox-built app has no live-data download because that needs an external API key/network; CSV import keeps it offline-friendly.)

## API
`GET /strategies` · `GET /symbols` · `POST /data/synthetic?symbol&days&seed` · `POST /data/upload?symbol=` · `POST /backtest` · `POST /compare` · `POST /export` (CSV).
Backtest body: `{symbol, strategy, params, cash, commission_bps, slippage_bps, start, end}`.
Strategy params: `sma_cross{fast,slow}`, `rsi_reversion{period,buy_below,sell_above}`, `breakout{lookback,exit_lookback}`.

## How the engine works (`app/engine.py`)
* A strategy returns a **target position per bar** using only data up to bar *t*.
* The engine loops bar by bar and **fills at bar t+1's open** → no look-ahead bias. A unit test hand-computes a trade to prove it.
* Whole shares only, costs on every fill, open position marked to market at the end.
* Metrics are computed from the daily equity curve (Sharpe annualised with √252, drawdown from running peak).

**Known limitations:** long-only, one asset, daily bars, no position sizing/stops, survivorship bias in whatever data you upload, `rf` assumed 0 in the API, no walk-forward validation. A sensible next step is parameter sweeps with out-of-sample testing. Complexity is O(n) per run, and vectorising the stateful loops is the obvious optimisation experiment.

## Troubleshooting: errors you are likely to hit
| Symptom | Cause | Fix |
|---|---|---|
| `Form data requires "python-multipart"` | Missing dependency | `pip install python-multipart` |
| `400 CSV needs 'Date' and 'Close' columns; found [...]` | Wrong header names or separator (`;`) | Use a comma CSV with `Date` and `Close` (`Adj Close` also accepted) |
| `400 Need at least 30 valid rows` | File mostly empty/`null` or dates unparsable | Check date format (`YYYY-MM-DD`) and remove junk rows |
| `404 No data for XYZ` | Symbol never imported (symbols are upper-cased) | `GET /symbols`; import first |
| `422 Bad strategy/params: fast must be < slow` | Invalid MA windows | Use e.g. `{"fast":50,"slow":200}` |
| `422 Bad strategy/params: ... unexpected keyword` | Param not valid for that strategy | See param list above |
| `422 Fewer than 30 bars in the selected range` | `start`/`end` too narrow | Widen the range |
| SMA(50/200) shows **0 trades** | Data shorter than ~250 bars or no crossover | Use more history or shorter windows (`20/60`) |
| Sharpe is `null` | Zero variance (never invested) | Strategy didn't trade in this range |
| UI chart empty + JSON error text | Forgot to generate/upload data | Click *Generate synthetic* first |
| Results differ from another tool | Different fill assumptions (next-open, costs), adjusted vs raw prices | Set `commission_bps`/`slippage_bps` to 0 and compare on the same price column |
| `sqlite3.OperationalError: unable to open database file` | `BACKTEST_DB` points at a missing directory | Create it or unset the variable |
| `ValueError: time data ... doesn't match format` (pandas 2+/3) | Mixed date formats in the CSV | Normalise dates; rows that fail to parse are dropped, all-bad files error |
| `Address already in use` | Port 8000 taken | `--port 8001` |
