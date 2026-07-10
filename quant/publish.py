"""Write the JSON files the website reads (docs/data/) and the posts index.

This module defines the Python <-> site contract; docs/js/*.js consumes
exactly these shapes. All floats rounded so git diffs stay readable.
"""
import json
import re
from pathlib import Path

import pandas as pd

from . import backtest, config


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1))


def _round(x, dp=4):
    return None if x is None or pd.isna(x) else round(float(x), dp)


def portfolio_json(as_of, weights, sig, report, pending=None):
    holdings = []
    for ticker, w in weights.sort_values(ascending=False).items():
        if w <= 0:
            continue
        row = sig.loc[ticker]
        holdings.append({
            "ticker": ticker,
            "sector": row.get("sector") if isinstance(row.get("sector"), str) else None,
            "weight": _round(w),
            "alpha_score": _round(row["composite"]),
            "signals": {
                "value": _round(row["value_score"]),
                "quality": _round(row["quality_score"]),
                "momentum": _round(row["momentum_score"]),
                "short_interest": _round(row["short_interest_score"]),
            },
            "raw": {
                "pe": _round(row["pe"], 1),
                "ev_ebitda_yield": _round(row.get("ev_ebitda_yield")),
                "fcf_yield": _round(row.get("fcf_yield")),
                "roic_mean": _round(row["roic_mean"]),
                "operating_margin": _round(row.get("operating_margin")),
                "roe": _round(row.get("roe")),
                "momentum_12_1": _round(row["momentum_12_1"]),
                "short_pct": _round(row["short_pct"]),
            },
        })
    pending_out = [{"ticker": t, "days": n, "needs": config.MIN_HISTORY_DAYS}
                   for t, n in sorted((pending or {}).items())]
    _write(config.DOCS_DATA_DIR / "portfolio.json", {
        "as_of": as_of,
        "vol_target_band": report["vol_band"],
        "model_vol": _round(report["model_vol"]),
        "vol_band_met": report["vol_band_met"],
        "min_var_vol": _round(report["min_var_vol"]),
        "n_positions": report["n_positions"],
        "sector_neutral": config.SECTOR_NEUTRAL,
        "pending": pending_out,
        "holdings": holdings,
    })


def signals_json(ic_report):
    _write(config.DOCS_DATA_DIR / "signals.json", ic_report)


def mvo_json(payload):
    """Expected returns + covariance for the browser efficient-frontier page."""
    oh = payload["optimal_hist"]
    out = {
        "assets": payload["assets"],
        "sectors": payload["sectors"],
        "rf": _round(payload["rf"]),
        "mu_hist": [_round(x) for x in payload["mu_hist"]],
        "mu_alpha": [_round(x, 5) for x in payload["mu_alpha"]],
        "vol": [_round(x) for x in payload["vol"]],
        "sigma": [[_round(x, 6) for x in row] for row in payload["sigma"]],
        "optimal_hist": {
            "weights": {t: _round(w) for t, w in oh["weights"].items()},
            "sectors": oh["sectors"],
            "ret": _round(oh["ret"]),
            "vol": _round(oh["vol"]),
            "sharpe": _round(oh["sharpe"], 2),
        },
    }
    _write(config.DOCS_DATA_DIR / "mvo.json", out)


def performance_json(returns, bench, history, weights):
    live = backtest.live_series(history, returns)
    live_start = str(live.index[0].date()) if len(live) else None

    hypo = backtest.buy_and_hold(weights, returns)
    # splice: hypothetical up to live_start, live after
    if len(live):
        port = pd.concat([hypo[hypo.index < live.index[0]], live])
    else:
        port = hypo

    idx = backtest.to_index(port)
    common = idx.index
    out = {
        "live_start": live_start,
        "dates": [str(d.date()) for d in common],
        "portfolio": [_round(v, 2) for v in idx],
        "stats": {"portfolio": backtest.stats(port),
                  "portfolio_live": backtest.stats(live) if len(live) else None},
    }
    for b in config.BENCHMARKS:
        series = bench[b].reindex(common).fillna(0.0)
        out[b.lower()] = [_round(v, 2) for v in backtest.to_index(series)]
        out["stats"][b.lower()] = backtest.stats(series)
    _write(config.DOCS_DATA_DIR / "performance.json", out)


def holdings_history_json(history):
    _write(config.DOCS_DATA_DIR / "holdings_history.json", history)


def risk_json(diag):
    exposures = {t: [_round(x) for x in row]
                 for t, row in zip(diag["tickers"], diag["loadings"])}
    _write(config.DOCS_DATA_DIR / "risk.json", {
        "factors_explained_var": [_round(v) for v in diag["explained_var"]],
        "eq_weight_vol": {k: _round(v) for k, v in diag["eq_weight_vol"].items()},
        "exposures": exposures,
    })


FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def posts_index():
    """Regenerate docs/posts/index.json from markdown front matter."""
    posts = []
    for md in sorted(config.POSTS_DIR.glob("*.md")):
        text = md.read_text()
        meta = {"slug": md.stem, "title": md.stem.replace("-", " ").title(),
                "date": "", "summary": ""}
        m = FRONT_MATTER.match(text)
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    if k.strip() in ("title", "date", "summary"):
                        meta[k.strip()] = v.strip()
        posts.append(meta)
    posts.sort(key=lambda p: p["date"], reverse=True)
    _write(config.POSTS_DIR / "index.json", posts)
    return posts
