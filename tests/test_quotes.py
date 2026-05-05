"""Quote-token cache invariants."""

from __future__ import annotations

import time

import pytest

from prime_intellect_mcp import quotes


def test_issue_returns_unique_tokens():
    a, _ = quotes.issue_quote({"x": 1})
    b, _ = quotes.issue_quote({"x": 2})
    assert a != b


def test_consume_returns_payload_then_invalidates():
    token, _ = quotes.issue_quote({"hourly_usd": 1.5})
    assert quotes.consume_quote(token)["hourly_usd"] == 1.5
    with pytest.raises(quotes.QuoteUnknown):
        quotes.consume_quote(token)


def test_consume_unknown_token_raises():
    with pytest.raises(quotes.QuoteUnknown):
        quotes.consume_quote("nope")


def test_expired_quote_raises(monkeypatch):
    token, _ = quotes.issue_quote({"hourly_usd": 1.0})
    # Fast-forward time past TTL.
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + quotes.QUOTE_TTL_SECONDS + 1)
    with pytest.raises((quotes.QuoteExpired, quotes.QuoteUnknown)):
        quotes.consume_quote(token)


def test_inspect_does_not_consume():
    token, _ = quotes.issue_quote({"hourly_usd": 1.0})
    assert quotes.inspect_quote(token) is not None
    assert quotes.inspect_quote(token) is not None  # still there
    quotes.consume_quote(token)  # now consume
    assert quotes.inspect_quote(token) is None
