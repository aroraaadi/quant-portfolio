"""Load IBKR return CSVs into an aligned daily returns matrix (USD)."""
import logging

import pandas as pd

from . import config

log = logging.getLogger(__name__)


def _load_series(ticker):
    path = config.RETURN_DIR / config.CSV_PATTERN.format(ticker=ticker.lower())
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["datetime"].astype(str), format="%Y%m%d")
    return df.set_index("datetime")


def _cadusd_returns():
    """Daily CADUSD FX returns, cached to CSV so offline reruns work."""
    try:
        import yfinance as yf
        fx = yf.Ticker("CADUSD=X").history(period="4y")["Close"]
        fx.index = fx.index.tz_localize(None).normalize()
        config.FX_CACHE.parent.mkdir(parents=True, exist_ok=True)
        fx.to_csv(config.FX_CACHE)
    except Exception as exc:
        if not config.FX_CACHE.exists():
            log.warning("CADUSD fetch failed (%s) and no cache — MDA stays CAD-local", exc)
            return None
        log.warning("CADUSD fetch failed (%s) — using cached FX", exc)
    fx = pd.read_csv(config.FX_CACHE, index_col=0, parse_dates=True)["Close"]
    return fx.pct_change().dropna()


def load_returns():
    """Aligned daily returns for the 18-stock universe, MDA converted to USD."""
    cols = {}
    for ticker in config.TICKERS:
        cols[ticker] = _load_series(ticker)["return"]
    returns = pd.DataFrame(cols)

    fx = _cadusd_returns()
    if fx is not None:
        for ticker in config.CAD_TICKERS:
            r_cad = returns[ticker]
            r_fx = fx.reindex(r_cad.index).fillna(0.0)
            returns[ticker] = (1 + r_cad) * (1 + r_fx) - 1

    # Drop dates where most of the universe is missing (index-only rows etc.);
    # isolated exchange-holiday gaps (TSX vs NYSE) count as 0 return.
    returns = returns.dropna(thresh=len(config.TICKERS) - 2)
    return returns.fillna(0.0)


def load_closes():
    return pd.DataFrame({t: _load_series(t)["close"] for t in config.TICKERS})


def load_benchmarks():
    return pd.DataFrame({b: _load_series(b)["return"] for b in config.BENCHMARKS}).dropna(how="all")
