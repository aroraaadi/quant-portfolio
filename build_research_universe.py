#!/usr/bin/env python3
"""Build the browser dataset for the search-driven MVO page.

Reads the backfilled yfinance return series (Return Series/*_daily_yf.csv) and the
S&P 500 constituents (for company names + sectors), and writes two files the MVO
page loads:
  docs/data/universe_index.json  - small search index (symbol, name, sector, ...)
  docs/data/returns_matrix.json  - aligned daily returns for every symbol

All expected-return / covariance math happens in the browser on the selected
subset, so this just ships the raw aligned returns + a searchable index.
"""
import csv
import io
import json
import ssl
import urllib.request
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
RS_DIR = BASE / "Return Series"
MANIFEST = BASE / "data" / "universe_sp500.json"
OUT_DIR = BASE / "docs" / "data"
SP500_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = ssl.create_default_context()

# Names + sectors for the held tickers that aren't S&P 500 constituents.
EXTRA_META = {
    "SHOP": ("Shopify", "Technology"), "MDA.TO": ("MDA Space", "Industrials"),
    "WULF": ("TeraWulf", "Financial Services"),
    "SCHG": ("Schwab US Large-Cap Growth ETF", "ETF"),
    "SOXL": ("Direxion Semiconductor Bull 3x ETF", "ETF"),
    "SHAZ": ("SHAZ ETF", "ETF"),
    "XIU.TO": ("iShares S&P/TSX 60 ETF", "ETF"),
    "XSP.TO": ("iShares S&P 500 CAD-Hedged ETF", "ETF"),
    "XNDU.TO": ("iShares Nasdaq 100 CAD-Hedged ETF", "ETF"),
}


def sp500_meta():
    req = urllib.request.Request(SP500_URL, headers={"User-Agent": "Mozilla/5.0"})
    txt = urllib.request.urlopen(req, timeout=30, context=_SSL).read().decode()
    out = {}
    for r in csv.DictReader(io.StringIO(txt)):
        out[r["Symbol"].replace(".", "-")] = (r["Security"], r.get("GICS Sector", ""))
    return out


def main():
    manifest = json.loads(MANIFEST.read_text())
    meta = sp500_meta()
    meta.update(EXTRA_META)

    series, index = {}, []
    for entry in manifest["symbols"]:
        sym = entry["symbol"]
        df = pd.read_csv(RS_DIR / entry["file"])
        df["datetime"] = df["datetime"].astype(str)
        s = pd.Series(df["return"].round(5).values, index=df["datetime"].values)
        series[sym] = s
        name, sector = meta.get(sym, (sym, ""))
        index.append({"symbol": sym, "name": name, "sector": sector or "Unknown",
                      "currency": entry["currency"], "in_sp500": entry["in_sp500"],
                      "rows": entry["rows"]})

    # Align every series to one common, sorted date axis (null where missing).
    matrix = pd.DataFrame(series).sort_index()
    dates = list(matrix.index)
    data = {sym: [None if pd.isna(v) else float(v) for v in matrix[sym].values]
            for sym in matrix.columns}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index.sort(key=lambda x: x["symbol"])
    (OUT_DIR / "universe_index.json").write_text(json.dumps(index, separators=(",", ":")))
    (OUT_DIR / "returns_matrix.json").write_text(
        json.dumps({"dates": dates, "data": data}, separators=(",", ":")))

    idx_kb = (OUT_DIR / "universe_index.json").stat().st_size / 1024
    mat_mb = (OUT_DIR / "returns_matrix.json").stat().st_size / 1024 / 1024
    print(f"universe_index.json: {len(index)} symbols ({idx_kb:.0f} KB)")
    print(f"returns_matrix.json: {len(dates)} dates x {len(data)} symbols ({mat_mb:.1f} MB)")


if __name__ == "__main__":
    main()
