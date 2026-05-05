"""Local-state tracker invariants."""

from __future__ import annotations

import json
import time

from prime_intellect_mcp import state


def test_record_and_list_round_trip():
    tp = state.TrackedPod(
        pod_id="pod-1",
        name="train-7b",
        hourly_usd=2.99,
        started_at_unix=time.time(),
        max_lifetime_hours=8,
    )
    state.record_provisioned(tp)
    items = state.list_tracked()
    assert len(items) == 1
    assert items[0].pod_id == "pod-1"


def test_record_terminated_drops():
    tp = state.TrackedPod(
        pod_id="pod-2", name=None, hourly_usd=1.0,
        started_at_unix=time.time(), max_lifetime_hours=4,
    )
    state.record_provisioned(tp)
    assert any(p.pod_id == "pod-2" for p in state.list_tracked())
    state.record_terminated("pod-2")
    assert not any(p.pod_id == "pod-2" for p in state.list_tracked())


def test_terminate_unknown_pod_is_noop():
    state.record_terminated("never-existed")  # no raise


def test_audit_log_appends():
    state.append_audit("test_event", foo="bar", n=3)
    state.append_audit("another_event")
    text = state.audit_file().read_text().strip().splitlines()
    assert len(text) == 2
    first = json.loads(text[0])
    assert first["event"] == "test_event"
    assert first["foo"] == "bar"
    assert first["n"] == 3
    assert "ts" in first
