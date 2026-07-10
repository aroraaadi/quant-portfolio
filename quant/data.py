"""Load IBKR return CSVs into an aligned daily returns matrix (USD).

The universe is dynamic (see universe.py): the number of names, their currencies,
and their history lengths all vary. Non-USD names are FX-converted to USD, and
names without enough history are flagged so the optimizer can hold them out.
"""
import logging

import pandas as pd

from . import config

log = logging.getLogger(__name__)


def _csv_path(ticker):
    return config.RETURN_DIR / config.CSV_PATTERN.format(ticker=ticker.lower())


def _load_series(ticker):
    path = _csv_path(ticker)
    if not path.exists():
        raise FileNotFoundError(
            f"No price CSV for {ticker} at {path.name} — run IBKRDATA.py "
            f"(with TWS running) to fetch it before rebalancing.")
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["datetime"].astype(str), format="%Y%m%d")
    return df.set_index("datetime")


def _fx_returns(currency):
    """Daily {CUR}USD FX returns, cached per currency so offline reruns work."""
    cache = config.FX_DIR / f"fx_{currency.lower()}usd.csv"
    try:
        import yfinance as yf
        fx = yf.Ticker(f"{currency}USD=X").history(period="4y")["Close"]
        fx.index = fx.index.tz_localize(None).normalize()
        cache.parent.mkdir(parents=True, exist_ok=True)
        fx.to_csv(cache)
    except Exception as exc:
        if not cache.exists():
            log.warning("%sUSD fetch failed (%s) and no cache — those names stay local", currency, exc)
            return None
        log.warning("%sUSD fetch failed (%s) — using cached FX", currency, exc)
    fx = pd.read_csv(cache, index_col=0, parse_dates=True)["Close"]
    return fx.pct_change().dropna()


def load_returns():
    """Aligned daily returns for the trade universe, non-USD names converted to USD.

    A name's returns are valid only from its first real bar (NaN before), so
    newly-added short-history names don't distort the panel. Isolated
    exchange-holiday gaps within a name's live window are treated as 0.
    """
    cols = {ticker: _load_series(ticker)["return"] for ticker in config.TICKERS}
    returns = pd.DataFrame(cols)

    # Generalized FX: convert every non-USD name via its currency's {CUR}USD series.
    fx_cache = {}
    for ticker, currency in config.NON_USD.items():
        if ticker not in returns.columns:
            continue
        if currency not in fx_cache:
            fx_cache[currency] = _fx_returns(currency)
        fx = fx_cache[currency]
        if fx is None:
            continue
        r_local = returns[ticker]
        r_fx = fx.reindex(r_local.index).fillna(0.0)
        converted = (1 + r_local) * (1 + r_fx) - 1
        returns[ticker] = converted.where(r_local.notna())  # keep pre-listing NaNs

    # Drop dates where most of the universe has no data (index-only rows etc.).
    min_names = max(3, len(config.TICKERS) - 2)
    returns = returns.dropna(thresh=min_names)
    # Fill only interior holiday gaps: a name gets 0 on days between its first and
    # last real bar, but stays NaN before it started trading (seasoning-aware).
    for ticker in returns.columns:
        s = returns[ticker]
        if s.notna().any():
            first = s.first_valid_index()
            returns.loc[first:, ticker] = returns.loc[first:, ticker].fillna(0.0)
    return returns


def history_lengths(returns):
    """{ticker: number of real (non-NaN) daily observations}."""
    return {t: int(returns[t].notna().sum()) for t in returns.columns}


def tradeable_universe(returns, min_days=None):
    """(tradeable, pending) split by history length.

    tradeable: names with >= min_days observations (optimizer allocates to these).
    pending:   {ticker: n_days} still seasoning (scored but held out).
    """
    min_days = config.MIN_HISTORY_DAYS if min_days is None else min_days
    lengths = history_lengths(returns)
    tradeable = [t for t in returns.columns if lengths[t] >= min_days]
    pending = {t: lengths[t] for t in returns.columns if lengths[t] < min_days}
    return tradeable, pending


def load_closes():
    return pd.DataFrame({t: _load_series(t)["close"] for t in config.TICKERS})


def load_benchmarks():
    return pd.DataFrame({b: _load_series(b)["return"] for b in config.BENCHMARKS}).dropna(how="all")
