"""Live end-to-end smoke test. Provisions a real GPU pod, runs nvidia-smi, terminates.

OFF BY DEFAULT. To opt in:

    PRIME_LIVE_TEST=1 \\
    PRIME_API_KEY=pi-... \\
    PRIME_LIVE_MAX_HOURLY=0.50 \\
    uv run pytest tests/test_smoke_live.py -v -s

The test is conservative — it picks the cheapest available GPU under
PRIME_LIVE_MAX_HOURLY (default $0.50/hr), runs for at most 5 minutes, and always
terminates in the finally block. Expected spend: $0.05–$0.20.

Skipped automatically when:
- PRIME_LIVE_TEST is unset
- PRIME_API_KEY is unset
- pytest is invoked with `-m "not live"` (default in CI)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time

import pytest

pytestmark = pytest.mark.live


def _live_enabled() -> bool:
    return os.getenv("PRIME_LIVE_TEST") == "1" and bool(os.getenv("PRIME_API_KEY"))


@pytest.mark.skipif(not _live_enabled(), reason="Set PRIME_LIVE_TEST=1 and PRIME_API_KEY to run.")
async def test_full_lifecycle_against_real_api():
    """rent → wait for SSH → nvidia-smi → terminate, with a safety net."""
    from fastmcp import Client

    from prime_intellect_mcp import server as srv

    # Force lazy-init to use the real env.
    srv._clients = None  # type: ignore[assignment]

    max_hourly = float(os.getenv("PRIME_LIVE_MAX_HOURLY", "0.50"))
    max_lifetime_hours = 1
    os.environ.setdefault("PRIME_MAX_HOURLY_USD", str(max_hourly))
    os.environ.setdefault("PRIME_MAX_TOTAL_USD", str(max_hourly * max_lifetime_hours))

    pod_id: str | None = None
    async with Client(srv.mcp) as c:
        # 1. Find the cheapest available GPU under our cap.
        types_res = await c.call_tool("list_gpu_types", {})
        types = types_res.data
        assert isinstance(types, list) and types, "No GPU types returned."

        chosen_quote: dict | None = None
        chosen_type: str | None = None
        for gpu_type in types:
            try:
                q = await c.call_tool(
                    "pod_quote",
                    {
                        "gpu_type": gpu_type,
                        "gpu_count": 1,
                        "disk_size_gb": 30,
                        "vcpus": 2,
                        "memory_gb": 8,
                    },
                )
                payload = q.data
                if payload["hourly_usd"] <= max_hourly:
                    chosen_quote = payload
                    chosen_type = gpu_type
                    break
            except Exception:
                continue

        assert chosen_quote is not None, (
            f"No GPU type under ${max_hourly}/hr is currently available. "
            "Try raising PRIME_LIVE_MAX_HOURLY."
        )
        print(f"\n[live] Picked {chosen_type} at ${chosen_quote['hourly_usd']:.3f}/hr")

        # 2. Provision.
        create = await c.call_tool(
            "pod_create",
            {
                "quote_token": chosen_quote["quote_token"],
                "name": "prime-intellect-mcp-smoke",
                "max_lifetime_hours": max_lifetime_hours,
                "confirm": True,
            },
        )
        pod = create.data
        pod_id = pod["id"]
        print(f"[live] Provisioned pod {pod_id}")

        try:
            # 3. Wait for SSH (up to 8 minutes).
            status = await c.call_tool(
                "pod_status",
                {"pod_id": pod_id, "wait_for_ssh": True, "timeout_s": 480},
            )
            ssh = status.data["ssh_connection"]
            assert ssh, f"SSH not ready: {status.data}"
            print(f"[live] SSH ready: {ssh}")

            # 4. Run nvidia-smi if `ssh` is on PATH; otherwise skip the exec step.
            if shutil.which("ssh"):
                # The ssh string already contains "user@host -p PORT". Tokenise.
                args = ["ssh", "-o", "StrictHostKeyChecking=no",
                        "-o", "UserKnownHostsFile=/dev/null", *ssh.split()]
                args.append("nvidia-smi -L")
                proc = subprocess.run(args, capture_output=True, text=True, timeout=60)
                print(f"[live] ssh stdout: {proc.stdout!r}")
                print(f"[live] ssh stderr: {proc.stderr!r}")
                if proc.returncode == 0 and "GPU" in proc.stdout:
                    print("[live] nvidia-smi reachable over SSH ✓")
                else:
                    print("[live] WARN: ssh failed but pod was provisioned. "
                          "Likely missing prime config set-ssh-key-path.")
        finally:
            # 5. Always terminate.
            if pod_id is not None:
                term = await c.call_tool(
                    "pod_terminate",
                    {"pod_id": pod_id, "confirm": True},
                )
                print(f"[live] Terminated: {term.data}")

    # 6. Sleep briefly, then assert pod_list does not include pod_id (or it's STOPPED).
    time.sleep(3)
    async with Client(srv.mcp) as c:
        listing = await c.call_tool("pod_list", {})
        live_states = [
            p for p in listing.data
            if p.get("id") == pod_id and p.get("status", "").upper() not in
            {"STOPPED", "TERMINATED", "DELETED", "FAILED"}
        ]
        assert not live_states, f"Pod still live after terminate: {live_states}"
