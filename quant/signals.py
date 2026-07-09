"""Cross-sectional signals -> composite alpha.

With N=18 names, raw z-scores are dominated by one or two outliers, so every
signal is scored with a Gaussianized rank: score = Phi^-1((rank - 0.5)/N).
The rank transform also does the job of winsorization. Missing data scores
neutral (0) rather than a fake extreme.
"""
import logging

import numpy as np
import pandas as pd
from scipy import stats

from . import config

log = logging.getLogger(__name__)


def gauss_rank(series):
    """Gaussianized cross-sectional rank; NaNs stay NaN (scored neutral later)."""
    valid = series.dropna()
    if len(valid) < 3:
        return pd.Series(np.nan, index=series.index)
    ranks = valid.rank()
    scores = stats.norm.ppf((ranks - 0.5) / len(valid))
    return pd.Series(scores, index=valid.index).reindex(series.index)


def _earnings_yield(rec):
    for field in ("trailingPE", "forwardPE"):
        pe = rec.get(field)
        if pe and pe > 0:
            return 1.0 / pe
    return np.nan  # negative/missing earnings -> neutral, not fake-cheap or fake-expensive


def _roic_stability(rec):
    quarters = rec.get("roic_quarters") or []
    if len(quarters) < 3:
        return np.nan
    return float(np.mean(quarters) / (np.std(quarters) + 0.01))


def momentum(returns):
    """12-1 momentum: total return over the lookback excluding the last month."""
    window = returns.iloc[-config.MOMENTUM_LOOKBACK:-config.MOMENTUM_SKIP]
    return (1 + window).prod() - 1


def build(fund, returns):
    """DataFrame ticker x {raw metrics, component scores, composite score, alpha}."""
    tickers = config.TICKERS
    raw = pd.DataFrame(index=tickers)
    raw["pe"] = [fund[t].get("trailingPE") for t in tickers]
    raw["earnings_yield"] = [_earnings_yield(fund[t]) for t in tickers]
    raw["roic_stability"] = [_roic_stability(fund[t]) for t in tickers]
    raw["roic_mean"] = [np.mean(fund[t]["roic_quarters"]) if fund[t].get("roic_quarters") else np.nan
                        for t in tickers]
    raw["short_pct"] = [fund[t].get("short_pct") for t in tickers]
    raw["momentum_12_1"] = momentum(returns).reindex(tickers)

    scores = pd.DataFrame(index=tickers)
    scores["value"] = gauss_rank(raw["earnings_yield"])
    scores["quality"] = gauss_rank(raw["roic_stability"])
    scores["momentum"] = gauss_rank(raw["momentum_12_1"])
    scores["short_interest"] = -gauss_rank(raw["short_pct"].astype(float))

    coverage = scores.notna()
    for t in tickers:
        gaps = [c for c in scores.columns if not coverage.at[t, c]]
        if gaps:
            log.warning("%s: missing %s -> scored neutral", t, gaps)

    weights = pd.Series(config.SIGNAL_WEIGHTS)
    composite = (scores.fillna(0.0) * weights).sum(axis=1)

    out = pd.concat([raw, scores.add_suffix("_score")], axis=1)
    out["composite"] = composite
    out["alpha"] = composite * config.ALPHA_SCALE
    out["coverage"] = coverage.sum(axis=1).astype(int).astype(str) + "/4"
    return out
