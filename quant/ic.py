"""Information-coefficient engine.

IC for a signal = the time-averaged Spearman rank correlation between its
cross-sectional scores at time t and forward returns over t -> t+h. A positive
IC means the signal has ranked winners above losers historically.

Momentum is computable now from price history alone. The fundamental signals
(value, quality, short) need point-in-time history, which only accrues as
data/fundamentals/*.json snapshots pile up. Until every signal has at least
MIN_IC_SNAPSHOTS, the composite keeps using the static config.SIGNAL_WEIGHTS and
this engine runs in report-only mode (ICs shown for validation). Once all signals
clear the bar, weights auto-switch to IC-implied (max(IC, 0), normalized).
"""
import json
import logging

import numpy as np
import pandas as pd
from scipy import stats

from . import config, signals

log = logging.getLogger(__name__)


def _spearman(scores, fwd):
    df = pd.concat([scores.rename("s"), fwd.rename("f")], axis=1).dropna()
    if len(df) < 4:
        return np.nan
    rho, _ = stats.spearmanr(df["s"], df["f"])
    return rho


def momentum_ic(returns, h=None, step=None):
    """Real, computable now: walk month-ends, correlate momentum score with the
    next h-day forward return."""
    h = config.IC_FWD_DAYS if h is None else h
    step = h if step is None else step
    look = config.MOMENTUM_LOOKBACK
    ics = []
    start = look + config.MOMENTUM_SKIP
    for t in range(start, len(returns) - h, step):
        window = returns.iloc[:t]
        mom = signals.momentum(window)
        fwd = (1 + returns.iloc[t:t + h].fillna(0.0)).prod() - 1
        ics.append(_spearman(mom, fwd))
    ics = [x for x in ics if not np.isnan(x)]
    return {"ic": float(np.mean(ics)) if ics else None,
            "periods": len(ics), "snapshots": len(ics)}


def _snapshot_ic(returns):
    """Value/quality/short IC from the accumulating fundamentals snapshots.

    Returns {signal: {ic, snapshots}} using pairs of consecutive dated snapshots:
    score names at snapshot date d, correlate with the return d -> next snapshot.
    """
    snaps = sorted(config.FUNDAMENTALS_DIR.glob("*.json"))
    dates = []
    funds = []
    for path in snaps:
        try:
            funds.append(json.loads(path.read_text()))
            dates.append(pd.Timestamp(path.stem))
        except Exception:
            continue
    out = {s: {"ic": None, "snapshots": 0} for s in ("value", "quality", "short_interest")}
    if len(dates) < 2:
        return out

    per_signal = {s: [] for s in out}
    for i in range(len(dates) - 1):
        d0, d1 = dates[i], dates[i + 1]
        window = returns[returns.index <= d0]
        if len(window) < config.MOMENTUM_LOOKBACK:
            continue
        try:
            sig = signals.build(funds[i], window)
        except Exception as exc:
            log.debug("snapshot IC build failed at %s: %s", d0, exc)
            continue
        fwd_slice = returns[(returns.index > d0) & (returns.index <= d1)]
        if fwd_slice.empty:
            continue
        fwd = (1 + fwd_slice.fillna(0.0)).prod() - 1
        for s in per_signal:
            per_signal[s].append(_spearman(sig[f"{s}_score"], fwd))
    for s in per_signal:
        vals = [x for x in per_signal[s] if not np.isnan(x)]
        out[s] = {"ic": float(np.mean(vals)) if vals else None, "snapshots": len(vals)}
    return out


def compute(returns):
    """Full IC report + the weights the composite should use.

    Returns (report_dict, weights_series). weights == config.SIGNAL_WEIGHTS unless
    every signal has >= MIN_IC_SNAPSHOTS, in which case IC-implied weights are used.
    """
    mom = momentum_ic(returns)
    snap = _snapshot_ic(returns)
    report = {
        "momentum": mom,
        "value": snap["value"],
        "quality": snap["quality"],
        "short_interest": snap["short_interest"],
        "fwd_days": config.IC_FWD_DAYS,
    }

    counts = {
        "momentum": mom["snapshots"],
        "value": snap["value"]["snapshots"],
        "quality": snap["quality"]["snapshots"],
        "short_interest": snap["short_interest"]["snapshots"],
    }
    enough = all(c >= config.MIN_IC_SNAPSHOTS for c in counts.values())

    if enough:
        ics = {k: max(report[k]["ic"] or 0.0, 0.0) for k in config.SIGNAL_WEIGHTS}
        total = sum(ics.values())
        if total > 0:
            weights = pd.Series({k: v / total for k, v in ics.items()})
            report["weighting"] = "ic-driven"
            report["weights"] = {k: round(v, 4) for k, v in weights.items()}
            return report, weights

    weights = pd.Series(config.SIGNAL_WEIGHTS)
    report["weighting"] = "static (fallback until every signal has "
    report["weighting"] += f"{config.MIN_IC_SNAPSHOTS} snapshots)"
    report["weights"] = dict(config.SIGNAL_WEIGHTS)
    report["snapshot_counts"] = counts
    return report, weights
