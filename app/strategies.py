"""Each strategy maps a price DataFrame -> target position per bar (1 = long, 0 = flat).
Signals use only data up to and including bar t; the engine fills at bar t+1 (no look-ahead)."""
import numpy as np, pandas as pd

def buy_hold(df, **_): return pd.Series(1, index=df.index)

def sma_cross(df, fast=50, slow=200, **_):
    if fast >= slow: raise ValueError("fast must be < slow")
    f, s = df.close.rolling(fast).mean(), df.close.rolling(slow).mean()
    return (f > s).astype(int).where(s.notna(), 0)          # flat until the slow MA exists

def rsi_reversion(df, period=14, buy_below=30, sell_above=70, **_):
    d = df.close.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    pos, state = [], 0
    for v in rsi:                                            # stateful: hold between the two thresholds
        if v < buy_below: state = 1
        elif v > sell_above: state = 0
        pos.append(state)
    return pd.Series(pos, index=df.index)

def breakout(df, lookback=20, exit_lookback=10, **_):
    hi = df.close.rolling(lookback).max().shift(1); lo = df.close.rolling(exit_lookback).min().shift(1)
    pos, state = [], 0
    for c, h, l in zip(df.close, hi, lo):
        if not np.isnan(h) and c > h: state = 1
        elif not np.isnan(l) and c < l: state = 0
        pos.append(state)
    return pd.Series(pos, index=df.index)

REGISTRY = {"buy_hold": buy_hold, "sma_cross": sma_cross, "rsi_reversion": rsi_reversion, "breakout": breakout}

def signal(name, df, params):
    if name not in REGISTRY: raise KeyError(f"Unknown strategy '{name}'. Options: {list(REGISTRY)}")
    return REGISTRY[name](df, **(params or {}))
