"""Export the raw inputs a browser needs to run mean-variance optimization.

The expensive estimates (expected returns + covariance for every asset) are
computed here once; the efficient frontier for any subset of assets is then
solved client-side in docs/js/mvo.js by re-slicing this matrix, so toggling
assets is instant with no server round-trip.
"""
import numpy as np

from . import config, risk


def _frank_wolfe(mu, S, lam, iters=600):
    """max muᵀw − lam·wᵀSw  s.t.  Σw = 1, w ≥ 0 (same solver as the browser page)."""
    n = len(mu)
    w = np.full(n, 1.0 / n)
    for t in range(iters):
        grad = mu - 2 * lam * (S @ w)
        k = int(np.argmax(grad))
        gamma = 2.0 / (t + 2)
        w = (1 - gamma) * w
        w[k] += gamma
    return w


def max_sharpe(mu, sigma, rf, assets):
    """Best long-only tangency portfolio: sweep risk-aversion, keep the highest
    Sharpe. Matches the in-browser frontier's max-Sharpe point."""
    best = None
    for lam in np.exp(np.linspace(np.log(0.15), np.log(1200), 60)):
        w = _frank_wolfe(mu, sigma, lam)
        ret = float(mu @ w)
        vol = float(np.sqrt(max(w @ sigma @ w, 0.0)))
        sharpe = (ret - rf) / vol if vol > 0 else -np.inf
        if best is None or sharpe > best["sharpe"]:
            best = {"w": w, "ret": ret, "vol": vol, "sharpe": sharpe}
    weights = {assets[i]: float(best["w"][i]) for i in range(len(assets)) if best["w"][i] > 1e-3}
    return {"weights": weights, "ret": best["ret"], "vol": best["vol"], "sharpe": best["sharpe"]}


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

    # Precompute the best (max-Sharpe) long-only portfolio on historical means,
    # shown on the Holdings page as a benchmark against the live model-driven book.
    optimal_hist = max_sharpe(np.asarray(mu_hist), np.asarray(sigma),
                              config.RISK_FREE_RATE, assets)
    optimal_hist["sectors"] = {t: sectors[assets.index(t)] for t in optimal_hist["weights"]}

    return {
        "assets": assets,
        "sectors": sectors,
        "mu_hist": mu_hist.tolist(),
        "mu_alpha": mu_alpha.tolist(),
        "vol": vol.tolist(),
        "sigma": sigma.tolist(),
        "rf": config.RISK_FREE_RATE,
        "optimal_hist": optimal_hist,
    }
