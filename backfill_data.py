#!/usr/bin/env python3
"""Backfill 3y of daily history for the S&P 500 + everything in the account.

Source: yfinance (bulk, split/dividend-adjusted). IBKR TWS can't practically
fetch ~500 names (pacing limits + needs TWS running), so this is a separate,
internally-consistent yfinance dataset for the research side. The existing
`*_daily_ibkr.csv` files (the concentrated model's universe) are left untouched.

Writes `Return Series/{sym}_daily_yf.csv` (schema matches the IBKR files:
datetime,open,high,low,close,volume,return) and a manifest at
`data/universe_sp500.json`.

Run:  python3 backfill_data.py
"""
import csv
import io
import json
import ssl
import urllib.request
from pathlib import Path

import pandas as pd
import yfinance as yf

BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "Return Series"
MANIFEST = BASE / "data" / "universe_sp500.json"
SP500_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = ssl.create_default_context()

# Held tickers to include beyond the S&P 500 (yfinance symbols). CDR underlyings
# (AMZN, GOOG, ...) are already S&P 500 members; these are the ones that aren't.
OWNED_EXTRA = {
    "SHOP": "USD", "MDA.TO": "CAD", "WULF": "USD",       # non-S&P stocks
    "SCHG": "USD", "SOXL": "USD", "SHAZ": "USD", "SPCX": "USD",  # US ETFs
    "XIU.TO": "CAD", "XSP.TO": "CAD", "XNDU.TO": "CAD",  # TSX ETFs (CAD)
}


def sp500_symbols():
    req = urllib.request.Request(SP500_URL, headers={"User-Agent": "Mozilla/5.0"})
    txt = urllib.request.urlopen(req, timeout=30, context=_SSL).read().decode()
    rows = list(csv.DictReader(io.StringIO(txt)))
    # yfinance wants dashes, not dots (BRK.B -> BRK-B)
    return {r["Symbol"].replace(".", "-"): "USD" for r in rows}


def file_name(sym):
    return sym.replace(".", "_").replace("-", "_").lower() + "_daily_yf.csv"


def write_csv(sym, df):
    out = pd.DataFrame({
        "datetime": df.index.strftime("%Y%m%d"),
        "open": df["Open"].round(4), "high": df["High"].round(4),
        "low": df["Low"].round(4), "close": df["Close"].round(4),
        "volume": df["Volume"].fillna(0).astype("int64"),
    })
    out["return"] = df["Close"].pct_change().values
    out = out.dropna(subset=["return"])
    path = OUT_DIR / file_name(sym)
    out.to_csv(path, index=False)
    return len(out)


def main():
    OUT_DIR.mkdir(exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)

    universe = {**sp500_symbols(), **OWNED_EXTRA}
    symbols = sorted(universe)
    print(f"Universe: {len(symbols)} symbols (S&P 500 + {len(OWNED_EXTRA)} held extras)")

    manifest, failures = [], []
    batch = 40
    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i + batch]
        try:
            data = yf.download(chunk, period="3y", interval="1d", auto_adjust=True,
                               group_by="ticker", threads=True, progress=False)
        except Exception as exc:
            print(f"  batch {i//batch} download error: {exc}")
            failures += chunk
            continue
        for sym in chunk:
            try:
                df = data[sym] if len(chunk) > 1 else data
                df = df.dropna(how="all")
                if df.empty or df["Close"].dropna().shape[0] < 50:
                    failures.append(sym)
                    continue
                n = write_csv(sym, df)
                manifest.append({"symbol": sym, "currency": universe[sym],
                                 "file": file_name(sym), "rows": n,
                                 "in_sp500": sym not in OWNED_EXTRA})
            except Exception:
                failures.append(sym)
        print(f"  {min(i+batch, len(symbols))}/{len(symbols)} done "
              f"({len(manifest)} ok, {len(failures)} failed)")

    manifest.sort(key=lambda m: m["symbol"])
    MANIFEST.write_text(json.dumps(
        {"count": len(manifest), "source": "yfinance (3y daily, adjusted)",
         "symbols": manifest, "failed": sorted(failures)}, indent=1))
    print(f"\nWrote {len(manifest)} CSVs -> Return Series/*_daily_yf.csv")
    print(f"Manifest -> {MANIFEST.relative_to(BASE)}")
    if failures:
        print(f"Failed ({len(failures)}): {', '.join(sorted(failures)[:20])}"
              + (" ..." if len(failures) > 20 else ""))


if __name__ == "__main__":
    main()
