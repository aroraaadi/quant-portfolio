---
title: How this portfolio works
date: 2026-07-09
summary: The signals, the risk model, and the optimizer behind the book — and what the backtest does and doesn't claim.
---

This site tracks a concentrated, long-only equity portfolio built from a small
universe of 18 hand-picked names. This first post documents the machinery.

## Return forecasting

Each month every stock is scored cross-sectionally on four signals:

- **Value** — earnings yield (1/P/E). Cheaper is better; names with negative
  earnings score neutral rather than fake-cheap.
- **Quality** — ROIC stability: the mean of the last ~5 quarters of return on
  invested capital divided by its standard deviation. Rewards businesses that
  compound capital *consistently*.
- **Momentum** — trailing 12-month return excluding the most recent month.
- **Short interest** — short percent of float, negated. Crowded shorts are a
  headwind; this signal gets the smallest weight because the data is stale and
  reported bi-weekly.

With only 18 names, raw z-scores get dominated by outliers, so each signal is a
**Gaussianized rank**: ranks mapped through the inverse normal CDF, giving
scores from roughly −1.9 to +1.9. The composite is 30% value, 30% quality,
25% momentum, 15% short interest.

## Risk model

Covariance comes from a statistical factor model, **Σ = BFBᵀ + D**, estimated
on the trailing year of daily returns: B holds the loadings on the top three
principal components, F their variances, and D the leftover stock-specific
variance. The first factor is effectively the market; the model keeps the
optimizer from treating any single stock's quiet year as a free lunch. A
Ledoit–Wolf shrinkage estimate runs alongside every month as a cross-check.

## Portfolio construction

Weights maximize **αᵀw − λ·wᵀΣw − TC(w, w₀)**: expected alpha, minus a risk
penalty, minus a transaction-cost penalty on turnover from the current book.
Long-only, fully invested, 20% max position. λ is tuned so portfolio
volatility lands in a 12–18% annualized band, and positions under 2% are
pruned, which is what keeps the book concentrated — currently seven names.

## What the chart claims (and what it doesn't)

There is no historical database of point-in-time P/E, ROIC, and short-interest
for this universe, so a genuine multi-year signal backtest isn't possible yet.
Rather than fake one, the performance chart is split in two: everything before
the live date is **hypothetical** — today's weights applied backwards, with
selection and lookahead bias, shown only for context — and everything after it
is the **live track record**, computed from weights that were locked in before
the returns happened. Fundamentals get snapshotted every month, so a real
point-in-time backtest becomes possible as history accrues.
