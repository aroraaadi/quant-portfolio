"""Performance series: honest two-track design.

1. Live track record — chained from holdings_history entries, weights drift
   with daily returns between rebalances, turnover cost deducted on rebalance
   days. Grows forward only; zero lookahead. This is the headline.
2. Hypothetical context — current target weights held buy-and-hold over the
   full CSV history. Labeled as illustrative on the site (constructed with
   today's information; selection + lookahead bias).

No historical fundamentals exist yet, so a true historical signal backtest is
impossible today — the snapshots in data/fundamentals/ will enable one later.
"""
import numpy as np
import pandas as pd

from . import config


def buy_and_hold(weights, returns):
    """Daily portfolio return series for fixed initial weights, never rebalanced."""
    w = weights.reindex(returns.columns).fillna(0.0).values
    growth = (1 + returns).cumprod()          # value of $1 in each name
    value = growth @ w
    return pd.Series(value, index=returns.index).pct_change().fillna(
        pd.Series(returns.values @ w, index=returns.index))


def live_series(history, returns):
    """Chain rebalance entries into one daily return series.

    history: list of {date, weights, turnover} sorted by date. Between
    rebalances weights drift with returns; on each rebalance day a cost of
    REBALANCE_COST_BPS x one-way turnover is deducted.
    """
    if not history:
        return pd.Series(dtype=float)
    entries = sorted(history, key=lambda e: e["date"])
    start = pd.Timestamp(entries[0]["date"])
    dates = returns.index[returns.index >= start]
    out = []
    w = np.zeros(len(returns.columns))
    idx = 0
    for day in dates:
        cost = 0.0
        while idx < len(entries) and pd.Timestamp(entries[idx]["date"]) <= day:
            w = pd.Series(entries[idx]["weights"]).reindex(returns.columns).fillna(0.0).values
            cost = entries[idx].get("turnover", 0.0) * config.REBALANCE_COST_BPS / 1e4
            idx += 1
        r_day = returns.loc[day].values
        out.append(float(w @ r_day) - cost)
        # drift weights with the day's returns
        w = w * (1 + r_day)
        s = w.sum()
        if s > 0:
            w = w / s
    return pd.Series(out, index=dates)


def stats(returns_series):
    r = returns_series.dropna()
    if len(r) < 20:
        return None
    n_years = len(r) / config.TRADING_DAYS
    total = float((1 + r).prod())
    cagr = total ** (1 / n_years) - 1
    vol = float(r.std() * np.sqrt(config.TRADING_DAYS))
    sharpe = (cagr - config.RISK_FREE_RATE) / vol if vol > 0 else 0.0
    curve = (1 + r).cumprod()
    max_dd = float((curve / curve.cummax() - 1).min())
    return {"cagr": round(cagr, 4), "vol": round(vol, 4),
            "sharpe": round(sharpe, 2), "max_dd": round(max_dd, 4)}


def to_index(returns_series, base=100.0):
    """Cumulative index (starts at base) from a daily return series."""
    return base * (1 + returns_series.fillna(0.0)).cumprod()
