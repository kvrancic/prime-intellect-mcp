"""Spend-cap enforcement."""

from __future__ import annotations

import pytest

from prime_intellect_mcp import safety
from prime_intellect_mcp.safety import SpendCapExceeded, check_caps


def test_default_caps_apply(monkeypatch):
    monkeypatch.delenv("PRIME_MAX_HOURLY_USD", raising=False)
    monkeypatch.delenv("PRIME_MAX_TOTAL_USD", raising=False)
    assert safety.max_hourly_usd() == safety.DEFAULT_MAX_HOURLY_USD
    assert safety.max_total_usd() == safety.DEFAULT_MAX_TOTAL_USD


def test_within_caps_passes(monkeypatch):
    monkeypatch.setenv("PRIME_MAX_HOURLY_USD", "5")
    monkeypatch.setenv("PRIME_MAX_TOTAL_USD", "40")
    check_caps(2.99, 8, wallet_balance_usd=100.0)  # no raise


def test_hourly_cap_blocks(monkeypatch):
    monkeypatch.setenv("PRIME_MAX_HOURLY_USD", "1")
    with pytest.raises(SpendCapExceeded, match="exceeds PRIME_MAX_HOURLY_USD"):
        check_caps(2.99, 1, wallet_balance_usd=1000.0)


def test_total_cap_blocks(monkeypatch):
    monkeypatch.setenv("PRIME_MAX_HOURLY_USD", "10")
    monkeypatch.setenv("PRIME_MAX_TOTAL_USD", "5")
    with pytest.raises(SpendCapExceeded, match="exceeds PRIME_MAX_TOTAL_USD"):
        check_caps(1.00, 100, wallet_balance_usd=1000.0)


def test_wallet_cap_blocks():
    with pytest.raises(SpendCapExceeded, match="exceeds wallet balance"):
        check_caps(1.00, 10, wallet_balance_usd=5.0)


def test_unset_wallet_balance_does_not_block():
    check_caps(1.00, 10, wallet_balance_usd=None)  # no raise


def test_invalid_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("PRIME_MAX_HOURLY_USD", "not-a-number")
    assert safety.max_hourly_usd() == safety.DEFAULT_MAX_HOURLY_USD
