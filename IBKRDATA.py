import logging
import os
import sys
import threading
import time
from pathlib import Path

import pandas as pd
from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper

# (symbol, secType, exchange, currency, primaryExchange)
STOCKS_NASDAQ = ["AMZN", "AAPL", "NVDA", "GOOG", "META", "AMD", "MU", "COST", "MSFT", "AVGO"]
STOCKS_NYSE = ["BE", "JPM", "SHOP", "SPGI", "GE", "APH", "NEE"]

SYMBOLS = (
    [dict(symbol=s, secType="STK", exchange="SMART", currency="USD", primaryExchange="NASDAQ")
     for s in STOCKS_NASDAQ]
    + [dict(symbol=s, secType="STK", exchange="SMART", currency="USD", primaryExchange="NYSE")
       for s in STOCKS_NYSE]
    # MDA Space trades on the Toronto Stock Exchange in CAD
    + [dict(symbol="MDA", secType="STK", exchange="SMART", currency="CAD", primaryExchange="TSE")]
    + [dict(symbol="SPX", secType="IND", exchange="CBOE", currency="USD"),
       dict(symbol="COMP", secType="IND", exchange="NASDAQ", currency="USD"),
       dict(symbol="INDU", secType="IND", exchange="CME", currency="USD")]
)

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "Return Series"

HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 123
DURATION = "3 Y"
REQUEST_TIMEOUT = 60.0
CONNECT_TIMEOUT = 10.0
PACING_SLEEP = 2.0

# Status noise from TWS (market data farm connection messages etc.)
INFO_CODES = {2100, 2103, 2104, 2105, 2106, 2107, 2108, 2119, 2150, 2158}

log = logging.getLogger("ibkr-daily")


class FetchError(Exception):
    pass


class IBKRApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.data = {}            # reqId -> list of bar dicts
        self.done = {}            # reqId -> threading.Event
        self.req_errors = {}      # reqId -> "code: message"
        self.connected_evt = threading.Event()

    def nextValidId(self, orderId):
        self.connected_evt.set()

    def historicalData(self, reqId, bar):
        self.data.setdefault(reqId, []).append({
            "datetime": bar.date,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        })

    def historicalDataEnd(self, reqId, start, end):
        if reqId in self.done:
            self.done[reqId].set()

    # ibapi 9.81 passes 3 args; newer versions pass more — absorb them
    def error(self, reqId, errorCode, errorString, *extra):
        if errorCode in INFO_CODES:
            log.debug("TWS info %s: %s", errorCode, errorString)
            return
        if reqId in self.done:
            self.req_errors[reqId] = f"{errorCode}: {errorString}"
            self.done[reqId].set()
        else:
            log.warning("TWS error (reqId=%s) %s: %s", reqId, errorCode, errorString)


def make_contract(spec):
    contract = Contract()
    contract.symbol = spec["symbol"]
    contract.secType = spec["secType"]
    contract.exchange = spec["exchange"]
    contract.currency = spec["currency"]
    if spec.get("primaryExchange"):
        contract.primaryExchange = spec["primaryExchange"]
    return contract


def connect(host=HOST, port=PORT, client_id=CLIENT_ID, timeout=CONNECT_TIMEOUT):
    app = IBKRApp()
    app.connect(host, port, client_id)
    thread = threading.Thread(target=app.run, daemon=True)
    thread.start()
    if not app.connected_evt.wait(timeout):
        log.error("Could not connect to TWS on %s:%s — is TWS/IB Gateway running "
                  "with API connections enabled?", host, port)
        app.disconnect()
        sys.exit(1)
    return app


def fetch_daily_bars(app, req_id, contract, duration=DURATION, timeout=REQUEST_TIMEOUT):
    app.data[req_id] = []
    app.done[req_id] = threading.Event()
    app.reqHistoricalData(
        reqId=req_id,
        contract=contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=1,
        formatDate=1,
        keepUpToDate=False,
        chartOptions=[],
    )
    if not app.done[req_id].wait(timeout):
        app.cancelHistoricalData(req_id)
        raise FetchError(f"timed out after {timeout:.0f}s")
    if req_id in app.req_errors:
        raise FetchError(app.req_errors[req_id])
    if not app.data[req_id]:
        raise FetchError("no bars returned")
    return pd.DataFrame(app.data[req_id])


def to_return_frame(df):
    df = df.copy()
    df["return"] = df["close"].pct_change()
    df = df.dropna(subset=["return"])
    return df[["datetime", "open", "high", "low", "close", "volume", "return"]]


def write_csv_atomic(df, path):
    tmp = path.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("ibapi").setLevel(logging.WARNING)
    OUT_DIR.mkdir(exist_ok=True)
    app = connect()

    failures = {}
    for i, spec in enumerate(SYMBOLS):
        symbol = spec["symbol"]
        req_id = 1000 + i
        try:
            bars = fetch_daily_bars(app, req_id, make_contract(spec))
            out_path = OUT_DIR / f"{symbol.lower()}_daily_ibkr.csv"
            write_csv_atomic(to_return_frame(bars), out_path)
            log.info("%s: %d bars -> %s", symbol, len(bars), out_path.name)
        except FetchError as exc:
            failures[symbol] = str(exc)
            log.error("%s: FAILED (%s)", symbol, exc)
        time.sleep(PACING_SLEEP)

    app.disconnect()

    ok = len(SYMBOLS) - len(failures)
    log.info("SUMMARY: %d/%d succeeded", ok, len(SYMBOLS))
    if failures:
        log.error("FAILED: %s", ", ".join(f"{s} ({e})" for s, e in failures.items()))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
