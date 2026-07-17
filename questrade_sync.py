#!/usr/bin/env python3
"""Pull the live portfolio from Questrade and write docs/data/current_portfolio.json.

Auth (Questrade OAuth 2.0, personal app):
  1. https://login.questrade.com/APIAccess/UserApps.aspx -> Register Personal App
     with read access to accounts / positions / balances.
  2. On that app: New Device -> Generate new token -> copy the refresh token.
  3. Put ONLY that token in a file named `.questrade_token` next to this script
     (already gitignored), or set env QUESTRADE_REFRESH_TOKEN. Never commit it.

Run:  python3 questrade_sync.py

Refresh tokens are single-use: each run redeems the token for an access token +
a NEW refresh token, and rewrites `.questrade_token` with the new one. If a run
fails after redemption you must generate a fresh token (the old one is spent).
Refresh tokens also expire after 3 days, so run at least that often (or on demand).
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
TOKEN_FILE = BASE / ".questrade_token"
OUT = BASE / "docs" / "data" / "current_portfolio.json"
LOGIN = "https://login.questrade.com/oauth2/token"

# TSX-listed CDRs (.TO) map to these US underlyings for the later risk/optimal work.
# (Display keeps the Questrade symbol; this is just metadata for downstream use.)


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def load_refresh_token():
    import os
    if os.environ.get("QUESTRADE_REFRESH_TOKEN"):
        return os.environ["QUESTRADE_REFRESH_TOKEN"].strip()
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    sys.exit(f"No refresh token. Put it in {TOKEN_FILE.name} or set "
             "QUESTRADE_REFRESH_TOKEN (see this file's docstring).")


def redeem(refresh_token):
    """Exchange the refresh token for an access token + api_server; rotate the token."""
    url = f"{LOGIN}?{urllib.parse.urlencode({'grant_type': 'refresh_token', 'refresh_token': refresh_token})}"
    tok = _get(url)
    # Persist the rotated refresh token immediately (it is single-use).
    TOKEN_FILE.write_text(tok["refresh_token"] + "\n")
    return tok["access_token"], tok["api_server"]


def usdcad_rate():
    """USD->CAD spot for base-currency weights. Falls back to 1.37 if offline."""
    try:
        import yfinance as yf
        px = yf.Ticker("USDCAD=X").history(period="5d")["Close"].dropna()
        return float(px.iloc[-1])
    except Exception:
        print("  (USDCAD fetch failed — using 1.37 fallback)")
        return 1.37


KIND = {"Stock": "stock", "Etf": "etf", "Option": "option", "Index": "index"}


def build_positions(api, headers):
    accounts = _get(f"{api}v1/accounts", headers)["accounts"]
    print(f"  accounts: {[a['number'] + ' (' + a['type'] + ')' for a in accounts]}")

    raw = []
    for acct in accounts:
        positions = _get(f"{api}v1/accounts/{acct['number']}/positions", headers)["positions"]
        for p in positions:
            raw.append(p)

    # Look up currency + security type per symbol (batched).
    ids = ",".join(str(p["symbolId"]) for p in raw if p.get("symbolId"))
    meta = {}
    if ids:
        for s in _get(f"{api}v1/symbols?ids={ids}", headers).get("symbols", []):
            meta[s["symbolId"]] = {"currency": s.get("currency", "CAD"),
                                   "kind": KIND.get(s.get("securityType"), "stock")}

    fx = usdcad_rate()
    rows, total_cad = [], 0.0
    for p in raw:
        m = meta.get(p.get("symbolId"), {"currency": "CAD", "kind": "stock"})
        mv = p.get("currentMarketValue", 0.0)
        cad = mv * (fx if m["currency"] == "USD" else 1.0)
        total_cad += cad
        rows.append({
            "symbol": p["symbol"],
            "kind": m["kind"],
            "currency": m["currency"],
            "_cad_value": cad,
            "mkt_value": round(mv, 2),
            "open_pnl": round(p.get("openPnl", 0.0), 2),
            "qty": p.get("openQuantity", 0),
            "avg_price": round(p.get("averageEntryPrice", 0.0), 4),
            "last_price": round(p.get("currentPrice", 0.0), 4),
        })
    for r in rows:
        r["weight"] = round(r.pop("_cad_value") / total_cad, 4) if total_cad else 0.0
    rows.sort(key=lambda r: r["weight"], reverse=True)

    # Aggregate P&L per currency from balances.
    pnl = {"CAD": 0.0, "USD": 0.0}
    for acct in accounts:
        for b in _get(f"{api}v1/accounts/{acct['number']}/balances", headers).get("perCurrencyBalances", []):
            if b["currency"] in pnl:
                pnl[b["currency"]] += b.get("realizedPnl", 0.0) + b.get("unrealizedPnl", 0.0)
    return rows, pnl


def main():
    from datetime import date
    refresh = load_refresh_token()
    print("Redeeming refresh token...")
    access, api = redeem(refresh)
    headers = {"Authorization": f"Bearer {access}"}
    print(f"  api_server: {api}")

    rows, pnl = build_positions(api, headers)
    payload = {
        "as_of": date.today().isoformat(),
        "source": "Questrade API (questrade_sync.py)",
        "base_currency": "CAD",
        "open_pnl_cad": round(pnl["CAD"], 2),
        "open_pnl_usd": round(pnl["USD"], 2),
        "note": "Weights are base-currency (CAD) market value / total. .TO symbols are "
                "TSX CDRs priced in CAD; the rest are USD. Market value and P&L are in "
                "each position's own currency.",
        "positions": rows,
    }
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {len(rows)} positions -> {OUT.relative_to(BASE)}")
    print("Review, then: git add -A && git commit -m 'Sync portfolio' && git push")


if __name__ == "__main__":
    main()
