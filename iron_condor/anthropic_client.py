"""Anthropic Messages API client for SPX news sentiment scans."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any


ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicScanError(RuntimeError):
    """Raised when the news scan request or response cannot be used."""


def _extract_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in response.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def _loads_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise AnthropicScanError("Claude did not return a JSON object.") from None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise AnthropicScanError(f"Could not parse scan JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise AnthropicScanError("Claude returned JSON, but not an object.")
    return parsed


def _clean_text(value: Any, limit: int | None = None) -> str:
    text = str(value or "")
    text = re.sub(r"</?cite\b[^>]*>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if limit is not None:
        return text[:limit]
    return text


def _normalize_scan(data: dict[str, Any]) -> dict[str, Any]:
    bias = str(data.get("bias", "neutral")).strip().lower()
    if bias not in {"bullish", "bearish", "neutral"}:
        bias = "neutral"

    confidence = str(data.get("confidence", "low")).strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"

    strike_shift = _clean_text(data.get("strike_shift", "hold current strikes"))
    allowed_shifts = {"shift calls up", "shift puts down", "hold current strikes"}
    if strike_shift.lower() not in allowed_shifts:
        strike_shift = "hold current strikes"

    summary = _clean_text(data.get("summary", ""))
    drivers_in = data.get("drivers")
    drivers: list[dict[str, str]] = []
    if isinstance(drivers_in, list):
        for item in drivers_in[:3]:
            if not isinstance(item, dict):
                continue
            drivers.append(
                {
                    "label": _clean_text(item.get("label", ""), 80),
                    "impact": _clean_text(item.get("impact", ""), 40),
                    "note": _clean_text(item.get("note", ""), 240),
                }
            )

    while len(drivers) < 3:
        drivers.append({"label": "-", "impact": "neutral", "note": "No driver returned."})

    return {
        "bias": bias,
        "confidence": confidence,
        "strike_shift": strike_shift,
        "summary": summary,
        "drivers": drivers,
    }


def scan_spx_news_sentiment(api_key: str, today: datetime | None = None, timeout: float = 45.0) -> dict[str, Any]:
    key = api_key.strip()
    if not key:
        raise AnthropicScanError("Enter an Anthropic API key first.")

    current = today or datetime.now()
    prompt = (
        f"Today is {current.strftime('%Y-%m-%d')}. "
        "Search for today's most important SPX/S&P 500 market news. "
        "Return ONLY a JSON object with fields: bias (bullish/bearish/neutral), "
        "confidence (low/medium/high), strike_shift (shift calls up / shift puts down / hold current strikes), "
        "summary (2-3 sentences), drivers (array of 3 objects each with label, impact, note)."
    )

    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 900,
        "temperature": 0,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AnthropicScanError(f"Anthropic request failed ({exc.code}): {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise AnthropicScanError(f"Could not reach Anthropic: {exc.reason}") from exc

    try:
        response = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AnthropicScanError(f"Anthropic returned invalid JSON: {exc}") from exc

    text = _extract_text(response)
    if not text:
        raise AnthropicScanError("Anthropic response did not include text JSON.")

    return _normalize_scan(_loads_json_object(text))
