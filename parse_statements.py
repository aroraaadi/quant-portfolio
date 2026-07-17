#!/usr/bin/env python3
"""Parse CIBC Investor's Edge monthly eStatements into the site's history data.

The raw PDFs (Past transaction/) contain personal info (name, address, account #)
and are gitignored. This writes:
  data/state/statements_raw.json  (gitignored) - full parse WITH dollars, local only
  docs/data/portfolio_history.json (published)  - indexed series only, NO dollars
  docs/data/transactions.json      (published)  - ledger with RELATIVE sizes, NO dollars

Run:  python3 parse_statements.py
"""
import calendar
import json
import re
from pathlib import Path

from pypdf import PdfReader

BASE = Path(__file__).resolve().parent
PDF_DIR = BASE / "Past transaction"
RAW_OUT = BASE / "data" / "state" / "statements_raw.json"
HIST_OUT = BASE / "docs" / "data" / "portfolio_history.json"
TX_OUT = BASE / "docs" / "data" / "transactions.json"
SPX_CSV = BASE / "Return Series" / "spx_daily_ibkr.csv"
CUR_PORTFOLIO = BASE / "docs" / "data" / "current_portfolio.json"

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
DATE_RE = re.compile(r"^([A-Z][a-z]{2})\s+(\d{1,2})$")
NUM_RE = re.compile(r"^-?[\d,]+\.\d+$")
INT_RE = re.compile(r"^-?[\d,]+$")
AMT_RE = re.compile(r"^-?\$[\d,]+\.\d\d$")
BOILER = {"UNSOLICITED", "WE ARE ACTING AS PRINCIPAL", "SECURITIES OF A RELATED ISSUER",
          "WE ARE ACTING AS AGENT", "REG S"}
SKIP_DESC = ("Opening cash balance", "Closing cash balance")
KNOWN_ACT = {"Bought": "buy", "Sold": "sell", "Contrib": "contribution",
             "Dividend": "dividend", "Withdraw": "withdrawal", "Interest": "interest",
             "Reinvest": "reinvest"}
# Strip anything sensitive from published descriptions: dollar amounts, account
# numbers, and share counts. Applied before publishing — the public site must
# carry no absolute dollars or identifying numbers.
_SCRUB = [
    re.compile(r"-?\$[\d,]+\.?\d*"),
    re.compile(r"account\s*#?\s*[\d\-]+", re.I),
    re.compile(r"\bON\s+[\d,]+\s*SH(?:S|ARES)?\b", re.I),
    re.compile(r"(ORD\s*#|REQ:|FX ORD).*", re.I),   # order references (contain the holder's id)
    re.compile(r"ARORA\w*", re.I),
]


def money(tok):
    return float(tok.replace("$", "").replace(",", ""))


# Page header/footer + column-header lines that bleed into blocks across page
# breaks. Dropping them also removes the account holder's name/address.
_NOISE = re.compile(
    r"^(date|activity|description|quantity|price|amount|\$|—|"
    r"page \d+ of \d+|\d{5,6}|SEE OVER.*|Investor's Edge.*|Tax Free Savings.*|"
    r"Order Execution.*|ADITYA ARORA|.*ELLESMERE.*|.*WELLESLEY.*|SCARBOROUGH.*|"
    r"TORONTO.*|Account #.*|To Contact Us.*|www\.investorsedge.*|1-800.*|"
    r"[A-Z][a-z]+ \d+-[A-Z][a-z]+ \d+, \d{4}.*|\(previous statement.*|"
    r"Items For Your Attention.*|Account Activity.*)$", re.I)
# Cut a security description at boilerplate tails (dividend dates, FX, tax, etc.)
_TAIL = re.compile(r"\b(CASH DIV|DIST REC|REC [A-Z]{3}|PAY [A-Z]{3}|EXCHANGE RATE|"
                   r"NON-RES TAX|RECORD DATE|EFFECTIVE|CUSIP|ISIN)\b", re.I)


def strip_noise(section):
    return "\n".join(l for l in section.splitlines() if not _NOISE.match(l.strip()))


def clean_desc(s):
    cut = _TAIL.search(s)
    if cut:
        s = s[:cut.start()]
    for rx in _SCRUB:
        s = rx.sub("", s)
    s = s.replace("$", "")
    s = re.sub(r"\b\d{4,}\b", "", s)
    return re.sub(r"\s+", " ", s).strip(" -")[:60]


def classify(activity, text):
    if activity in KNOWN_ACT:
        return KNOWN_ACT[activity]
    t = (activity + " " + text).upper()
    for kw, lab in [("TAX", "tax"), ("DIVIDEND", "dividend"), ("CASH DIV", "dividend"),
                    ("MERGER", "merger"), ("CONVERSION", "conversion"),
                    ("FEE", "fee"), ("INTEREST", "interest"), ("CONTRIB", "contribution")]:
        if kw in t:
            return lab
    return "other"


