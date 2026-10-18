#!/usr/bin/env python3
"""Fetch QQQ / SPY option chains with yfinance and write options.json for the page.

Usage:  python scripts/fetch_options.py [output_path]   (default: options.json)

Keeps every expiry out to 21 days, then Friday expiries out to 60 days, and only
strikes within roughly -25% / +25% of spot, so the file stays small.
Each row is [strike, bid, ask, last, yahoo_iv].
"""
import json
import sys
from datetime import date, datetime, timezone

import yfinance as yf

TICKERS = ["QQQ", "SPY"]
MAX_DTE = 60
ALL_EXPIRIES_UNTIL = 21
LOW, HIGH = 0.75, 1.25


def rows(df, spot):
    out = []
    for r in df.itertuples():
        k = float(r.strike)
        if not (spot * LOW <= k <= spot * HIGH):
            continue
        bid = float(r.bid or 0)
        ask = float(r.ask or 0)
        last = float(r.lastPrice or 0)
        iv = float(r.impliedVolatility or 0)
        if bid <= 0 and ask <= 0 and last <= 0:
            continue
        out.append([round(k, 2), round(bid, 2), round(ask, 2), round(last, 2), round(iv, 4)])
    return out


def fetch(symbol):
    t = yf.Ticker(symbol)
    hist = t.history(period="5d")
    spot = float(hist["Close"].iloc[-1])
    today = date.today()
    expiries = []
    for exp in t.options:
        d = datetime.strptime(exp, "%Y-%m-%d").date()
        dte = (d - today).days
        if dte < 0 or dte > MAX_DTE:
            continue
        if dte > ALL_EXPIRIES_UNTIL and d.weekday() != 4:
            continue
        chain = t.option_chain(exp)
        expiries.append({"exp": exp, "puts": rows(chain.puts, spot), "calls": rows(chain.calls, spot)})
    return {"spot": round(spot, 2), "expiries": expiries}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "options.json"
    data = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tickers": {}}
    for s in TICKERS:
        data["tickers"][s] = fetch(s)
        print(f"{s}: spot {data['tickers'][s]['spot']}, {len(data['tickers'][s]['expiries'])} expiries")
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print("wrote", path)


if __name__ == "__main__":
    main()

