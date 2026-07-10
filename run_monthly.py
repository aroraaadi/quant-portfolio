#!/usr/bin/env python3
"""Monthly rebalance pipeline — run, review the printed tables, then git push.

Usage:
    python3 run_monthly.py               # full run: mutates state + site JSON
    python3 run_monthly.py --dry-run     # compute + print only, no state changes
    python3 run_monthly.py --use-cached  # reuse last fundamentals snapshot

Never touches git and never calls IBKRDATA.py (launchd owns the price refresh).
"""
import argparse
import json
import logging
import sys
from datetime import date

import numpy as np
import pandas as pd

from quant import config, data, fundamentals, ic, mvo, optimize, publish, risk, signals

log = logging.getLogger("run_monthly")


def _fmt(x):
    return "n/a" if x is None else f"{x:+.3f}"


def check_freshness(returns):
    last = returns.index.max()
    age = np.busday_count(last.date(), date.today())
    if age > 5:
        sys.exit(f"ABORT: return data is {age} business days old (last bar {last.date()}). "
                 "Check that TWS is running and the launchd job succeeded.")
    log.info("Data fresh: last bar %s (%d business days old)", last.date(), age)


def load_history():
    if config.HOLDINGS_HISTORY.exists():
        return json.loads(config.HOLDINGS_HISTORY.read_text())
    return []


def drifted_w0(history, returns):
    """Last rebalance weights drifted by returns since, as today's starting point."""
    if not history:
        return None
    last = sorted(history, key=lambda e: e["date"])[-1]
    w = pd.Series(last["weights"]).reindex(returns.columns).fillna(0.0)
    since = returns[returns.index > pd.Timestamp(last["date"])]
    growth = (1 + since).prod()
    w = w * growth
    return w / w.sum() if w.sum() > 0 else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="no state mutation")
    parser.add_argument("--use-cached", action="store_true", help="reuse last fundamentals snapshot")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)

    # 1. Data + freshness
    returns = data.load_returns()
    bench = data.load_benchmarks()
    check_freshness(returns)

    # Seasoning: names without enough history are held out of the optimizer.
    tradeable, pending = data.tradeable_universe(returns)
    if pending:
        print("\n=== PENDING (seasoning, held out) ===")
        for t, n in sorted(pending.items()):
            print(f"  {t}: {n}/{config.MIN_HISTORY_DAYS} days of history")

    # 2. Fundamentals (snapshotted to data/fundamentals/ before use)
    fund = fundamentals.fetch(use_cached=args.use_cached)

    # 3. Signal weighting (IC-driven once enough snapshots exist, else static)
    ic_report, sig_weights = ic.compute(returns)
    print(f"\n=== SIGNAL IC ({ic_report['weighting']}) ===")
    for s in ("value", "quality", "momentum", "short_interest"):
        r = ic_report[s]
        print(f"  {s:15s} IC={_fmt(r['ic'])}  ({r['snapshots']} snapshots)")

    # 4. Signals
    sig = signals.build(fund, returns, weights=sig_weights)
    print("\n=== SIGNALS (review before trading) ===")
    print(sig[["sector", "value_score", "quality_score", "momentum_score",
               "short_interest_score", "composite", "coverage"]].round(3)
          .sort_values("composite", ascending=False))

    # 5. Risk model (tradeable universe only)
    sigma, diag = risk.build(returns[tradeable])
    print(f"\nrisk factors explained variance: "
          f"{[round(v, 3) for v in diag['explained_var']]}")

    # 6. Optimize from drifted previous weights, over the tradeable set only
    history = load_history()
    w0 = drifted_w0(history, returns)
    weights, report = optimize.construct(sig["alpha"].reindex(tradeable), sigma,
                                         w0.reindex(tradeable) if w0 is not None else None)

    print("\n=== TARGET PORTFOLIO ===")
    tbl = pd.DataFrame({"target": weights[weights > 0]})
    if w0 is not None:
        tbl["previous"] = w0.reindex(tbl.index).fillna(0.0)
        tbl["change"] = tbl["target"] - tbl["previous"]
    print(tbl.sort_values("target", ascending=False).round(4))
    print(f"\nmodel vol {report['model_vol']:.1%}  band {report['vol_band']}  "
          f"met={report['vol_band_met']}  positions={report['n_positions']}  "
          f"one-way turnover {report['turnover_one_way']:.1%}")

    if args.dry_run:
        print("\n--dry-run: stopping before state mutation.")
        return

    # 6. Append to holdings history
    today = date.today().isoformat()
    history = [e for e in history if e["date"] != today]  # idempotent same-day rerun
    history.append({
        "date": today,
        "turnover": round(report["turnover_one_way"], 4),
        "model_vol": round(report["model_vol"], 4),
        "weights": {t: round(float(w), 4) for t, w in weights.items() if w > 0},
        "note": "initial portfolio" if len(history) == 0 else "monthly rebalance",
    })
    config.HOLDINGS_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    config.HOLDINGS_HISTORY.write_text(json.dumps(history, indent=1))

    # 7. Publish site JSON
    publish.portfolio_json(today, weights, sig, report, pending=pending)
    publish.performance_json(returns, bench, history, weights)
    publish.holdings_history_json(history)
    publish.risk_json(diag)
    publish.signals_json(ic_report)
    publish.mvo_json(mvo.build_payload(returns, tradeable, sig))
    posts = publish.posts_index()

    print(f"\nPublished docs/data/*.json  ({len(posts)} blog posts indexed)")
    print("Review changes, write a blog post if you like, then:")
    print("  git add -A && git commit -m 'Monthly rebalance' && git push")


if __name__ == "__main__":
    main()
