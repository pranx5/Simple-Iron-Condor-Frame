"""Configuration constants for the Iron Condor desktop app."""

from pathlib import Path

TRADING_DAYS = 252

UNDERLYINGS = {
    "SPX": {
        "ticker": "^GSPC",
        "wing": 5,
        "iv_default": 20.0,
    },
    "QQQ": {
        "ticker": "QQQ",
        "wing": 2,
        "iv_default": 22.0,
    },
    "AAPL": {
        "ticker": "AAPL",
        "wing": 1,
        "iv_default": 28.0,
    },
    "IWM": {
        "ticker": "IWM",
        "wing": 1,
        "iv_default": 24.0,
    },
}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRADES_PATH = DATA_DIR / "trades.json"
