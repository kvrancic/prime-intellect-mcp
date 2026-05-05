"""End-to-end MCP tool tests using FastMCP's in-process Client."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp import Client

from prime_intellect_mcp.server import mcp
from tests.conftest import _make_status


@pytest.fixture
async def mcp_client(fake_clients):
    async with Client(mcp) as c:
        yield c


def _payload(result) -> Any:
    """FastMCP returns CallToolResult; pull the parsed JSON payload."""
    if hasattr(result, "data") and result.data is not None:
        return result.data
    if hasattr(result, "structured_content") and result.structured_content is not None:
        return result.structured_content
    # Fall back to text content if nothing structured.
    text = result.content[0].text if result.content else "null"
    return json.loads(text)


async def test_tools_list_returns_nine_tools(mcp_client):
    tools = await mcp_client.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "list_gpu_types",
        "list_availability",
        "get_wallet_balance",
        "pod_quote",
        "pod_create",
        "pod_list",
        "pod_status",
        "pod_terminate",
        "pod_check_runaway",
    }


async def test_list_gpu_types(mcp_client):
    res = await mcp_client.call_tool("list_gpu_types", {})
    data = _payload(res)
    assert "H100_80GB" in data


async def test_get_wallet_balance(mcp_client):
    res = await mcp_client.call_tool("get_wallet_balance", {})
    data = _payload(res)
    assert data["balance_usd"] == 50.0


async def test_pod_quote_picks_cheapest(mcp_client, fake_clients, gpu_t4_cheap):
    # Two T4 rows, the second is more expensive — cheapest_match should pick the cheap one.
    from prime_cli.api.availability import (
        DiskConfig,
        GPUAvailability,
        Prices,
        ResourceConfig,
    )
    expensive = GPUAvailability(
        cloud_id="cl-expensive", gpu_type="T4", socket="PCIE", provider="other",
        data_center="us-east-2", country="US", gpu_count=1, gpu_memory=16,
        disk=DiskConfig(min_count=10, default_count=50, max_count=500, price=None, step=None, included=None),
        vcpu=ResourceConfig(min_count=1, default_count=4, max_count=32, price=None, step=None, included=None),
        memory=ResourceConfig(min_count=4, default_count=16, max_count=128, price=None, step=None, included=None),
        internet_speed=None, interconnect=None, interconnect_type=None,
        provisioning_time=None, stock_status="High", security="standard",
        prices=Prices(on_demand=5.00, community_price=None, is_variable=False, currency="USD"),
        images=["ubuntu_22_cuda_12"], is_spot=False, prepaid_time=None,
    )
    fake_clients.availability.get.return_value = {"T4": [gpu_t4_cheap, expensive]}

    res = await mcp_client.call_tool(
        "pod_quote",
        {"gpu_type": "T4", "gpu_count": 1, "disk_size_gb": 50, "vcpus": 4, "memory_gb": 16},
    )
    data = _payload(res)
    assert data["hourly_usd"] == 0.20  # community_price wins over on_demand
    assert data["provider"] == "lambda"
    assert data["estimated_runway_hours"] == pytest.approx(50.0 / 0.20)
    assert "quote_token" in data


async def test_pod_quote_no_match_errors(mcp_client, fake_clients):
    fake_clients.availability.get.return_value = {"H100_80GB": []}
    with pytest.raises(Exception, match="No available pod matches"):
        await mcp_client.call_tool(
            "pod_quote",
            {"gpu_type": "H100_80GB", "gpu_count": 8, "disk_size_gb": 100,
             "vcpus": 8, "memory_gb": 64},
        )


async def test_pod_create_dry_run_does_not_provision(mcp_client, fake_clients):
    quote = _payload(await mcp_client.call_tool(
        "pod_quote",
        {"gpu_type": "T4", "gpu_count": 1, "disk_size_gb": 50, "vcpus": 4, "memory_gb": 16},
    ))
    res = await mcp_client.call_tool(
        "pod_create",
        {"quote_token": quote["quote_token"], "name": "my-pod",
         "max_lifetime_hours": 1, "confirm": False},
    )
    data = _payload(res)
    assert data["will_provision"] is False
    fake_clients.pods.create.assert_not_called()


async def test_pod_create_with_confirm_provisions(mcp_client, fake_clients):
    quote = _payload(await mcp_client.call_tool(
        "pod_quote",
        {"gpu_type": "T4", "gpu_count": 1, "disk_size_gb": 50, "vcpus": 4, "memory_gb": 16},
    ))
    res = await mcp_client.call_tool(
        "pod_create",
        {"quote_token": quote["quote_token"], "name": "my-pod",
         "max_lifetime_hours": 1, "confirm": True},
    )
    data = _payload(res)
    assert data["id"] == "pod-abc"
    assert fake_clients.pods.create.call_count == 1
    sent = fake_clients.pods.create.call_args.args[0]
    assert sent["pod"]["name"] == "my-pod"
    assert sent["pod"]["gpuType"] == "T4"


async def test_pod_create_blocks_above_hourly_cap(mcp_client, fake_clients, low_caps):
    # Default fixture has H100 at $2.99/hr; cap is $1/hr.
    quote = _payload(await mcp_client.call_tool(
        "pod_quote",
        {"gpu_type": "H100_80GB", "gpu_count": 1, "disk_size_gb": 100,
         "vcpus": 8, "memory_gb": 64},
    ))
    with pytest.raises(Exception, match="exceeds PRIME_MAX_HOURLY_USD"):
        await mcp_client.call_tool(
            "pod_create",
            {"quote_token": quote["quote_token"], "name": "expensive",
             "max_lifetime_hours": 1, "confirm": True},
        )
    fake_clients.pods.create.assert_not_called()


async def test_pod_create_blocks_above_total_cap(mcp_client, fake_clients, monkeypatch):
    monkeypatch.setenv("PRIME_MAX_HOURLY_USD", "10")
    monkeypatch.setenv("PRIME_MAX_TOTAL_USD", "1")
    quote = _payload(await mcp_client.call_tool(
        "pod_quote",
        {"gpu_type": "T4", "gpu_count": 1, "disk_size_gb": 50, "vcpus": 4, "memory_gb": 16},
    ))
    with pytest.raises(Exception, match="exceeds PRIME_MAX_TOTAL_USD"):
        await mcp_client.call_tool(
            "pod_create",
            {"quote_token": quote["quote_token"], "name": "long-run",
             "max_lifetime_hours": 100, "confirm": True},
        )


async def test_pod_create_rejects_unknown_quote(mcp_client):
    with pytest.raises(Exception, match="unknown or expired"):
        await mcp_client.call_tool(
            "pod_create",
            {"quote_token": "fake", "name": "x",
             "max_lifetime_hours": 1, "confirm": True},
        )


async def test_pod_terminate_dry_run(mcp_client, fake_clients):
    res = await mcp_client.call_tool(
        "pod_terminate", {"pod_id": "pod-abc", "confirm": False},
    )
    data = _payload(res)
    assert data["terminated"] is False
    fake_clients.pods.delete.assert_not_called()


async def test_pod_terminate_confirmed(mcp_client, fake_clients):
    res = await mcp_client.call_tool(
        "pod_terminate", {"pod_id": "pod-abc", "confirm": True},
    )
    data = _payload(res)
    assert data["terminated"] is True
    fake_clients.pods.delete.assert_called_once_with("pod-abc")


async def test_pod_status_returns_ssh_string(mcp_client, fake_clients):
    res = await mcp_client.call_tool("pod_status", {"pod_id": "pod-abc"})
    data = _payload(res)
    assert data["ssh_connection"] == "root@1.2.3.4 -p 22"
    assert data["ssh_hint"] is not None


async def test_pod_status_normalises_list_ssh(mcp_client, fake_clients):
    fake_clients.pods.get_status.return_value = [
        _make_status(ssh_connection=["root@1.2.3.4 -p 22"]),
    ]
    res = await mcp_client.call_tool("pod_status", {"pod_id": "pod-abc"})
    data = _payload(res)
    assert data["ssh_connection"] == "root@1.2.3.4 -p 22"


async def test_pod_status_wait_polls_and_then_returns(mcp_client, fake_clients):
    fake_clients.pods.get_status.side_effect = [
        [_make_status(ssh_connection=None, status="PROVISIONING")],
        [_make_status(ssh_connection="root@1.2.3.4 -p 22", status="ACTIVE")],
    ]
    # Patch asyncio.sleep so we don't actually wait 5s.
    import prime_intellect_mcp.server as srv
    orig_sleep = srv.asyncio.sleep
    async def fast_sleep(_):
        return None
    srv.asyncio.sleep = fast_sleep  # type: ignore[assignment]
    try:
        res = await mcp_client.call_tool(
            "pod_status",
            {"pod_id": "pod-abc", "wait_for_ssh": True, "timeout_s": 30},
        )
    finally:
        srv.asyncio.sleep = orig_sleep  # type: ignore[assignment]
    data = _payload(res)
    assert data["ssh_connection"] == "root@1.2.3.4 -p 22"
    assert fake_clients.pods.get_status.call_count == 2


async def test_pod_check_runaway_flags_overdue(mcp_client, fake_clients, monkeypatch):
    import time as time_mod

    from prime_intellect_mcp import state
    state.record_provisioned(state.TrackedPod(
        pod_id="pod-old",
        name="train-overdue",
        hourly_usd=2.0,
        started_at_unix=time_mod.time() - 3 * 3600,
        max_lifetime_hours=1,
    ))
    res = await mcp_client.call_tool("pod_check_runaway", {})
    data = _payload(res)
    assert len(data) == 1
    assert data[0]["pod_id"] == "pod-old"
    assert "max_lifetime_hours" in data[0]["reason"]
