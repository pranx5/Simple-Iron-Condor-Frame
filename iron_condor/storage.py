"""Disk-backed trade storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

from .config import DATA_DIR, TRADES_PATH


class TradeStore:
    def __init__(self, path=TRADES_PATH):
        self.path = path

    def read_all(self) -> list[dict[str, Any]]:
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            return []
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            return []

    def write_all(self, trades: list[dict[str, Any]]) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(self.path.parent)) as tmp:
            json.dump(trades, tmp, indent=2)
            tmp_path = tmp.name
        from pathlib import Path

        Path(tmp_path).replace(self.path)

    def list_sorted(self) -> list[dict[str, Any]]:
        trades = self.read_all()
        return sorted(trades, key=lambda t: str(t.get("savedAt", "")), reverse=True)

    def add_trade(self, body: dict[str, Any]) -> dict[str, Any]:
        def to_num(v: Any):
            if v is None or v == "":
                return None
            try:
                n = float(v)
                return n
            except (TypeError, ValueError):
                return None

        trade = {
            "id": str(uuid4()),
            "savedAt": datetime.now(timezone.utc).isoformat(),
            "legsText": str(body.get("legsText", ""))[:2000],
            "legs": body.get("legs", []),
            "breakEvenLower": to_num(body.get("breakEvenLower")),
            "breakEvenUpper": to_num(body.get("breakEvenUpper")),
            "maxProfit": to_num(body.get("maxProfit")),
            "maxLoss": to_num(body.get("maxLoss")),
            "contractsQty": int(body.get("contractsQty", 0)),
            "contractsSymbol": str(body.get("contractsSymbol", "")).strip()[:32],
            "notes": str(body.get("notes", ""))[:4000],
        }
        trades = self.read_all()
        trades.append(trade)
        self.write_all(trades)
        return trade

    def delete_trade(self, trade_id: str) -> bool:
        trades = self.read_all()
        next_trades = [t for t in trades if t.get("id") != trade_id]
        if len(next_trades) == len(trades):
            return False
        self.write_all(next_trades)
        return True
