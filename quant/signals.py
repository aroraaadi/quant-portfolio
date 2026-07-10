"""Cross-sectional signals -> composite alpha.

Each style signal is an equal-weighted composite of several sub-metrics. Every
sub-metric is sector-neutralized (so a "value" tilt is stock selection, not a
sector bet) and then Gaussianized-ranked across the universe: with N~18 names,
raw z-scores are outlier-dominated, so score = Phi^-1((rank - 0.5)/N). Missing
data scores neutral (0) rather than a fake extreme.

Sub-metrics per signal (all oriented so higher = better):
  value    : earnings yield (1/PE), EV/EBITDA yield (1/EV_EBITDA), FCF yield
  quality  : ROIC stability (mean/std of quarterly ROIC), operating margin,
             return on equity, negative leverage (-debt/equity)
  momentum : 12-1 month total return
  short    : negative short % of float
"""
import logging

import numpy as np
import pandas as pd
from scipy import stats

from . import config

log = logging.getLogger(__name__)

# Sub-metrics that make up each composite. Each entry names how to pull the raw
# value from the fundamentals record; momentum is filled from price returns.
VALUE_SUBS = ["earnings_yield", "ev_ebitda_yield", "fcf_yield"]
QUALITY_SUBS = ["roic_stability", "operating_margin", "roe", "neg_leverage"]


def gauss_rank(series):
    """Gaussianized cross-sectional rank; NaNs stay NaN (scored neutral later)."""
    valid = series.dropna()
    if len(valid) < 3:
        return pd.Series(np.nan, index=series.index)
    ranks = valid.rank()
    scores = stats.norm.ppf((ranks - 0.5) / len(valid))
    return pd.Series(scores, index=valid.index).reindex(series.index)


def sector_neutralize(metric, sectors):
    """Remove the sector mean from a raw metric before ranking.

    Shrunk by (n-1)/n within each sector so a singleton sector (n=1) keeps its
    raw value (shrink -> 0) instead of being zeroed, while a large sector gets
    near-full neutralization. No-op when config.SECTOR_NEUTRAL is False.
    """
    if not config.SECTOR_NEUTRAL:
        return metric
    out = metric.copy()
    for _, idx in sectors.groupby(sectors).groups.items():
        grp = metric.loc[idx].dropna()
        n = len(grp)
        if n == 0:
            continue
        shrink = (n - 1) / n
        out.loc[grp.index] = grp - shrink * grp.mean()
    return out


def _score(metric, sectors):
    return gauss_rank(sector_neutralize(metric, sectors))


def _earnings_yield(rec):
    for field in ("trailingPE", "forwardPE"):
        pe = rec.get(field)
        if pe and pe > 0:
            return 1.0 / pe
    return np.nan


def _ev_ebitda_yield(rec):
    ev = rec.get("enterpriseToEbitda")
    return 1.0 / ev if ev and ev > 0 else np.nan


def _fcf_yield(rec):
    fcf, mcap = rec.get("freeCashflow"), rec.get("marketCap")
    return fcf / mcap if fcf is not None and mcap else np.nan


def _roic_stability(rec):
    quarters = rec.get("roic_quarters") or []
    if len(quarters) < 3:
        return np.nan
    return float(np.mean(quarters) / (np.std(quarters) + 0.01))


def _neg_leverage(rec):
    d2e = rec.get("debtToEquity")
    return -float(d2e) if d2e is not None else np.nan


def momentum(returns):
    """12-1 momentum: total return over the lookback excluding the last month."""
    window = returns.iloc[-config.MOMENTUM_LOOKBACK:-config.MOMENTUM_SKIP]
    return (1 + window.fillna(0.0)).prod() - 1


def _raw_metrics(fund, returns, tickers):
    raw = pd.DataFrame(index=tickers)
    raw["sector"] = [fund[t].get("sector") or "Unknown" for t in tickers]
    raw["pe"] = [fund[t].get("trailingPE") for t in tickers]
    # value sub-metrics
    raw["earnings_yield"] = [_earnings_yield(fund[t]) for t in tickers]
    raw["ev_ebitda_yield"] = [_ev_ebitda_yield(fund[t]) for t in tickers]
    raw["fcf_yield"] = [_fcf_yield(fund[t]) for t in tickers]
    # quality sub-metrics
    raw["roic_stability"] = [_roic_stability(fund[t]) for t in tickers]
    raw["roic_mean"] = [np.mean(fund[t]["roic_quarters"]) if fund[t].get("roic_quarters") else np.nan
                        for t in tickers]
    raw["operating_margin"] = [fund[t].get("operatingMargins") for t in tickers]
    raw["roe"] = [fund[t].get("returnOnEquity") for t in tickers]
    raw["neg_leverage"] = [_neg_leverage(fund[t]) for t in tickers]
    # momentum / short
    raw["momentum_12_1"] = momentum(returns).reindex(tickers)
    raw["short_pct"] = [fund[t].get("short_pct") for t in tickers]
    return raw


def _composite_score(raw, subs, sectors):
    """Average of the available sub-metric scores per name (NaN if none present)."""
    sub_scores = pd.DataFrame(
        {s: _score(raw[s].astype(float), sectors) for s in subs}, index=raw.index)
    composite = sub_scores.mean(axis=1)   # ignores NaN sub-metrics automatically
    return composite, sub_scores


def build(fund, returns, weights=None):
    """DataFrame ticker x {raw metrics, signal scores, sub-scores, composite, alpha}.

    `weights` (optional dict/Series) overrides config.SIGNAL_WEIGHTS — used by the
    IC engine once enough history accrues.
    """
    tickers = config.TICKERS
    raw = _raw_metrics(fund, returns, tickers)
    sectors = raw["sector"]

    scores = pd.DataFrame(index=tickers)
    scores["value"], value_subs = _composite_score(raw, VALUE_SUBS, sectors)
    scores["quality"], quality_subs = _composite_score(raw, QUALITY_SUBS, sectors)
    scores["momentum"] = _score(raw["momentum_12_1"], sectors)
    scores["short_interest"] = -_score(raw["short_pct"].astype(float), sectors)

    coverage = scores.notna()
    for t in tickers:
        gaps = [c for c in scores.columns if not coverage.at[t, c]]
        if gaps:
            log.warning("%s: missing %s -> scored neutral", t, gaps)

    w = pd.Series(config.SIGNAL_WEIGHTS if weights is None else dict(weights))
    composite = (scores.fillna(0.0) * w).sum(axis=1)

    out = pd.concat([raw, scores.add_suffix("_score"),
                     value_subs.add_prefix("v_"), quality_subs.add_prefix("q_")], axis=1)
    out["composite"] = composite
    out["alpha"] = composite * config.ALPHA_SCALE
    out["coverage"] = coverage.sum(axis=1).astype(int).astype(str) + "/4"
    return out
