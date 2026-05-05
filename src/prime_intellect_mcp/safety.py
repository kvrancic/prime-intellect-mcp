"""Spend-cap enforcement.

The product risk with autonomous GPU provisioning is that an agent loop spins up
expensive hardware nobody intended. We defend in three layers:

1. The model must call pod_quote first (or pod_create with confirm=False) so the
   price is in its context window before it spends.
2. pod_create requires confirm=True — a deliberate second tool call.
3. Hard caps from env vars (PRIME_MAX_HOURLY_USD, PRIME_MAX_TOTAL_USD) refuse the
   provision regardless of what the model says.
"""

from __future__ import annotations

import os

DEFAULT_MAX_HOURLY_USD = 5.0
DEFAULT_MAX_TOTAL_USD = 40.0


class SpendCapExceeded(Exception):
    """Raised when a provision would breach a configured hard cap."""


def max_hourly_usd() -> float:
    raw = os.getenv("PRIME_MAX_HOURLY_USD")
    if raw is None:
        return DEFAULT_MAX_HOURLY_USD
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_MAX_HOURLY_USD


def max_total_usd() -> float:
    raw = os.getenv("PRIME_MAX_TOTAL_USD")
    if raw is None:
        return DEFAULT_MAX_TOTAL_USD
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_MAX_TOTAL_USD


def check_caps(
    hourly_usd: float,
    max_lifetime_hours: int,
    wallet_balance_usd: float | None,
) -> None:
    """Raise SpendCapExceeded with a model-readable explanation if any cap is breached."""

    h_cap = max_hourly_usd()
    t_cap = max_total_usd()
    estimated_total = hourly_usd * max_lifetime_hours

    if hourly_usd > h_cap:
        raise SpendCapExceeded(
            f"Hourly rate ${hourly_usd:.2f}/hr exceeds PRIME_MAX_HOURLY_USD cap of "
            f"${h_cap:.2f}/hr. Either pick a cheaper GPU or raise the cap."
        )
    if estimated_total > t_cap:
        raise SpendCapExceeded(
            f"Estimated total ${estimated_total:.2f} (={hourly_usd:.2f} × "
            f"{max_lifetime_hours}h) exceeds PRIME_MAX_TOTAL_USD cap of "
            f"${t_cap:.2f}. Either lower max_lifetime_hours or raise the cap."
        )
    if wallet_balance_usd is not None and estimated_total > wallet_balance_usd:
        raise SpendCapExceeded(
            f"Estimated total ${estimated_total:.2f} exceeds wallet balance "
            f"${wallet_balance_usd:.2f}. Top up at primeintellect.ai/wallet "
            "or lower max_lifetime_hours."
        )
