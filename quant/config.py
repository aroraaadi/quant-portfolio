"""All tunables in one place. Monthly tweaks should be one-line edits here."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RETURN_DIR = BASE_DIR / "Return Series"
DATA_DIR = BASE_DIR / "data"
FUNDAMENTALS_DIR = DATA_DIR / "fundamentals"
STATE_DIR = DATA_DIR / "state"
HOLDINGS_HISTORY = STATE_DIR / "holdings_history.json"
DOCS_DATA_DIR = BASE_DIR / "docs" / "data"
POSTS_DIR = BASE_DIR / "docs" / "posts"

TICKERS = [
    "AMZN", "AAPL", "NVDA", "BE", "GOOG", "MDA", "META", "JPM", "SHOP",
    "SPGI", "GE", "AMD", "MU", "COST", "APH", "MSFT", "AVGO", "NEE",
]
BENCHMARKS = ["SPX", "COMP"]
CSV_PATTERN = "{ticker}_daily_ibkr.csv"

# MDA trades on TSX in CAD; yfinance needs the .TO suffix and returns need FX conversion
YF_TICKER_MAP = {"MDA": "MDA.TO"}
CAD_TICKERS = {"MDA"}
FX_CACHE = DATA_DIR / "fx_cadusd.csv"

# --- Signals ---
SIGNAL_WEIGHTS = {
    "value": 0.30,          # earnings yield (1/PE)
    "quality": 0.30,        # ROIC stability (mean/std of quarterly ROIC)
    "momentum": 0.25,       # 12-1 month total return
    "short_interest": 0.15, # short % of float, negated (stale bi-weekly data -> lowest weight)
}
ALPHA_SCALE = 0.04          # annual alpha per unit of composite score (stated assumption)
MOMENTUM_LOOKBACK = 252     # ~12 months
MOMENTUM_SKIP = 21          # skip most recent month (short-term reversal)

# --- Risk model ---
RISK_MODEL = "pca"          # "pca" or "lw" (escape hatch)
RISK_LOOKBACK = 252
N_FACTORS = 3
TRADING_DAYS = 252

# --- Portfolio construction ---
# Band chosen to be feasible for a long-only, fully-invested portfolio of this
# high-beta universe (verified against the min-variance vol at runtime).
VOL_BAND = (0.12, 0.18)     # annualized
FULLY_INVESTED = True
MAX_WEIGHT = 0.20
PRUNE_THRESHOLD = 0.02      # drop positions below 2% and re-solve (concentration)
TC_GAMMA = 0.0020           # 20 bps per unit of one-way turnover in the objective
REBALANCE_COST_BPS = 10     # deducted from the live track record on rebalance days
RISK_FREE_RATE = 0.04       # for Sharpe
