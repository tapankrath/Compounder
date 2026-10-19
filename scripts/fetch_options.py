#!/usr/bin/env python3
"""Fetch QQQ / SPY option chains and write options.json for the page.

Source 1: Cboe's free delayed-quotes feed (15-min delayed, no key, works from GitHub).
Source 2: yfinance, used only if Cboe fails for a ticker.

Usage:  python scripts/fetch_options.py [output_path]   (default: options.json)
Keeps every expiry out to 21 days, then Friday expiries out to 60 days, and only
strikes within -25% / +25% of spot. Each row is [strike, bid, ask, last, iv].
"""
import json
import sys
import urllib.request
from datetime import date, datetime, timezone

TICKERS = ["QQQ", "SPY"]
MAX_DTE = 60
ALL_EXPIRIES_UNTIL = 21
LOW, HIGH = 0.75, 1.25


def keep_expiry(d, today):
    dte = (d - today).days
    if dte < 0 or dte > MAX_DTE:
        return False
    return dte <= ALL_EXPIRIES_UNTIL or d.weekday() == 4


def row(k, bid, ask, last, iv, spot):
    if not (spot * LOW <= k <= spot * HIGH):
        return None
    bid, ask, last, iv = (float(x or 0) for x in (bid, ask, last, iv))
    if bid <= 0 and ask <= 0 and last <= 0:
        return None
    return [round(k, 2), round(bid, 2), round(ask, 2), round(last, 2), round(iv, 4)]


def from_cboe(symbol):
    url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (options-bot)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)["data"]
    spot = float(data.get("current_price") or data.get("close") or 0)
    if spot <= 0:
        raise ValueError("no spot price")
    today = date.today()
    by_exp = {}
    for o in data["options"]:
        code = o["option"]                      # e.g. SPY261030P00550000
        tail = code[-15:]
        d = datetime.strptime(tail[:6], "%y%m%d").date()
        if not keep_expiry(d, today):
            continue
        r = row(int(tail[7:]) / 1000, o.get("bid"), o.get("ask"), o.get("last_trade_price"), o.get("iv"), spot)
        if r:
            e = by_exp.setdefault(d.isoformat(), {"exp": d.isoformat(), "puts": [], "calls": []})
            e["puts" if tail[6] == "P" else "calls"].append(r)
    expiries = sorted(by_exp.values(), key=lambda e: e["exp"])
    for e in expiries:
        e["puts"].sort(); e["calls"].sort()
    if not expiries:
        raise ValueError("no expiries")
    return {"spot": round(spot, 2), "expiries": expiries, "source": "Cboe"}


def from_yfinance(symbol):
    import yfinance as yf
    t = yf.Ticker(symbol)
    spot = float(t.history(period="5d")["Close"].iloc[-1])
    today = date.today()
    expiries = []
    for exp in t.options:
        d = datetime.strptime(exp, "%Y-%m-%d").date()
        if not keep_expiry(d, today):
            continue
        ch = t.option_chain(exp)
        conv = lambda df: [x for x in (row(float(r.strike), r.bid, r.ask, r.lastPrice, r.impliedVolatility, spot) for r in df.itertuples()) if x]
        expiries.append({"exp": exp, "puts": conv(ch.puts), "calls": conv(ch.calls)})
    return {"spot": round(spot, 2), "expiries": expiries, "source": "Yahoo"}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "options.json"
    data = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tickers": {}}
    for s in TICKERS:
        for fn in (from_cboe, from_yfinance):
            try:
                data["tickers"][s] = fn(s)
                t = data["tickers"][s]
                print(f"{s}: {t['source']} spot {t['spot']}, {len(t['expiries'])} expiries")
                break
            except Exception as e:
                print(f"{s}: {fn.__name__} failed: {e}")
    if not data["tickers"]:
        sys.exit("No data from any source")
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print("wrote", path)


if __name__ == "__main__":
    main()
