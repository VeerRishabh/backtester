import io, os
import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import data, engine, strategies

app = FastAPI(title="Backtesting Platform")
STATIC = os.path.join(os.path.dirname(__file__), "..", "static")

class Run(BaseModel):
    symbol: str
    strategy: str
    params: dict = {}
    cash: float = Field(10_000, gt=0)
    commission_bps: float = Field(5, ge=0)
    slippage_bps: float = Field(2, ge=0)
    start: str | None = None
    end: str | None = None

class Compare(BaseModel):
    symbol: str
    strategies: list[dict]          # [{"strategy": "sma_cross", "params": {...}}, ...]
    cash: float = 10_000

def _execute(r: Run):
    try: df = data.load(r.symbol)
    except KeyError as e: raise HTTPException(404, str(e))
    if r.start: df = df[df.date >= r.start]
    if r.end: df = df[df.date <= r.end]
    df = df.reset_index(drop=True)
    if len(df) < 30: raise HTTPException(422, "Fewer than 30 bars in the selected range")
    try: sig = strategies.signal(r.strategy, df, r.params)
    except (KeyError, TypeError, ValueError) as e: raise HTTPException(422, f"Bad strategy/params: {e}")
    eq, trades = engine.run(df, sig, r.cash, r.commission_bps, r.slippage_bps)
    return df, eq, trades

@app.get("/strategies")
def list_strategies(): return list(strategies.REGISTRY)

@app.get("/symbols")
def symbols(): return data.symbols()

@app.post("/data/synthetic")
def make_synth(symbol: str = "DEMO", days: int = 1500, seed: int = 7):
    if not 60 <= days <= 20000: raise HTTPException(422, "days must be 60..20000")
    return {"symbol": symbol.upper(), "rows": data.save(symbol, data.synthetic(days, seed))}

@app.post("/data/upload")
async def upload(symbol: str, file: UploadFile = File(...)):
    try: df = data.parse_csv(await file.read())
    except Exception as e: raise HTTPException(400, str(e))
    return {"symbol": symbol.upper(), "rows": data.save(symbol, df)}

@app.post("/backtest")
def backtest(r: Run):
    df, eq, trades = _execute(r)
    bh = engine.run(df, strategies.buy_hold(df), r.cash, r.commission_bps, r.slippage_bps)[0]
    return {"metrics": engine.metrics(eq, trades), "benchmark_metrics": engine.metrics(bh, []),
            "dates": eq.index.strftime("%Y-%m-%d").tolist(), "equity": eq.round(2).tolist(),
            "benchmark": bh.round(2).tolist(), "trades": trades}

@app.post("/compare")
def compare(c: Compare):
    out = []
    for s in c.strategies:
        df, eq, trades = _execute(Run(symbol=c.symbol, strategy=s["strategy"], params=s.get("params", {}), cash=c.cash))
        out.append({"strategy": s["strategy"], "params": s.get("params", {}), "metrics": engine.metrics(eq, trades),
                    "dates": eq.index.strftime("%Y-%m-%d").tolist(), "equity": eq.round(2).tolist()})
    return out

@app.post("/export")
def export(r: Run):
    """CSV with the daily equity curve; trades follow after a blank line."""
    _, eq, trades = _execute(r)
    buf = io.StringIO()
    eq.rename("equity").round(2).to_csv(buf, index_label="date")
    buf.write("\n"); pd.DataFrame(trades).to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{r.symbol}_{r.strategy}.csv"'})

app.mount("/static", StaticFiles(directory=STATIC), name="static")
@app.get("/")
def index(): return FileResponse(os.path.join(STATIC, "index.html"))
