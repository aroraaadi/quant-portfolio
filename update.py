#!/usr/bin/env python3
"""One-shot data refresh — runs the whole pipeline in dependency order.

  backfill_data.py          S&P 500 + holdings return series (yfinance)   [slow]
  build_research_universe   -> returns_matrix.json + universe_index.json
  questrade_sync.py         -> current_portfolio.json (+ local $ detail)
  parse_statements.py       -> portfolio_history.json + transactions.json
  compute_metrics.py        -> portfolio_metrics.json

Usage:
  python3 update.py           # full refresh (re-pulls ~510 names, a few minutes)
  python3 update.py --quick   # skip the S&P 500 backfill; holdings + metrics only

A failed Questrade sync (e.g. an expired token) is a warning, not a stop — the
rest still refresh from existing data.
"""
import argparse
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# (script, description, soft?) — soft steps warn and continue on failure.
SLOW = [
    ("backfill_data.py", "Backfill S&P 500 + holdings return series", False),
    ("build_research_universe.py", "Rebuild returns matrix + search index", False),
]
CORE = [
    ("questrade_sync.py", "Sync current holdings from Questrade", True),
    ("parse_statements.py", "Update equity curve + transaction log", False),
    ("compute_metrics.py", "Compute portfolio risk metrics", False),
]


def run(script, desc, soft):
    print(f"\n=== {desc}  ({script}) ===", flush=True)
    code = subprocess.run([sys.executable, str(BASE / script)]).returncode
    if code == 0:
        return
    if soft:
        print(f"WARNING: {script} failed (exit {code}); continuing with existing data.")
    else:
        sys.exit(f"ABORT: {script} failed (exit {code}) — fix it and re-run.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true",
                    help="skip the slow S&P 500 backfill; refresh holdings + metrics only")
    args = ap.parse_args()

    for script, desc, soft in (CORE if args.quick else [*SLOW, *CORE]):
        run(script, desc, soft)

    print("\nDone. Review docs/data, then publish:")
    print("  git add -A && git commit -m 'Update data' && git push")


if __name__ == "__main__":
    main()
