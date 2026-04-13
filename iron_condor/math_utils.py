"""Core iron condor math helpers."""

from __future__ import annotations

import math
from typing import Optional

from .config import TRADING_DAYS


def round_strike(price: float, wing: int) -> int:
    if wing >= 5:
        return int(round(price / 5.0) * 5)
    return int(round(price))


def one_sd_dollars(price: float, iv_pct: float) -> Optional[float]:
    if price <= 0 or iv_pct <= 0:
        return None
    return price * (iv_pct / 100.0) / math.sqrt(TRADING_DAYS)


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def pop_profit_zone(s0: float, sigma_dollars: float, lower_be: float, upper_be: float) -> Optional[float]:
    if sigma_dollars <= 0 or upper_be <= lower_be:
        return None
    z1 = (lower_be - s0) / sigma_dollars
    z2 = (upper_be - s0) / sigma_dollars
    return normal_cdf(z2) - normal_cdf(z1)


def pl_at_expiry_per_share(
    s: float,
    lp_k: float,
    sp_k: float,
    sc_k: float,
    lc_k: float,
    sp_r: float,
    lp_p: float,
    sc_r: float,
    lc_p: float,
) -> float:
    put_short = max(0.0, sp_k - s)
    put_long = max(0.0, lp_k - s)
    call_short = max(0.0, s - sc_k)
    call_long = max(0.0, s - lc_k)
    return (sp_r - lp_p - put_short + put_long) + (sc_r - lc_p - call_short + call_long)
