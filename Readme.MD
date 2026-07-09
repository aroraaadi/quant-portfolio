Personal Portfolio

Goals:
-Create a portfolio
-Create a website to show the portfolio with holdings and methodolgies
-Options methodology to generate returns and protect risk


Portfolio
-High Returns
-Vol allowance 8%~125

Retutn forcasting (cross-sectional singlas, each z-scored across the universe)
-Value ~ P/E
-Quality ~ ROIC stability
-short interest

Risk Model
-Factor model, , Σ = B F Bᵀ + D (Barra-style fundamental, statistical/APCA, or hybrid; Ledoit–Wolf shrinkage if you're stuck with sample cov)

Portfolio Construction
-Objective is maximize αᵀw − λ·wᵀΣw − TC(w, w₀)

------------Parts-----------
Stocks of Interest
AMZN - Amazon
AAPL - Apple
NVDA - Nivida
BE - Bloom Energy
GOOG - Google
MDA - MDA Space
META - Meta
JPM - JPmorgan and chase
SHOP - Shopify
SPGI - S&P Global
GE - GE Aerospace
AMD - Advanced Micro Devices
MU - Micron
COST - Costco
APH - Amphenol
MSFT - Microsoft
AVGO - Broadcom 
NEE - Nextera Energy

Bench marks
SPY
NASDAQ Composite

----------- How to run -----------

Monthly rebalance (review output, then push):
    python3 run_monthly.py                # full run: signals -> risk -> optimize -> publish site JSON
    python3 run_monthly.py --dry-run      # compute and print only, no state changes
    python3 run_monthly.py --use-cached   # reuse last fundamentals snapshot (offline)

Then review, optionally add a blog post to docs/posts/ (markdown with
title/date/summary front matter), and:
    git add -A && git commit -m "Monthly rebalance" && git push

Preview the site locally:
    python3 -m http.server -d docs 8000   # then open http://localhost:8000

Layout:
    IBKRDATA.py          daily price pull from IBKR TWS (runs via launchd)
    quant/               signals, risk model, optimizer, backtest, publisher
    data/fundamentals/   dated yfinance snapshots (point-in-time archive)
    data/state/          holdings_history.json — source of truth per rebalance
    docs/                GitHub Pages site (dashboard, holdings, blog)

Signals: value (1/PE), quality (ROIC stability), 12-1 momentum, short interest —
each a Gaussianized cross-sectional rank, composite 30/30/25/15, alpha = score x 4%.
Risk: PCA 3-factor model (Sigma = BFB' + D) on trailing 252d, Ledoit-Wolf cross-check.
Construction: max a'w - lambda w'Sw - TC, long-only, sum(w)=1, w <= 20%, prune < 2%,
lambda bisected so vol lands in the 12-18% band.