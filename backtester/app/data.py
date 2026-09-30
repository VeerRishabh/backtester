"""Price storage (SQLite via stdlib; swap for PostgreSQL by replacing these 4 functions)."""
import io, os, sqlite3
import numpy as np, pandas as pd

DB = lambda: os.getenv("BACKTEST_DB", "prices.db")

def _conn():
    c = sqlite3.connect(DB())
    c.execute("""CREATE TABLE IF NOT EXISTS prices(symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
                 volume REAL, PRIMARY KEY(symbol, date))""")
    return c

def save(symbol: str, df: pd.DataFrame) -> int:
    df = df.copy(); df["symbol"] = symbol.upper(); df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    with _conn() as c:
        c.execute("DELETE FROM prices WHERE symbol=?", (symbol.upper(),))
        c.executemany("INSERT INTO prices VALUES(?,?,?,?,?,?,?)",
                      df[["symbol", "date", "open", "high", "low", "close", "volume"]].itertuples(index=False, name=None))
    return len(df)

def load(symbol: str) -> pd.DataFrame:
    with _conn() as c:
        df = pd.read_sql_query("SELECT * FROM prices WHERE symbol=? ORDER BY date", c, params=(symbol.upper(),), parse_dates=["date"])
    if df.empty: raise KeyError(f"No data for {symbol.upper()}")
    return df.drop(columns="symbol").reset_index(drop=True)

def symbols() -> list[dict]:
    with _conn() as c:
        return [dict(symbol=s, rows=n, start=a, end=b) for s, n, a, b in
                c.execute("SELECT symbol, COUNT(*), MIN(date), MAX(date) FROM prices GROUP BY symbol")]

def parse_csv(raw: bytes) -> pd.DataFrame:
    """Accepts Yahoo-style CSVs: Date, Open, High, Low, Close, (Adj Close), Volume. Only Date+Close required."""
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    if "date" not in df or ("close" not in df and "adj_close" not in df):
        raise ValueError(f"CSV needs 'Date' and 'Close' columns; found {list(df.columns)}")
    if "adj_close" in df: df["close"] = df["adj_close"]       # prefer split/dividend-adjusted
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ("open", "high", "low", "volume"):
        if col not in df: df[col] = df["close"] if col != "volume" else 0.0
    df = df.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates("date")
    df = df[(df["close"] > 0)]
    if len(df) < 30: raise ValueError("Need at least 30 valid rows")
    return df[["date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)

def synthetic(days: int = 1500, seed: int = 7, start_price: float = 100.0) -> pd.DataFrame:
    """Geometric Brownian motion with a regime change so trend strategies have something to find."""
    rng = np.random.default_rng(seed)
    drift = np.where(np.arange(days) % 500 < 300, 0.0005, -0.0004)
    r = drift + rng.normal(0, 0.012, days)
    close = start_price * np.exp(np.cumsum(r))
    open_ = np.r_[start_price, close[:-1]] * (1 + rng.normal(0, 0.002, days))
    dates = pd.bdate_range("2018-01-01", periods=days)
    return pd.DataFrame({"date": dates, "open": open_, "high": np.maximum(open_, close) * 1.004,
                         "low": np.minimum(open_, close) * 0.996, "close": close, "volume": rng.integers(1e5, 1e6, days).astype(float)})
