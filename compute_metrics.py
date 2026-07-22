#!/usr/bin/env python3
"""Full risk-analytics package for the portfolio.

Builds a daily return series by applying the CURRENT holding weights over the
past ~3 years (a current-holdings backtest — hypothetical, since weights change),
then computes an institutional metric set: return/risk, market sensitivity
(incl. downside/upside beta, alpha, capture ratios, tracking error/IR), tail
risk (VaR/CVaR, skew/kurtosis), and concentration (HHI, sector/currency).

All outputs are ratios / percentages — no dollar figures — safe to publish.
Run:  python3 compute_metrics.py   (after build_research_universe.py + questrade_sync.py)
"""
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy import stats

BASE = Path(__file__).resolve().parent
PF = BASE / "docs" / "data" / "current_portfolio.json"
MATRIX = BASE / "docs" / "data" / "returns_matrix.json"
INDEX = BASE / "docs" / "data" / "universe_index.json"
HIST = BASE / "docs" / "data" / "portfolio_history.json"
SPX = BASE / "Return Series" / "spx_daily_ibkr.csv"
OUT = BASE / "docs" / "data" / "portfolio_metrics.json"
RF = 0.04
RF_D = RF / 252
MIN_DAYS = 200


def matrix_key(sym, data):
    if sym.endswith(".TO"):
        base = sym[:-3]
        return base if base in data else (sym if sym in data else None)
    return sym if sym in data else None


def max_drawdown(returns):
    curve = np.cumprod(1 + returns)
    dd = curve / np.maximum.accumulate(curve) - 1
    return float(dd.min()), dd


def ann_return(r, n):
    return float(np.prod(1 + r) ** (252 / n) - 1)


def beta_of(p, m):
    """cov(p,m)/var(m) — both from one sample covariance matrix (consistent ddof=1)."""
    C = np.cov(p, m)
    return float(C[0, 1] / C[1, 1])


def capture(port, mkt, mask):
    mm = mkt[mask].mean()                         # avg-return ratio on up/down days
    return float(port[mask].mean() / mm) if mm else None


SEC_ALIAS = {"Technology": "Information Technology", "Financial Services": "Financials",
             "Consumer Cyclical": "Consumer Discretionary"}


