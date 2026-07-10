"""Single source of truth for the investable universe + benchmarks.

Both IBKRDATA.py (the daily price pull) and quant/config.py import from here, so
you change the universe in ONE place. To add a stock:
  1. Append a dict below (role="trade").
  2. Run IBKRDATA.py with TWS up to fetch its history.
  3. Run run_monthly.py — the name seasons (held out, shown as pending) until it
     has ~1 year of history, then enters the optimized book automatically.

Fields:
  symbol            IBKR ticker AND the CSV/base name used throughout the pipeline
  sec_type          "STK" | "IND"
  exchange          IBKR routing exchange (usually "SMART" for stocks)
  currency          "USD", "CAD", ...  (non-USD names get FX-converted to USD)
  primary_exchange  IBKR primaryExchange disambiguator (optional)
  yf                yfinance symbol (suffix for non-US listings, ^ for indices)
  role              "trade" (portfolio candidate) | "benchmark" (context only)
"""

UNIVERSE = [
    # --- Nasdaq-listed ---
    {"symbol": "AMZN", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NASDAQ", "yf": "AMZN", "role": "trade"},
    {"symbol": "AAPL", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NASDAQ", "yf": "AAPL", "role": "trade"},
    {"symbol": "NVDA", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NASDAQ", "yf": "NVDA", "role": "trade"},
    {"symbol": "GOOG", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NASDAQ", "yf": "GOOG", "role": "trade"},
    {"symbol": "META", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NASDAQ", "yf": "META", "role": "trade"},
    {"symbol": "AMD", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NASDAQ", "yf": "AMD", "role": "trade"},
    {"symbol": "MU", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NASDAQ", "yf": "MU", "role": "trade"},
    {"symbol": "COST", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NASDAQ", "yf": "COST", "role": "trade"},
    {"symbol": "MSFT", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NASDAQ", "yf": "MSFT", "role": "trade"},
    {"symbol": "AVGO", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NASDAQ", "yf": "AVGO", "role": "trade"},
    # --- NYSE-listed ---
    {"symbol": "BE", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NYSE", "yf": "BE", "role": "trade"},
    {"symbol": "JPM", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NYSE", "yf": "JPM", "role": "trade"},
    {"symbol": "SHOP", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NYSE", "yf": "SHOP", "role": "trade"},
    {"symbol": "SPGI", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NYSE", "yf": "SPGI", "role": "trade"},
    {"symbol": "GE", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NYSE", "yf": "GE", "role": "trade"},
    {"symbol": "APH", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NYSE", "yf": "APH", "role": "trade"},
    {"symbol": "NEE", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary_exchange": "NYSE", "yf": "NEE", "role": "trade"},
    # --- Non-USD (FX-converted to USD in the pipeline) ---
    {"symbol": "MDA", "sec_type": "STK", "exchange": "SMART", "currency": "CAD", "primary_exchange": "TSE", "yf": "MDA.TO", "role": "trade"},
    # --- Benchmarks (context only, never held) ---
    {"symbol": "SPX", "sec_type": "IND", "exchange": "CBOE", "currency": "USD", "yf": "^GSPC", "role": "benchmark"},
    {"symbol": "COMP", "sec_type": "IND", "exchange": "NASDAQ", "currency": "USD", "yf": "^IXIC", "role": "benchmark"},
]

_BY_SYMBOL = {u["symbol"]: u for u in UNIVERSE}


def by_symbol(symbol):
    return _BY_SYMBOL[symbol]


def trade_symbols():
    return [u["symbol"] for u in UNIVERSE if u["role"] == "trade"]


def benchmark_symbols():
    return [u["symbol"] for u in UNIVERSE if u["role"] == "benchmark"]


def all_symbols():
    return [u["symbol"] for u in UNIVERSE]


def non_usd_symbols():
    """{symbol: currency} for every trade/benchmark name not priced in USD."""
    return {u["symbol"]: u["currency"] for u in UNIVERSE if u["currency"] != "USD"}


def yf_symbol(symbol):
    return _BY_SYMBOL[symbol]["yf"]
