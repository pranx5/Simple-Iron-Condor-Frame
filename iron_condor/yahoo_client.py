"""Yahoo quote fetching for desktop app (no browser CORS workarounds needed)."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, Optional


@dataclass
class Quote:
    price: float
    as_of_sec: Optional[int]
    source: str
    change_pct: Optional[float] = None


def _get_json(url: str, timeout: float = 10.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _yahoo_chart_url(ticker: str) -> str:
    q = urllib.parse.quote(ticker, safe="")
    return (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?"
        f"interval=1m&range=1d&includePrePost=true&_={int(time.time() * 1000)}"
    )


def _yahoo_quote_url(ticker: str) -> str:
    q = urllib.parse.quote(ticker, safe="")
    return f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={q}&_={int(time.time() * 1000)}"


def _last_finite_index(arr: list[Any] | None) -> int:
    if not arr:
        return -1
    for i in range(len(arr) - 1, -1, -1):
        v = arr[i]
        if isinstance(v, (int, float)):
            return i
    return -1


def _parse_chart_quote(data: dict[str, Any]) -> Quote:
    result = data.get("chart", {}).get("result") or []
    if not result:
        raise ValueError("No chart result")
    r0 = result[0]
    meta = r0.get("meta", {})
    timestamps = r0.get("timestamp") or []
    quote = ((r0.get("indicators") or {}).get("quote") or [{}])[0]

    price = None
    as_of_sec = None

    idx = _last_finite_index(quote.get("close"))
    if idx >= 0:
        price = quote["close"][idx]
    if price is None:
        idx = _last_finite_index(quote.get("open"))
        if idx >= 0:
            price = quote["open"][idx]

    if idx >= 0 and idx < len(timestamps):
        ts = timestamps[idx]
        if isinstance(ts, (int, float)):
            as_of_sec = int(ts)

    if as_of_sec is None:
        rmt = meta.get("regularMarketTime")
        if isinstance(rmt, (int, float)):
            as_of_sec = int(rmt)

    for key in ("regularMarketPrice", "postMarketPrice", "preMarketPrice"):
        if price is None:
            v = meta.get(key)
            if isinstance(v, (int, float)):
                price = float(v)

    if price is None:
        raise ValueError("No chart price")

    return Quote(price=float(price), as_of_sec=as_of_sec, source="chart", change_pct=None)


def _parse_v7_quote(data: dict[str, Any]) -> Quote:
    result = data.get("quoteResponse", {}).get("result") or []
    if not result:
        raise ValueError("No quote result")
    r0 = result[0]

    price = None
    for key in ("regularMarketPrice", "postMarketPrice", "preMarketPrice"):
        v = r0.get(key)
        if isinstance(v, (int, float)):
            price = float(v)
            break

    if price is None:
        raise ValueError("No quote price")

    as_of_sec = None
    for key in ("regularMarketTime", "postMarketTime", "preMarketTime"):
        v = r0.get(key)
        if isinstance(v, (int, float)):
            as_of_sec = int(v)
            break

    chg = r0.get("regularMarketChangePercent")
    change_pct = float(chg) if isinstance(chg, (int, float)) else None

    return Quote(price=price, as_of_sec=as_of_sec, source="quote", change_pct=change_pct)


def fetch_yahoo_quote(ticker: str) -> Quote:
    """Fetch quote with quote endpoint first, then chart fallback."""
    first_error: Exception | None = None
    try:
        return _parse_v7_quote(_get_json(_yahoo_quote_url(ticker)))
    except Exception as exc:
        first_error = exc

    try:
        return _parse_chart_quote(_get_json(_yahoo_chart_url(ticker)))
    except Exception:
        if first_error is not None:
            raise first_error
        raise


def fetch_yahoo_close_for_date(ticker: str, target_date: date) -> Optional[float]:
    """
    Fetch official daily close for a ticker on a specific calendar date.
    Returns None if no bar is available for that date.
    """
    start = datetime.combine(target_date - timedelta(days=2), dt_time.min).timestamp()
    end = datetime.combine(target_date + timedelta(days=3), dt_time.min).timestamp()
    q = urllib.parse.quote(ticker, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?"
        f"interval=1d&period1={int(start)}&period2={int(end)}"
    )
    data = _get_json(url)
    result = data.get("chart", {}).get("result") or []
    if not result:
        return None
    r0 = result[0]
    timestamps = r0.get("timestamp") or []
    quote = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []

    for ts, close in zip(timestamps, closes):
        if not isinstance(ts, (int, float)):
            continue
        if not isinstance(close, (int, float)):
            continue
        d = datetime.fromtimestamp(ts).date()
        if d == target_date:
            return float(close)
    return None
