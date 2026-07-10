"""Export the raw inputs a browser needs to run mean-variance optimization.

The expensive estimates (expected returns + covariance for every asset) are
computed here once; the efficient frontier for any subset of assets is then
solved client-side in docs/js/mvo.js by re-slicing this matrix, so toggling
assets is instant with no server round-trip.
"""
import numpy as np

from . import config, risk


def build_payload(returns, tradeable, sig):
    """Inputs for the browser MVO: expected returns (two flavors) + covariance.

    Only full-history (tradeable) names are included — a seasoning name has no
    stable covariance to offer.
    """
    assets = [t for t in config.TICKERS if t in tradeable]
    r = returns[assets]

    # Full-history Ledoit-Wolf covariance (stable / well-conditioned for MVO).
    sigma = risk.ledoit_wolf_cov(r, lookback=None)

    mu_hist = r.mean().values * config.TRADING_DAYS          # annualized realized mean
    mu_alpha = sig["alpha"].reindex(assets).fillna(0.0).values  # model composite alpha
    vol = np.sqrt(np.diag(sigma))
    sectors = [sig.loc[t, "sector"] if isinstance(sig.loc[t, "sector"], str) else "Unknown"
               for t in assets]

    return {
        "assets": assets,
        "sectors": sectors,
        "mu_hist": mu_hist.tolist(),
        "mu_alpha": mu_alpha.tolist(),
        "vol": vol.tolist(),
        "sigma": sigma.tolist(),
        "rf": config.RISK_FREE_RATE,
    }
