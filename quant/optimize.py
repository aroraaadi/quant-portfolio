"""Portfolio construction: maximize alpha^T w - lambda w^T Sigma w - gamma ||w - w0||_1.

Long-only, fully invested, 20% position cap. Lambda is bisected so model vol
lands in config.VOL_BAND; if the band is unreachable long-only we pin to the
closest feasible vol and flag it honestly. Concentration comes from an
iterative prune: positions under PRUNE_THRESHOLD are dropped and the problem
re-solved on the survivors.
"""
import logging

import cvxpy as cp
import numpy as np
import pandas as pd

from . import config

log = logging.getLogger(__name__)


def _solve(alpha, sigma, w0, lam, gamma, allowed):
    n = len(alpha)
    w = cp.Variable(n)
    objective = alpha @ w - lam * cp.quad_form(w, cp.psd_wrap(sigma)) - gamma * cp.norm1(w - w0)
    upper = np.where(allowed, config.MAX_WEIGHT, 0.0)
    problem = cp.Problem(cp.Maximize(objective),
                         [cp.sum(w) == 1, w >= 0, w <= upper])
    problem.solve()
    if problem.status not in ("optimal", "optimal_inaccurate"):
        raise RuntimeError(f"solver status: {problem.status}")
    return np.maximum(w.value, 0.0)


def _vol(w, sigma):
    return float(np.sqrt(w @ sigma @ w))


def min_variance_vol(sigma, n):
    w = cp.Variable(n)
    cp.Problem(cp.Minimize(cp.quad_form(w, cp.psd_wrap(sigma))),
               [cp.sum(w) == 1, w >= 0, w <= config.MAX_WEIGHT]).solve()
    return _vol(np.maximum(w.value, 0.0), sigma)


def construct(alpha_series, sigma, w0_series=None):
    """Returns (weights Series, report dict)."""
    tickers = list(alpha_series.index)
    alpha = alpha_series.values
    n = len(alpha)
    w0 = (w0_series.reindex(tickers).fillna(0.0).values
          if w0_series is not None else np.zeros(n))
    gamma = config.TC_GAMMA if w0.sum() > 0 else 0.0  # initial buy-in cost is sunk

    lo, hi = config.VOL_BAND
    target = (lo + hi) / 2
    minvar = min_variance_vol(sigma, n)
    band_feasible = minvar <= hi
    if not band_feasible:
        log.warning("Vol band [%.1f%%, %.1f%%] unreachable long-only: min-var vol is %.1f%%. "
                    "Pinning to minimum variance.", lo * 100, hi * 100, minvar * 100)

    allowed = np.ones(n, dtype=bool)
    for iteration in range(5):
        # Bisection on log-lambda to land model vol in the band (vol is
        # monotone decreasing in lambda).
        log_lo, log_hi = -2.0, 5.0
        w, vol = None, None
        for _ in range(40):
            lam = 10 ** ((log_lo + log_hi) / 2)
            w = _solve(alpha, sigma, w0, lam, gamma, allowed)
            vol = _vol(w, sigma)
            if band_feasible and lo <= vol <= hi:
                break
            if vol > (target if band_feasible else minvar * 1.02):
                log_lo = (log_lo + log_hi) / 2  # too risky -> raise lambda
            else:
                log_hi = (log_lo + log_hi) / 2

        # Concentration: drop dust positions, re-solve on survivors.
        dust = (w < config.PRUNE_THRESHOLD) & allowed & (w > 1e-9)
        small = (w <= 1e-9) & allowed
        drop = dust | small
        if not drop.any() or (allowed & ~drop).sum() < 5:
            break
        allowed &= ~drop
        log.info("Prune iteration %d: dropped %s", iteration + 1,
                 [t for t, d in zip(tickers, drop) if d])

    weights = pd.Series(np.where(w < 1e-6, 0.0, w), index=tickers)
    weights /= weights.sum()
    turnover = float(np.abs(weights.values - w0).sum()) / 2  # one-way
    report = {
        "model_vol": _vol(weights.values, sigma),
        "min_var_vol": minvar,
        "vol_band": [lo, hi],
        "vol_band_met": bool(lo <= _vol(weights.values, sigma) <= hi),
        "lambda": lam,
        "n_positions": int((weights > 0).sum()),
        "turnover_one_way": turnover,
        "names_at_cap": [t for t, x in weights.items() if x > config.MAX_WEIGHT - 1e-4],
    }
    return weights, report
