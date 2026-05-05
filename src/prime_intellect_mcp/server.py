"""FastMCP server exposing Prime Intellect GPU pods to MCP clients (Claude Code, etc.).

Tool surface (9):

    list_gpu_types          — discover what GPU types Prime Intellect has
    list_availability       — find pods that match (gpu_type, gpu_count, region)
    get_wallet_balance      — current Prime Intellect wallet balance

    pod_quote               — non-binding price + provisioning preview (issues a token)
    pod_create              — provisions a pod; requires confirm=True + a fresh quote_token
    pod_list                — list every pod the API key can see
    pod_status              — pod state; with wait_for_ssh=True, blocks until SSH info is available
    pod_terminate           — destroy a pod (requires confirm=True)
    pod_check_runaway       — locally-tracked pods past their declared lifetime / approaching cap

Spend authorization is enforced in three layers — see safety.py for details.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from . import __version__
from .client import (
    Clients,
    ConfigError,
    build_pod_config,
    cheapest_match,
    make_clients,
    normalise_ssh,
    price_per_hour,
    translate_api_error,
)
from .models import PodCreatePreview, PodQuote, RunawayPod, TerminateResult
from .quotes import QuoteExpired, QuoteUnknown, consume_quote, inspect_quote, issue_quote
from .safety import SpendCapExceeded, check_caps, max_total_usd
from .state import TrackedPod, append_audit, list_tracked, record_provisioned, record_terminated

INSTRUCTIONS = """\
You are connected to a Prime Intellect MCP server.

This server lets you rent GPU pods on demand. Important rules:

1. ALWAYS call pod_quote before pod_create. The quote shows the price; you must
   read the price before committing. Quotes expire 60 seconds after issue.

2. pod_create requires confirm=True AND a fresh quote_token. Without confirm=True
   it returns a dry-run preview only — no pod is provisioned.

3. The server enforces hourly and total spend caps from environment variables.
   If you hit a cap, do NOT retry with the same parameters; pick a cheaper GPU
   or lower max_lifetime_hours.

4. After pod_status returns an `ssh_connection` string, drive the pod from your
   own Bash tool: `ssh -o StrictHostKeyChecking=no <connection> "<command>"`.
   The user must have run `prime config set-ssh-key-path` once locally so the
   pod has their public key.

5. ALWAYS terminate pods you created (pod_terminate) when work is done. Idle
   pods accumulate hourly charges. If you ever lose track, call pod_check_runaway
   at session start.
