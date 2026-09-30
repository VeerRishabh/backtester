"""Hand-written event-loop backtester (no backtesting library). Long-only, whole shares, costs on every fill."""
from dataclasses import dataclass, asdict
import numpy as np, pandas as pd

@dataclass
class Trade:
    entry_date: str; exit_date: str; entry_price: float; exit_price: float; shares: int; pnl: float; return_pct: float

def run(df: pd.DataFrame, target: pd.Series, cash=10_000.0, commission_bps=5.0, slippage_bps=2.0):
    cost = (commission_bps + slippage_bps) / 1e4
    shares, equity, trades, entry = 0, [], [], None
    open_, close, dates = df.open.to_numpy(), df.close.to_numpy(), df.date.dt.strftime("%Y-%m-%d").to_numpy()
    tgt = target.to_numpy()
    for i in range(len(df)):
        if i > 0:                                            # execute yesterday's decision at today's open
            want = tgt[i - 1]
            if want == 1 and shares == 0:
                px = open_[i] * (1 + cost)
                shares = int(cash // px)
                if shares: cash -= shares * px; entry = (dates[i], px, shares)
            elif want == 0 and shares > 0:
                px = open_[i] * (1 - cost)
                cash += shares * px
                trades.append(_close(entry, dates[i], px)); shares = 0; entry = None
        equity.append(cash + shares * close[i])
    if shares > 0:                                           # mark open position to market, record as a trade
        trades.append(_close(entry, dates[-1], close[-1] * (1 - cost)))
    return pd.Series(equity, index=df.date), [asdict(t) for t in trades]

def _close(entry, date, px):
    d, epx, n = entry
    return Trade(d, date, round(epx, 4), round(px, 4), n, round((px - epx) * n, 2), round((px / epx - 1) * 100, 3))

def metrics(equity: pd.Series, trades: list[dict], rf=0.0) -> dict:
    r = equity.pct_change().dropna()
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    total = equity.iloc[-1] / equity.iloc[0] - 1
    dd = equity / equity.cummax() - 1
    underwater, longest, cur = dd < 0, 0, 0
    for u in underwater: cur = cur + 1 if u else 0; longest = max(longest, cur)
    sd = r.std(ddof=1)
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]; losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    f = lambda x: None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), 4)
    return {"total_return_pct": f(total * 100), "cagr_pct": f(((1 + total) ** (1 / years) - 1) * 100),
            "volatility_pct": f(sd * np.sqrt(252) * 100),
            "sharpe": f((r.mean() - rf / 252) / sd * np.sqrt(252)) if sd and sd > 0 else None,
            "max_drawdown_pct": f(dd.min() * 100), "max_drawdown_days": longest,
            "trades": len(trades), "win_rate_pct": f(100 * len(wins) / len(trades)) if trades else None,
            "avg_win": f(np.mean(wins)) if wins else None, "avg_loss": f(np.mean(losses)) if losses else None,
            "profit_factor": f(sum(wins) / -sum(losses)) if losses and sum(losses) < 0 else None,
            "final_equity": f(equity.iloc[-1])}
