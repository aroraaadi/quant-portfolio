#!/usr/bin/env python3
"""Portfolio risk metrics from current holdings + return history.

Builds a daily return series by applying the CURRENT holding weights over the
past ~3 years (a current-holdings backtest — hypothetical, since weights change),
then derives beta, volatility, max drawdown, and Sharpe. Also reports the actual
time-weighted max drawdown from the monthly equity curve. All outputs are ratios
/ percentages — no dollar figures — so they are safe to publish.

Run:  python3 compute_metrics.py   (after build_research_universe.py)
"""
import csv
import json
import math
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
PF = BASE / "docs" / "data" / "current_portfolio.json"
MATRIX = BASE / "docs" / "data" / "returns_matrix.json"
HIST = BASE / "docs" / "data" / "portfolio_history.json"
SPX = BASE / "Return Series" / "spx_daily_ibkr.csv"
OUT = BASE / "docs" / "data" / "portfolio_metrics.json"
RF = 0.04
MIN_DAYS = 200   # exclude very-short-history names from the time series


def matrix_key(sym, data):
    if sym.endswith(".TO"):
        base = sym[:-3]
        return base if base in data else (sym if sym in data else None)
    return sym if sym in data else None


def max_drawdown(returns):
    curve = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(curve)
    return float((curve / peak - 1).min())


def main():
    pf = json.loads(PF.read_text())
    mat = json.loads(MATRIX.read_text())
    data, dates = mat["data"], mat["dates"]

    spx = {}
    with open(SPX) as f:
        for r in csv.DictReader(f):
            spx[r["datetime"]] = float(r["return"])
    mkt = np.array([spx.get(d, np.nan) for d in dates])

    # map holdings -> return columns; keep those with enough history
    cols, weights, covered, skipped = [], [], [], []
    for p in pf["positions"]:
        k = matrix_key(p["symbol"], data)
        if k is None:
            skipped.append(p["symbol"]); continue
        col = np.array([np.nan if v is None else v for v in data[k]])
        if (~np.isnan(col)).sum() < MIN_DAYS:
            skipped.append(p["symbol"] + "(short)"); continue
        cols.append(col); weights.append(p["weight"]); covered.append(p["symbol"])
    W = np.array(weights); W = W / W.sum()
    coverage = sum(weights)   # fraction of book covered (pre-renormalization)

    # common window where every covered name + the market have data
    M = np.vstack(cols)
    ok = ~np.isnan(M).any(axis=0) & ~np.isnan(mkt)
    port = (W[:, None] * M[:, ok]).sum(axis=0)   # daily portfolio return
    m = mkt[ok]
    n = len(port)

    vol = float(port.std(ddof=1) * math.sqrt(252))
    cagr = float(np.prod(1 + port) ** (252 / n) - 1)
    beta = float(np.cov(port, m)[0, 1] / np.var(m))
    mdd = max_drawdown(port)
    sharpe = (cagr - RF) / vol if vol else 0.0

    # actual max drawdown from the monthly time-weighted equity curve
    twr_mdd = None
    if HIST.exists():
        twr = np.array([h["twr_index"] for h in json.loads(HIST.read_text())], float)
        peak = np.maximum.accumulate(twr)
        twr_mdd = float((twr / peak - 1).min())

    out = {
        "as_of": pf["as_of"],
        "coverage_pct": round(coverage, 4),
        "window_days": n,
        "beta": round(beta, 2),
        "vol_annual": round(vol, 4),
        "max_drawdown": round(mdd, 4),
        "sharpe": round(sharpe, 2),
        "cagr": round(cagr, 4),
        "best_day": round(float(port.max()), 4),
        "worst_day": round(float(port.min()), 4),
        "twr_max_drawdown": round(twr_mdd, 4) if twr_mdd is not None else None,
        "note": "Daily metrics apply current holdings over the past ~3y (hypothetical). "
                "Max-drawdown (TWR) is the actual monthly equity-curve drawdown.",
    }
    OUT.write_text(json.dumps(out, indent=1))
    print(f"beta {beta:.2f}  vol {vol:.1%}  maxDD {mdd:.1%}  sharpe {sharpe:.2f}  "
          f"(current-holdings, {n}d, {coverage:.0%} of book)")
    print(f"actual TWR max drawdown: {twr_mdd:.1%}" if twr_mdd is not None else "")
    print("skipped:", skipped)


if __name__ == "__main__":
    main()