"""

mcp: FastMCP = FastMCP(
    name="prime-intellect-mcp",
    version=__version__,
    instructions=INSTRUCTIONS,
)


# --- lazy client construction --------------------------------------------------

_clients: Clients | None = None
_clients_lock = asyncio.Lock()


async def get_clients() -> Clients:
    """Build and cache the Prime Intellect SDK clients on first use.

    We delay construction until a tool actually runs so `--help` and `tools/list`
    work without PRIME_API_KEY (the user can wire up env in Claude config first
    and the server only fails when they actually invoke a tool)."""

    global _clients
    if _clients is not None:
        return _clients
    async with _clients_lock:
        # Re-check inside the lock in case another awaitable raced us. mypy
        # narrows _clients to None after the outer guard but we may have
        # awaited the lock — bypass the narrow with a local read.
        cached = _clients
        if cached is not None:
            return cached
        try:
            _clients = make_clients()
        except ConfigError as exc:
            raise ToolError(str(exc)) from exc
    return _clients


def _err(exc: Exception) -> ToolError:
    """Wrap any SDK error in a ToolError with a friendly message."""
    return ToolError(translate_api_error(exc))


# --- discovery tools -----------------------------------------------------------


@mcp.tool
async def list_gpu_types() -> list[str]:
    """List every GPU type Prime Intellect currently offers (e.g. "H100_80GB", "A100_80GB").

    Use this when the user is vague about what they want. Pass the result into
    list_availability or pod_quote.
    """
    clients = await get_clients()
    try:
        return clients.availability.get_available_gpu_types()
    except Exception as e:
        raise _err(e) from e


@mcp.tool
async def list_availability(
    gpu_type: str | None = Field(
        default=None,
        description="GPU type slug, e.g. 'H100_80GB'. Strongly recommended — the unfiltered response is large.",
    ),
    gpu_count: int | None = Field(
        default=None,
        description="Required GPU count per pod (1, 2, 4, 8). None means any.",
    ),
    regions: list[str] | None = Field(
        default=None,
        description="Optional list of region slugs. None means any.",
    ),
) -> dict[str, list[dict[str, Any]]]:
    """List currently-available GPU pods that match the filters.

    Returns the SDK's GPUAvailability rows (cloud_id, gpu_type, gpu_count, prices,
    disk/vcpu/memory bounds, stock_status, ...). Use this to pick a target before
    pod_quote, or to show the user options.
    """
    clients = await get_clients()
    try:
        result = clients.availability.get(
            regions=regions, gpu_count=gpu_count, gpu_type=gpu_type
        )
    except Exception as e:
        raise _err(e) from e
    return {k: [r.model_dump() for r in v] for k, v in result.items()}


@mcp.tool
async def get_wallet_balance() -> dict[str, Any]:
    """Return the current Prime Intellect wallet balance and recent billings.

    Use this to estimate how long a quoted pod can run, or to check why
    pod_create returned an insufficient-funds error.
    """
    clients = await get_clients()
    try:
        wallet = clients.wallet.get(limit=5)
    except Exception as e:
        raise _err(e) from e
    return wallet.model_dump()


# --- pod lifecycle tools -------------------------------------------------------


@mcp.tool
async def pod_quote(
    gpu_type: str = Field(..., description="GPU type slug, e.g. 'H100_80GB'."),
    gpu_count: int = Field(default=1, description="Number of GPUs per pod (1, 2, 4, 8)."),
    disk_size_gb: int = Field(default=100, description="Disk size in GB."),
    vcpus: int = Field(default=8, description="vCPU count."),
    memory_gb: int = Field(default=64, description="Memory in GB."),
    image: str = Field(
        default="ubuntu_22_cuda_12",
        description="Container image slug. Use 'ubuntu_22_cuda_12' if unsure.",
    ),
) -> dict[str, Any]:
    """Get a non-binding price quote + reserved provisioning payload.

    Returns a quote_token (TTL=60s) that you pass to pod_create with confirm=True
    to actually provision. This tool has NO side effects.

    The server picks the *cheapest* matching GPUAvailability row that satisfies
    the requested disk/vcpu/memory. If none matches, returns an error explaining
    what's available.
    """
    clients = await get_clients()
    try:
        availability = clients.availability.get(gpu_type=gpu_type, gpu_count=gpu_count)
    except Exception as e:
        raise _err(e) from e

    gpu = cheapest_match(
        availability,
        gpu_type=gpu_type,
        gpu_count=gpu_count,
        disk_size_gb=disk_size_gb,
        vcpus=vcpus,
        memory_gb=memory_gb,
    )
    if gpu is None:
        raise ToolError(
            f"No available pod matches gpu_type={gpu_type}, gpu_count={gpu_count}, "
            f"disk={disk_size_gb}GB, vcpus={vcpus}, memory={memory_gb}GB. "
            "Try list_availability with different parameters."
        )

    hourly = price_per_hour(gpu.prices)
    if hourly is None:
        raise ToolError(
            f"Selected pod has no listed price (gpu_type={gpu.gpu_type}, "
            f"provider={gpu.provider}). Pick a different row."
        )

    wallet_balance: float | None = None
    with contextlib.suppress(Exception):
        # Wallet is informational; failing to read it should not block a quote.
        wallet_balance = float(clients.wallet.get(limit=1).balance_usd)

    pod_config = build_pod_config(
        name="<unset>",  # filled in at create time
        gpu=gpu,
        gpu_count=gpu_count,
        disk_size_gb=disk_size_gb,
        vcpus=vcpus,
        memory_gb=memory_gb,
        image=image,
        env_vars=None,
        team_id=None,
    )

    token, expires_at = issue_quote(
        {
            "pod_config": pod_config,
            "gpu_summary": gpu.model_dump(),
            "hourly_usd": hourly,
            "request": {
                "gpu_type": gpu_type,
                "gpu_count": gpu_count,
                "disk_size_gb": disk_size_gb,
                "vcpus": vcpus,
                "memory_gb": memory_gb,
                "image": image,
            },
        }
    )

    runway = wallet_balance / hourly if (wallet_balance and hourly > 0) else None

    quote = PodQuote(
        quote_token=token,
        expires_at_unix=expires_at,
        gpu_type=gpu.gpu_type,
        gpu_count=gpu.gpu_count,
        gpu_memory_gb=gpu.gpu_memory,
        provider=gpu.provider,
        region=gpu.data_center,
        country=gpu.country,
        is_spot=gpu.is_spot,
        stock_status=gpu.stock_status,
        disk_size_gb=disk_size_gb,
        vcpus=vcpus,
        memory_gb=memory_gb,
        image=image,
        hourly_usd=hourly,
        currency=gpu.prices.currency or "USD",
        is_variable_price=gpu.prices.is_variable,
        wallet_balance_usd=wallet_balance,
        estimated_runway_hours=runway,
    )
    return quote.model_dump()


@mcp.tool
async def pod_create(
    quote_token: str = Field(..., description="Token returned by pod_quote."),
    name: str = Field(..., description="Human-readable pod name."),
    max_lifetime_hours: int = Field(
        default=8,
        description="Soft budget cap: hourly_usd × this must fit under PRIME_MAX_TOTAL_USD.",
    ),
    confirm: bool = Field(
        default=False,
        description="Required True to actually provision. False returns a dry-run preview.",
    ),
    env_vars: dict[str, str] | None = Field(
        default=None,
        description="Optional env vars to inject into the pod.",
    ),
) -> dict[str, Any]:
    """Provision a Prime Intellect GPU pod (or preview the provisioning).

    With confirm=False: returns a dry-run preview describing what *would* happen.
    With confirm=True: validates spend caps + quote freshness, then provisions.

    The server enforces:
      - quote_token must be fresh (TTL 60s)
      - hourly_usd ≤ PRIME_MAX_HOURLY_USD
      - hourly_usd × max_lifetime_hours ≤ PRIME_MAX_TOTAL_USD
      - estimated total ≤ wallet balance

    On success, the pod is recorded in local state.json so pod_check_runaway can
    warn about overdue pods later.
    """
    if max_lifetime_hours < 1:
        raise ToolError("max_lifetime_hours must be ≥ 1.")

    cached = inspect_quote(quote_token)
    if cached is None:
        raise ToolError(
            "Quote token is unknown or expired. Call pod_quote again to get a fresh one."
        )
    hourly = float(cached["hourly_usd"])
    estimated_total = hourly * max_lifetime_hours

    if not confirm:
        gpu = cached["gpu_summary"]
        preview = PodCreatePreview(
            quote=PodQuote(
                quote_token=quote_token,
                expires_at_unix=time.time(),  # informational
                gpu_type=gpu["gpu_type"],
                gpu_count=gpu["gpu_count"],
                gpu_memory_gb=gpu["gpu_memory"],
                provider=gpu.get("provider"),
                region=gpu.get("data_center"),
                country=gpu.get("country"),
                is_spot=gpu.get("is_spot"),
                stock_status=gpu.get("stock_status"),
                disk_size_gb=cached["request"]["disk_size_gb"],
                vcpus=cached["request"]["vcpus"],
                memory_gb=cached["request"]["memory_gb"],
                image=cached["request"]["image"],
                hourly_usd=hourly,
                wallet_balance_usd=None,
            ),
            estimated_total_usd=estimated_total,
            max_lifetime_hours=max_lifetime_hours,
        )
        return preview.model_dump()

    # Hard caps + wallet check.
    wallet_balance: float | None = None
    with contextlib.suppress(Exception):
        clients_for_wallet = await get_clients()
        wallet_balance = float(clients_for_wallet.wallet.get(limit=1).balance_usd)

    try:
        check_caps(hourly, max_lifetime_hours, wallet_balance)
    except SpendCapExceeded as exc:
        append_audit(
            "create_blocked", reason=str(exc), hourly_usd=hourly,
            max_lifetime_hours=max_lifetime_hours,
        )
        raise ToolError(str(exc)) from exc

    # Consume the token (single-use after this point).
    try:
        payload = consume_quote(quote_token)
    except (QuoteExpired, QuoteUnknown) as exc:
        raise ToolError(str(exc)) from exc

    # Fill in the name + env_vars on the cached config.
    pod_config = payload["pod_config"]
    pod_config["pod"]["name"] = name
    if env_vars:
        pod_config["pod"]["envVars"] = env_vars

    clients = await get_clients()
    try:
        pod = clients.pods.create(pod_config)
    except Exception as e:
        append_audit("create_failed", error=str(e), hourly_usd=hourly)
        raise _err(e) from e

    record_provisioned(
        TrackedPod(
            pod_id=pod.id,
            name=pod.name,
            hourly_usd=hourly,
            started_at_unix=time.time(),
            max_lifetime_hours=max_lifetime_hours,
        )
    )
    append_audit(
        "create_succeeded",
        pod_id=pod.id,
        name=pod.name,
        hourly_usd=hourly,
        max_lifetime_hours=max_lifetime_hours,
    )
    return pod.model_dump()


@mcp.tool
async def pod_list() -> list[dict[str, Any]]:
    """List every pod the API key can see (active + provisioning + stopped)."""
    clients = await get_clients()
    try:
        result = clients.pods.list(offset=0, limit=100)
    except Exception as e:
        raise _err(e) from e
    return [p.model_dump() for p in result.data]


@mcp.tool
async def pod_status(
    pod_id: str = Field(..., description="The id returned by pod_create."),
    wait_for_ssh: bool = Field(
        default=False,
        description="If True, poll until ssh_connection is populated or timeout_s elapses.",
    ),
    timeout_s: int = Field(
        default=180, description="Max seconds to wait when wait_for_ssh=True."
    ),
) -> dict[str, Any]:
    """Get the current status (provisioning / active / failed) for a pod.

    With wait_for_ssh=True, blocks (polls every 5s) until ssh_connection is
    available — that's when you can SSH in. Returns the SSH connection string
    in `ssh_connection` (e.g. "root@1.2.3.4 -p 22000"). Use it from your Bash
    tool: `ssh -o StrictHostKeyChecking=no <ssh_connection> "<cmd>"`.
    """
    clients = await get_clients()
    deadline = time.time() + max(0, timeout_s)

    while True:
        try:
            statuses = clients.pods.get_status([pod_id])
        except Exception as e:
            raise _err(e) from e
        if not statuses:
            raise ToolError(f"Pod {pod_id!r} not found.")
        status = statuses[0]
        ssh = normalise_ssh(status.ssh_connection)

        if not wait_for_ssh or ssh:
            payload = status.model_dump()
            payload["ssh_connection"] = ssh
            payload["ssh_hint"] = (
                "Ensure you've run `prime config set-ssh-key-path ~/.ssh/id_ed25519` "
                "(or your key path) at least once on this machine so the pod accepts "
                "your key. Then your Bash tool can: ssh -o StrictHostKeyChecking=no "
                f"{ssh}"
            ) if ssh else None
            return payload

        if time.time() > deadline:
            raise ToolError(
                f"Timed out after {timeout_s}s waiting for SSH on pod {pod_id}. "
                f"Last status: {status.status!r}, installation_progress="
                f"{status.installation_progress!r}. Call pod_status again or pod_terminate."
            )
        await asyncio.sleep(5)


@mcp.tool
async def pod_terminate(
    pod_id: str = Field(..., description="The pod to destroy."),
    confirm: bool = Field(default=False, description="Required True to actually terminate."),
) -> dict[str, Any]:
    """Destroy (terminate) a pod. Idempotent on already-deleted pods.

    Without confirm=True, returns a no-op preview so you can re-read your decision."""
    if not confirm:
        return TerminateResult(
            pod_id=pod_id, terminated=False,
            message="Dry run only. Re-call with confirm=True to actually terminate.",
        ).model_dump()
    clients = await get_clients()
    try:
        clients.pods.delete(pod_id)
    except Exception as e:
        # Best-effort idempotence: report the error but still clean local state.
        msg = translate_api_error(e)
        record_terminated(pod_id)
        append_audit("terminate_error", pod_id=pod_id, error=msg)
        raise ToolError(msg) from e
    record_terminated(pod_id)
    append_audit("terminate_succeeded", pod_id=pod_id)
    return TerminateResult(
        pod_id=pod_id, terminated=True, message=f"Pod {pod_id} terminated."
    ).model_dump()


# --- safety / hygiene ----------------------------------------------------------


@mcp.tool
async def pod_check_runaway() -> list[dict[str, Any]]:
    """Return locally-tracked pods that have run past max_lifetime_hours OR whose
    accumulated cost is approaching PRIME_MAX_TOTAL_USD.

    Call this at the start of long-running sessions to catch forgotten pods.
    """
    runaways: list[RunawayPod] = []
    cap_total = max_total_usd()
    for tp in list_tracked():
        elapsed_hours = (time.time() - tp.started_at_unix) / 3600.0
        spend = elapsed_hours * tp.hourly_usd
        reasons = []
        if elapsed_hours > tp.max_lifetime_hours:
            reasons.append(
                f"running for {elapsed_hours:.2f}h, declared max_lifetime_hours="
                f"{tp.max_lifetime_hours}"
            )
        if spend > cap_total * 0.8:
            reasons.append(
                f"estimated spend ${spend:.2f} is >80% of PRIME_MAX_TOTAL_USD=${cap_total:.2f}"
            )
        if not reasons:
            continue
        runaways.append(
            RunawayPod(
                pod_id=tp.pod_id,
                name=tp.name,
                hourly_usd=tp.hourly_usd,
                started_at_unix=tp.started_at_unix,
                elapsed_hours=elapsed_hours,
                estimated_spend_usd=spend,
                max_lifetime_hours=tp.max_lifetime_hours,
                reason="; ".join(reasons),
            )
        )
    return [r.model_dump() for r in runaways]


# --- entry point ---------------------------------------------------------------


def main() -> None:
    """Console-script entry point. Runs the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
