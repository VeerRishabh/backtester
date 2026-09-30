import os, tempfile
os.environ["BACKTEST_DB"] = os.path.join(tempfile.mkdtemp(), "p.db")
import numpy as np, pandas as pd
from fastapi.testclient import TestClient
from app import data, engine, strategies
from app.main import app

def frame(prices):
    n = len(prices); p = np.array(prices, float)
    return pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=n), "open": p, "high": p, "low": p, "close": p, "volume": 1.0})

def test_no_lookahead_and_hand_computed_trade():
    df = frame([10] * 5 + [20] * 5)                     # jump at bar 5
    sig = pd.Series([0, 0, 0, 0, 1, 1, 1, 1, 1, 0])     # decide long at bar 4, exit decided at bar 9
    eq, trades = engine.run(df, sig, cash=1000, commission_bps=0, slippage_bps=0)
    # Decision at bar 4 fills at bar 5's open (20): 50 shares. Sell decision at bar 9 has no next bar -> marked at close 20.
    assert trades[0]["shares"] == 50 and trades[0]["entry_price"] == 20 and eq.iloc[-1] == 1000

def test_costs_reduce_equity():
    df = frame(np.linspace(10, 20, 60)); sig = pd.Series(1, index=df.index)
    free = engine.run(df, sig, 1000, 0, 0)[0].iloc[-1]; costly = engine.run(df, sig, 1000, 50, 50)[0].iloc[-1]
    assert costly < free

def test_metrics_drawdown():
    eq = pd.Series([100, 120, 90, 110], index=pd.bdate_range("2020-01-01", periods=4))
    m = engine.metrics(eq, [])
    assert m["max_drawdown_pct"] == -25.0 and m["total_return_pct"] == 10.0

def test_sma_cross_rejects_bad_params():
    try: strategies.sma_cross(frame([1] * 50), fast=200, slow=50); assert False
    except ValueError: pass

def test_api_end_to_end():
    c = TestClient(app)
    assert c.post("/data/synthetic?symbol=demo").json()["rows"] == 1500
    r = c.post("/backtest", json={"symbol": "DEMO", "strategy": "sma_cross", "params": {"fast": 20, "slow": 60}}).json()
    assert r["metrics"]["trades"] > 0 and len(r["equity"]) == 1500
    assert c.post("/backtest", json={"symbol": "NOPE", "strategy": "sma_cross"}).status_code == 404
    assert c.post("/backtest", json={"symbol": "DEMO", "strategy": "nope"}).status_code == 422
    assert c.post("/export", json={"symbol": "DEMO", "strategy": "breakout"}).text.startswith("date,equity")
    assert len(c.post("/compare", json={"symbol": "DEMO", "strategies": [{"strategy": "buy_hold"}, {"strategy": "rsi_reversion"}]}).json()) == 2

def test_csv_upload_validation():
    c = TestClient(app)
    bad = c.post("/data/upload?symbol=X", files={"file": ("x.csv", b"foo,bar\n1,2\n")})
    assert bad.status_code == 400 and "Date" in bad.json()["detail"]
