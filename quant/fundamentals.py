"""Pull fundamentals from yfinance; snapshot every raw pull to disk first.

The dated snapshots in data/fundamentals/ build a true point-in-time history,
which is what will make an honest signal backtest possible in a year or so.
"""
import json
import logging
from datetime import date

import pandas as pd

from . import config

log = logging.getLogger(__name__)

INFO_FIELDS = [
    "trailingPE", "forwardPE", "shortPercentOfFloat", "sharesShort",
    "floatShares", "marketCap", "longName", "sector", "industry",
    "enterpriseToEbitda", "freeCashflow", "operatingMargins",
    "debtToEquity", "returnOnEquity",
]


def _quarterly_roic(tkr):
    """Quarterly ROIC = EBIT*(1-tax) / (debt + equity - cash) for available quarters."""
    inc = tkr.quarterly_income_stmt
    bal = tkr.quarterly_balance_sheet
    if inc is None or bal is None or inc.empty or bal.empty:
        return []
    roics = []
    for q in inc.columns:
        if q not in bal.columns:
            continue
        try:
            ebit = inc.at["EBIT", q] if "EBIT" in inc.index else None
            if ebit is None or pd.isna(ebit):
                continue
            pretax = inc.at["Pretax Income", q] if "Pretax Income" in inc.index else None
            tax = inc.at["Tax Provision", q] if "Tax Provision" in inc.index else None
            if pretax and tax is not None and not pd.isna(pretax) and pretax != 0:
                tau = min(max(float(tax) / float(pretax), 0.0), 0.35)
            else:
                tau = 0.21
            debt = bal.at["Total Debt", q] if "Total Debt" in bal.index else 0.0
            equity = bal.at["Stockholders Equity", q] if "Stockholders Equity" in bal.index else None
            cash = (bal.at["Cash And Cash Equivalents", q]
                    if "Cash And Cash Equivalents" in bal.index else 0.0)
            if equity is None or pd.isna(equity):
                continue
            debt = 0.0 if pd.isna(debt) else float(debt)
            cash = 0.0 if pd.isna(cash) else float(cash)
            invested = debt + float(equity) - cash
            if invested <= 0:
                continue
            roics.append(float(ebit) * (1 - tau) / invested)
        except Exception as exc:
            log.debug("ROIC for %s at %s failed: %s", tkr.ticker, q, exc)
    return roics


def fetch(use_cached=False):
    """Return {ticker: {pe, forward_pe, short_pct, roic_quarters, name}}."""
    snap_path = None
    if use_cached:
        snaps = sorted(config.FUNDAMENTALS_DIR.glob("*.json"))
        if snaps:
            snap_path = snaps[-1]
            log.info("Using cached fundamentals snapshot %s", snap_path.name)
            return json.loads(snap_path.read_text())
        log.warning("--use-cached requested but no snapshot exists; fetching live")

    import yfinance as yf

    out = {}
    for ticker in config.TICKERS:
        tkr = yf.Ticker(config.yf_symbol(ticker))
        try:
            info = tkr.info or {}
        except Exception as exc:
            log.warning("%s: info fetch failed (%s)", ticker, exc)
            info = {}
        rec = {k: info.get(k) for k in INFO_FIELDS}
        short_pct = rec.get("shortPercentOfFloat")
        if short_pct is None and rec.get("sharesShort") and rec.get("floatShares"):
            short_pct = rec["sharesShort"] / rec["floatShares"]
        rec["short_pct"] = short_pct
        rec["roic_quarters"] = _quarterly_roic(tkr)
        out[ticker] = rec
        log.info("%s: PE=%s short%%=%s roic_quarters=%d", ticker,
                 rec.get("trailingPE"), short_pct, len(rec["roic_quarters"]))

    config.FUNDAMENTALS_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = config.FUNDAMENTALS_DIR / f"{date.today().isoformat()}.json"
    snap_path.write_text(json.dumps(out, indent=1, default=str))
    log.info("Snapshot written to %s", snap_path)
    return out