def parse_activity(section, year, currency, tx):
    lines = [l.strip() for l in section.splitlines()]
    i = 0
    while i < len(lines):
        m = DATE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        mon, day = MONTHS[m.group(1)], int(m.group(2))
        # collect this block until the next date line
        j = i + 1
        block = []
        while j < len(lines) and not DATE_RE.match(lines[j]):
            if lines[j] and lines[j] != "$":
                block.append(lines[j])
            j += 1
        i = j
        if not block:
            continue
        activity_col = block[0]
        rest = block[1:]
        if any(s in " ".join(block) for s in SKIP_DESC):
            continue
        # trailing numeric fields: amount ($) last, optional price, optional qty
        amount = price = qty = None
        if rest and AMT_RE.match(rest[-1]):
            amount = money(rest.pop())
        if rest and NUM_RE.match(rest[-1]):
            price = float(rest.pop().replace(",", ""))
        if rest and INT_RE.match(rest[-1]):
            qty = int(rest.pop().replace(",", ""))
        activity = classify(activity_col, " ".join(block))
        # cash events get a fixed label; security events keep the (scrubbed) name
        fixed = {"contribution": "Contribution", "withdrawal": "Withdrawal",
                 "tax": "Non-resident tax withheld", "fee": "Fee", "interest": "Interest",
                 "conversion": "Currency conversion"}
        if activity in fixed:
            desc = fixed[activity]
        else:
            desc_src = rest if activity_col in KNOWN_ACT else [activity_col] + rest
            desc = clean_desc(" ".join(l for l in desc_src if l not in BOILER and l != "—"))
        if not desc:
            continue
        tx.append({"date": f"{year:04d}-{mon:02d}-{day:02d}",
                   "activity": activity, "description": desc, "currency": currency,
                   "qty": qty, "price": price, "amount": amount})


def parse_statement(path):
    year, month = int(path.stem[:4]), int(path.stem[5:7])
    txt = "\n".join(p.extract_text() for p in PdfReader(str(path)).pages)

    mv = re.search(r"total portfolio\s*\n[\d.]+%\s*\n\$([\d,]+\.\d\d)", txt)
    month_end = money(mv.group(1)) if mv else None
    cv = re.search(r"Contributions\s*\n\$([\d,]+\.\d\d)", txt)
    wv = re.search(r"Withdrawals\s*\n\$([\d,]+\.\d\d)", txt)
    contrib = money(cv.group(1)) if cv else 0.0
    withdraw = money(wv.group(1)) if wv else 0.0

    tx = []
    for cur, tag in [("CAD", "Canadian Dollars"), ("USD", "U.S. Dollars")]:
        for m in re.finditer(rf"Account Activity — {re.escape(tag)}(?: \(continued\))?", txt):
            end = txt.find("Account Activity", m.end())
            seg = txt[m.end():end if end > 0 else len(txt)]
            parse_activity(strip_noise(seg), year, cur, tx)

    last_day = calendar.monthrange(year, month)[1]
    return {"period": f"{year}-{month:02d}", "date": f"{year:04d}-{month:02d}-{last_day:02d}",
            "month_end_value": month_end, "contributions": contrib, "withdrawals": withdraw,
            "transactions": tx}


def spx_monthly(dates):
    import csv
    closes = {}
    with open(SPX_CSV) as f:
        for row in csv.DictReader(f):
            closes[row["datetime"]] = float(row["close"])
    keys = sorted(closes)
    out = []
    for d in dates:
        key = d.replace("-", "")
        prior = [k for k in keys if k <= key]
        out.append(closes[prior[-1]] if prior else None)
    return out


def main():
    stmts = [parse_statement(p) for p in sorted(PDF_DIR.glob("*.pdf"))]
    stmts = [s for s in stmts if s["month_end_value"]]
    RAW_OUT.parent.mkdir(parents=True, exist_ok=True)
    RAW_OUT.write_text(json.dumps({"statements": stmts}, indent=1))
    ntx = sum(len(s["transactions"]) for s in stmts)
    print(f"Parsed {len(stmts)} statements, {ntx} transactions")
    print(f"  value range: ${stmts[0]['month_end_value']:.2f} -> ${stmts[-1]['month_end_value']:.2f}")

    # --- append current live value (same money, moved brokers) ---
    dates = [s["date"] for s in stmts]
    values = [s["month_end_value"] for s in stmts]
    netc = [s["contributions"] - s["withdrawals"] for s in stmts]
    if CUR_PORTFOLIO.exists():
        cur = json.loads(CUR_PORTFOLIO.read_text())
        dates.append(cur["as_of"]); values.append(cur["total_value_cad"]); netc.append(0.0)

    base = values[0]
    cum = 0.0; twr = 100.0; hist = []
    spx = spx_monthly(dates)
    spx_base = next((x for x in spx if x), None)
    for t, (d, v, c) in enumerate(zip(dates, values, netc)):
        cum += c
        if t == 0:
            ret = 0.0
        else:
            denom = values[t - 1] + 0.5 * c
            ret = (v - values[t - 1] - c) / denom if denom else 0.0
            twr *= (1 + ret)
        hist.append({"date": d,
                     "value_index": round(v / base * 100, 2),
                     "invested_index": round(cum / base * 100, 2),
                     "twr_index": round(twr, 2),
                     "spx_index": round(spx[t] / spx_base * 100, 2) if spx[t] and spx_base else None,
                     "ret": round(ret, 4)})
    HIST_OUT.write_text(json.dumps(hist, indent=1))
    print(f"  portfolio_history.json: {len(hist)} points, TWR-to-date {twr - 100:+.1f}%")

    # --- sanitized ledger: relative sizes, no dollars, no share counts ---
    by_period = {s["period"]: s["month_end_value"] for s in stmts}
    pub = []
    for s in stmts:
        mev = by_period[s["period"]]
        for t in s["transactions"]:
            pub.append({"date": t["date"], "activity": t["activity"],
                        "description": t["description"], "currency": t["currency"],
                        "price": t["price"],
                        "size_pct": round(abs(t["amount"]) / mev, 4) if t["amount"] and mev else None})
    pub.sort(key=lambda x: x["date"], reverse=True)
    TX_OUT.write_text(json.dumps(pub, indent=1))
    print(f"  transactions.json: {len(pub)} rows (relative sizes, no $)")


if __name__ == "__main__":
    main()
