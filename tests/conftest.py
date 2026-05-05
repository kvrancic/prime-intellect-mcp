"""Test fixtures: isolated state dir, fake SDK clients, in-process FastMCP."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from prime_cli.api.availability import (
    DiskConfig,
    GPUAvailability,
    Prices,
    ResourceConfig,
)
from prime_cli.api.pods import Pod, PodList, PodStatus
from prime_cli.api.wallet import Wallet

import prime_intellect_mcp.server as server_module


@pytest.fixture(autouse=True)
def isolated_state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIME_INTELLECT_MCP_STATE_DIR", str(tmp_path / "state"))
    yield tmp_path / "state"


@pytest.fixture(autouse=True)
def reset_clients_cache(monkeypatch):
    """Make sure each test starts with no cached SDK clients."""
    monkeypatch.setattr(server_module, "_clients", None)
    yield


@pytest.fixture
def low_caps(monkeypatch):
    monkeypatch.setenv("PRIME_MAX_HOURLY_USD", "1.0")
    monkeypatch.setenv("PRIME_MAX_TOTAL_USD", "5.0")


@pytest.fixture
def gpu_h100() -> GPUAvailability:
    return GPUAvailability(
        cloud_id="cl-test",
        gpu_type="H100_80GB",
        socket="SXM5",
        provider="datacrunch",
        data_center="us-east-1",
        country="US",
        gpu_count=1,
        gpu_memory=80,
        disk=DiskConfig(min_count=20, default_count=100, max_count=2000, price=None, step=None, included=None),
        vcpu=ResourceConfig(min_count=1, default_count=8, max_count=64, price=None, step=None, included=None),
        memory=ResourceConfig(min_count=8, default_count=64, max_count=512, price=None, step=None, included=None),
        internet_speed=None,
        interconnect=None,
        interconnect_type=None,
        provisioning_time=None,
        stock_status="High",
        security="standard",
        prices=Prices(on_demand=2.99, community_price=None, is_variable=False, currency="USD"),
        images=["ubuntu_22_cuda_12"],
        is_spot=False,
        prepaid_time=None,
    )


@pytest.fixture
def gpu_t4_cheap() -> GPUAvailability:
    return GPUAvailability(
        cloud_id="cl-cheap",
        gpu_type="T4",
        socket="PCIE",
        provider="lambda",
        data_center="us-west-1",
        country="US",
        gpu_count=1,
        gpu_memory=16,
        disk=DiskConfig(min_count=10, default_count=50, max_count=500, price=None, step=None, included=None),
        vcpu=ResourceConfig(min_count=1, default_count=4, max_count=32, price=None, step=None, included=None),
        memory=ResourceConfig(min_count=4, default_count=16, max_count=128, price=None, step=None, included=None),
        internet_speed=None,
        interconnect=None,
        interconnect_type=None,
        provisioning_time=None,
        stock_status="Medium",
        security="standard",
        prices=Prices(on_demand=0.30, community_price=0.20, is_variable=False, currency="USD"),
        images=["ubuntu_22_cuda_12"],
        is_spot=True,
        prepaid_time=None,
    )


def _make_pod(pod_id: str = "pod-abc", **overrides: Any) -> Pod:
    base: dict[str, Any] = {
        "id": pod_id,
        "name": "test-pod",
        "gpu_type": "H100_80GB",
        "gpu_count": 1,
        "status": "ACTIVE",
        "created_at": "2026-05-05T00:00:00Z",
        "provider_type": "datacrunch",
        "socket": "SXM5",
        "type": "GPU",
        "resources": {},
        "ssh_connection": None,
        "ip": None,
        "price_hr": 2.99,
    }
    base.update(overrides)
    return Pod(**base)


def _make_status(pod_id: str = "pod-abc", **overrides: Any) -> PodStatus:
    base: dict[str, Any] = {
        "pod_id": pod_id,
        "provider_type": "datacrunch",
        "status": "ACTIVE",
        "ssh_connection": "root@1.2.3.4 -p 22",
        "cost_per_hr": 2.99,
        "ip": "1.2.3.4",
        "installation_progress": 100,
    }
    base.update(overrides)
    return PodStatus(**base)


def _make_wallet(balance: float = 50.0) -> Wallet:
    return Wallet(
        wallet_id="wlt-test",
        team_id=None,
        balance_usd=balance,
        currency="USD",
        total_billings=0,
        recent_billings=[],
    )


@pytest.fixture
def fake_clients(monkeypatch, gpu_h100, gpu_t4_cheap):
    """Replace make_clients() with a MagicMock-based fake the server can use."""

    fake = MagicMock()
    # Default availability response: H100 + T4 both visible.
    fake.availability.get.return_value = {
        "H100_80GB": [gpu_h100],
        "T4": [gpu_t4_cheap],
    }
    fake.availability.get_available_gpu_types.return_value = ["H100_80GB", "T4"]

    fake.wallet.get.return_value = _make_wallet(50.0)

    fake.pods.create.return_value = _make_pod()
    fake.pods.list.return_value = PodList(total_count=0, offset=0, limit=100, data=[])
    fake.pods.get_status.return_value = [_make_status()]
    fake.pods.get.return_value = _make_pod()
    fake.pods.delete.return_value = None

    monkeypatch.setattr(server_module, "_clients", fake)
    return fake


__all__ = ["_make_pod", "_make_status", "_make_wallet"]
