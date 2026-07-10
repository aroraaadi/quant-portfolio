"""All tunables in one place. Monthly tweaks should be one-line edits here.

The universe itself (which stocks, currencies, yfinance symbols) lives in the
repo-root universe.py, which IBKRDATA.py also reads.
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
import universe  # noqa: E402

RETURN_DIR = BASE_DIR / "Return Series"
DATA_DIR = BASE_DIR / "data"
FUNDAMENTALS_DIR = DATA_DIR / "fundamentals"
STATE_DIR = DATA_DIR / "state"
HOLDINGS_HISTORY = STATE_DIR / "holdings_history.json"
DOCS_DATA_DIR = BASE_DIR / "docs" / "data"
POSTS_DIR = BASE_DIR / "docs" / "posts"
FX_DIR = DATA_DIR / "fx"

# Universe derived from universe.py (single source of truth)
TICKERS = universe.trade_symbols()
BENCHMARKS = universe.benchmark_symbols()
CSV_PATTERN = "{ticker}_daily_ibkr.csv"
# {symbol: currency} for any non-USD name -> FX-converted to USD in data.py
NON_USD = universe.non_usd_symbols()


def yf_symbol(ticker):
    return universe.yf_symbol(ticker)

# --- Signals ---
# Static top-level weights (the fallback until every signal has >= MIN_IC_SNAPSHOTS
# of history, at which point ic.py switches to IC-implied weights). Sub-metrics
# within each composite are equal-weighted.
SIGNAL_WEIGHTS = {
    "value": 0.30,          # earnings yield + EV/EBITDA yield + FCF yield
    "quality": 0.30,        # ROIC stability + operating margin + ROE + (neg) leverage
    "momentum": 0.25,       # 12-1 month total return
    "short_interest": 0.15, # short % of float, negated (stale bi-weekly data -> lowest weight)
}
ALPHA_SCALE = 0.04          # annual alpha per unit of composite score (stated assumption)
MOMENTUM_LOOKBACK = 252     # ~12 months
MOMENTUM_SKIP = 21          # skip most recent month (short-term reversal)
SECTOR_NEUTRAL = True       # neutralize every signal within GICS sector before ranking
MIN_IC_SNAPSHOTS = 6        # snapshots needed before a signal's weight goes IC-driven
IC_FWD_DAYS = 21            # forward-return horizon for information coefficient
MIN_HISTORY_DAYS = 252      # a name seasons until it has this many daily bars

# --- Risk model ---
RISK_MODEL = "pca"          # "pca" or "lw" (escape hatch)
RISK_LOOKBACK = 252
N_FACTORS = 3
TRADING_DAYS = 252

# --- Portfolio construction ---
# Band chosen to be feasible for a long-only, fully-invested portfolio of this
# high-beta universe (verified against the min-variance vol at runtime).
VOL_BAND = (0.12, 0.18)     # annualized
MAX_WEIGHT = 0.20
PRUNE_THRESHOLD = 0.02      # drop positions below 2% and re-solve (concentration)
TC_GAMMA = 0.0020           # 20 bps per unit of one-way turnover in the objective
REBALANCE_COST_BPS = 10     # deducted from the live track record on rebalance days
RISK_FREE_RATE = 0.04       # for Sharpe