def main():
    pf = json.loads(PF.read_text())
    matrix = json.loads(MATRIX.read_text())
    data, dates_all = matrix["data"], matrix["dates"]
    sectors = {x["symbol"]: x["sector"] for x in json.loads(INDEX.read_text())}

    spx = {}
    with open(SPX) as f:
        for r in csv.DictReader(f):
            spx[r["datetime"]] = float(r["return"])
    mkt_all = np.array([spx.get(d, np.nan) for d in dates_all])

    # map holdings -> return columns (with enough history) for the time series
    cols, w_ts, skipped = [], [], []
    for p in pf["positions"]:
        k = matrix_key(p["symbol"], data)
        col = np.array([np.nan if v is None else v for v in data[k]]) if k else None
        if k is None or (~np.isnan(col)).sum() < MIN_DAYS:
            skipped.append(p["symbol"]); continue
        cols.append(col); w_ts.append(p["weight"])
    coverage = sum(w_ts)
    W = np.array(w_ts) / sum(w_ts)
    M = np.vstack(cols)
    ok = ~np.isnan(M).any(axis=0) & ~np.isnan(mkt_all)
    port = (W[:, None] * M[:, ok]).sum(axis=0)
    mkt = mkt_all[ok]
    dates = [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d, o in zip(dates_all, ok) if o]  # ISO
    n = len(port)

    # --- return & risk ---
    vol = float(port.std(ddof=1) * math.sqrt(252))
    cagr = ann_return(port, n)
    dd_min, dd_series = max_drawdown(port)
    below = np.minimum(port - RF_D, 0.0)          # downside relative to the risk-free MAR
    downside_dev = float(math.sqrt((below ** 2).mean()) * math.sqrt(252))
    sharpe = (cagr - RF) / vol if vol else 0.0
    sortino = (cagr - RF) / downside_dev if downside_dev else 0.0
    calmar = cagr / abs(dd_min) if dd_min else 0.0

    # --- market sensitivity ---
    dn, up = mkt < 0, mkt > 0
    beta = beta_of(port, mkt)
    beta_dn = beta_of(port[dn], mkt[dn])
    beta_up = beta_of(port[up], mkt[up])
    alpha_ann = float(((port - RF_D).mean() - beta * (mkt - RF_D).mean()) * 252)
    corr = float(np.corrcoef(port, mkt)[0, 1])
    te = float((port - mkt).std(ddof=1) * math.sqrt(252))
    ann_mkt = ann_return(mkt, n)
    info_ratio = (cagr - ann_mkt) / te if te else 0.0

    # --- tail risk ---
    q5 = np.percentile(port, 5)
    var95 = float(-q5)
    cvar95 = float(-port[port <= q5].mean())
    skew = float(stats.skew(port))
    kurt = float(stats.kurtosis(port))          # excess
    pct_pos = float((port > 0).mean())

    # --- concentration (HHI on renormalized weights) ---
    wv = np.array([p["weight"] for p in pf["positions"]], float)
    wv = wv / wv.sum()                            # published weights are rounded — renormalize
    hhi = float((wv ** 2).sum())
    ws = sorted(wv, reverse=True)
    sec, cur = {}, {}
    for p in pf["positions"]:
        k = matrix_key(p["symbol"], data)
        s = sectors.get(k, sectors.get(p["symbol"], "Other")) if k else "Other"
        s = SEC_ALIAS.get(s, s)
        sec[s] = sec.get(s, 0) + p["weight"]
        cur[p["currency"]] = cur.get(p["currency"], 0) + p["weight"]
    hhi_sector = float(sum(v ** 2 for v in sec.values()))
    hhi_cur = float(sum(v ** 2 for v in cur.values()))

    twr_mdd = None
    if HIST.exists():
        twr = np.array([h["twr_index"] for h in json.loads(HIST.read_text())], float)
        twr_mdd = float((twr / np.maximum.accumulate(twr) - 1).min())

    out = {
        "as_of": pf["as_of"], "coverage_pct": round(coverage, 4), "window_days": n,
        # return & risk
        "cagr": round(cagr, 4), "vol_annual": round(vol, 4), "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2), "calmar": round(calmar, 2),
        "max_drawdown": round(dd_min, 4), "downside_dev": round(downside_dev, 4),
        # market sensitivity
        "beta": round(beta, 2), "beta_down": round(beta_dn, 2), "beta_up": round(beta_up, 2),
        "beta_asymmetry": round(beta_up - beta_dn, 2), "alpha_annual": round(alpha_ann, 4),
        "correlation": round(corr, 2), "r2": round(corr ** 2, 2),
        "up_capture": round(capture(port, mkt, up), 2), "down_capture": round(capture(port, mkt, dn), 2),
        "tracking_error": round(te, 4), "information_ratio": round(info_ratio, 2),
        # tail
        "var95": round(var95, 4), "cvar95": round(cvar95, 4),
        "skew": round(skew, 2), "kurtosis": round(kurt, 2), "pct_positive": round(pct_pos, 4),
        "best_day": round(float(port.max()), 4), "worst_day": round(float(port.min()), 4),
        # concentration
        "hhi": round(hhi, 4), "effective_n": round(1 / hhi, 1),
        "top5_weight": round(sum(ws[:5]), 4), "top10_weight": round(sum(ws[:10]), 4),
        "hhi_sector": round(hhi_sector, 4), "hhi_currency": round(hhi_cur, 4),
        "sector_exposure": sorted([{"sector": k, "weight": round(v, 4)} for k, v in sec.items()],
                                  key=lambda x: -x["weight"]),
        "currency_exposure": [{"currency": k, "weight": round(v, 4)} for k, v in
                              sorted(cur.items(), key=lambda x: -x[1])],
        "twr_max_drawdown": round(twr_mdd, 4) if twr_mdd is not None else None,
        # series for charts (relative, no dollars)
        "series": {"dates": dates,
                   "port": [round(float(x), 5) for x in port],
                   "mkt": [round(float(x), 5) for x in mkt],
                   "drawdown": [round(float(x), 4) for x in dd_series]},
        "note": "Daily metrics apply current holdings over the past ~3y (hypothetical). "
                "Max-drawdown (TWR) is the actual monthly equity-curve drawdown.",
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"beta {beta:.2f} (dn {beta_dn:.2f}/up {beta_up:.2f})  vol {vol:.1%}  maxDD {dd_min:.1%}  "
          f"sharpe {sharpe:.2f}  sortino {sortino:.2f}  HHI {hhi:.3f} (eff N {1/hhi:.1f})")
    print(f"alpha {alpha_ann:+.1%}  VaR95 {var95:.1%}  CVaR95 {cvar95:.1%}  skew {skew:.2f}  "
          f"up/dn capture {out['up_capture']:.2f}/{out['down_capture']:.2f}  {coverage:.0%} of book")


if __name__ == "__main__":
    main()
