"""Risk model: statistical PCA factor model, Sigma = B F B^T + D (annualized).

Cross-checked every run against a constant-correlation Ledoit-Wolf shrinkage
estimator; config.RISK_MODEL = "lw" is the escape hatch if PCA misbehaves.
"""
import logging

import numpy as np

from . import config

log = logging.getLogger(__name__)


def pca_cov(returns):
    """(Sigma_annual, diagnostics) from the last RISK_LOOKBACK days of returns."""
    window = returns.iloc[-config.RISK_LOOKBACK:]
    x = window.values - window.values.mean(axis=0)
    sample = x.T @ x / (len(x) - 1)

    eigvals, eigvecs = np.linalg.eigh(sample)
    order = np.argsort(eigvals)[::-1]
    eigvals, eigvecs = eigvals[order], eigvecs[:, order]

    # Guard the factor count for a variable-size tradeable universe.
    n = sample.shape[0]
    k = min(config.N_FACTORS, max(1, n - 1))
    if k < config.N_FACTORS:
        log.warning("Only %d tradeable names — using %d risk factors (not %d)",
                    n, k, config.N_FACTORS)
    B = eigvecs[:, :k]                      # loadings
    F = np.diag(eigvals[:k])                # factor covariance
    common = B @ F @ B.T
    D = np.diag(np.maximum(np.diag(sample - common), 1e-8))
    sigma_daily = common + D

    diagnostics = {
        "explained_var": (eigvals[:k] / eigvals.sum()).tolist(),
        "loadings": B,                       # N x K, ordered like returns.columns
        "tickers": list(window.columns),
    }
    return sigma_daily * config.TRADING_DAYS, diagnostics


def ledoit_wolf_cov(returns):
    """Constant-correlation Ledoit-Wolf shrinkage (Honey, I Shrunk the Sample
    Covariance Matrix, 2004), annualized."""
    window = returns.iloc[-config.RISK_LOOKBACK:]
    x = window.values - window.values.mean(axis=0)
    t, n = x.shape
    sample = x.T @ x / t

    var = np.diag(sample)
    sd = np.sqrt(var)
    corr = sample / np.outer(sd, sd)
    rbar = (corr.sum() - n) / (n * (n - 1))
    prior = rbar * np.outer(sd, sd)
    np.fill_diagonal(prior, var)

    # pi-hat: sum of asymptotic variances of sample cov entries
    y = x ** 2
    phi_mat = (y.T @ y) / t - sample ** 2
    pihat = phi_mat.sum()
    # rho-hat: off-diagonal covariance term for the constant-correlation prior
    term1 = ((x ** 3).T @ x) / t
    theta_mat = term1 - var[:, None] * sample
    np.fill_diagonal(theta_mat, 0)
    rhohat = np.diag(phi_mat).sum() + rbar * ((1 / sd)[:, None] * sd[None, :] * theta_mat).sum()
    # gamma-hat: misspecification of the prior
    gammahat = np.linalg.norm(sample - prior, "fro") ** 2

    kappa = (pihat - rhohat) / gammahat
    delta = max(0.0, min(1.0, kappa / t))
    log.info("Ledoit-Wolf shrinkage intensity: %.3f", delta)
    sigma_daily = delta * prior + (1 - delta) * sample
    return sigma_daily * config.TRADING_DAYS


def build(returns):
    """Primary Sigma per config.RISK_MODEL, plus diagnostics and cross-check."""
    sigma_pca, diag = pca_cov(returns)
    sigma_lw = ledoit_wolf_cov(returns)

    n = len(returns.columns)
    w_eq = np.full(n, 1 / n)
    vol_pca = float(np.sqrt(w_eq @ sigma_pca @ w_eq))
    vol_lw = float(np.sqrt(w_eq @ sigma_lw @ w_eq))
    realized = returns.iloc[-config.RISK_LOOKBACK:].mean(axis=1)
    vol_real = float(realized.std() * np.sqrt(config.TRADING_DAYS))
    log.info("Equal-weight vol — PCA: %.1f%%  LW: %.1f%%  realized 252d: %.1f%%",
             vol_pca * 100, vol_lw * 100, vol_real * 100)
    if abs(vol_pca - vol_lw) / vol_lw > 0.20:
        log.warning("PCA and Ledoit-Wolf vols disagree by >20%% — inspect the risk model")

    diag["eq_weight_vol"] = {"pca": vol_pca, "lw": vol_lw, "realized": vol_real}
    sigma = sigma_lw if config.RISK_MODEL == "lw" else sigma_pca
    return sigma, diag
