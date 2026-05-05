"""Thin wrapper around prime_cli.api so the rest of the server can pretend the
SDK never changes shape.

We intentionally do *not* hide every detail — the SDK's Pydantic models are good
and we re-export them as JSON to the model. This module just centralises:

- API client construction (auth, error handling)
- the pod_config dict-shape used by PodsClient.create()
- friendly error translation (UnauthorizedError → "set PRIME_API_KEY", etc.)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from prime_cli.api import (
    APIClient,
    APIError,
    PaymentRequiredError,
    UnauthorizedError,
)
from prime_cli.api.availability import AvailabilityClient, GPUAvailability, Prices
from prime_cli.api.pods import Pod, PodsClient, PodStatus
from prime_cli.api.wallet import Wallet, WalletClient


class ConfigError(Exception):
    """Wraps SDK init failures with an actionable message."""


@dataclass
class Clients:
    api: APIClient
    availability: AvailabilityClient
    pods: PodsClient
    wallet: WalletClient


def make_clients() -> Clients:
    api_key = os.getenv("PRIME_API_KEY")
    if not api_key:
        raise ConfigError(
            "PRIME_API_KEY is not set. Get one at https://app.primeintellect.ai/dashboard/api-keys "
            "and either export it or add it to the MCP server's `env` block."
        )
    try:
        api = APIClient(api_key=api_key)
    except UnauthorizedError as exc:
        raise ConfigError(
            "PRIME_API_KEY was rejected by the Prime Intellect API. Generate a new "
            "key at https://app.primeintellect.ai/dashboard/api-keys."
        ) from exc
    return Clients(
        api=api,
        availability=AvailabilityClient(api),
        pods=PodsClient(api),
        wallet=WalletClient(api),
    )


def price_per_hour(prices: Prices) -> float | None:
    """Mirror of Prices.price (community wins over on-demand) but tolerant of None."""
    if prices.community_price is not None:
        return float(prices.community_price)
    if prices.on_demand is not None:
        return float(prices.on_demand)
    return None


def cheapest_match(
    availability: dict[str, list[GPUAvailability]],
    *,
    gpu_type: str,
    gpu_count: int,
    disk_size_gb: int,
    vcpus: int,
    memory_gb: int,
) -> GPUAvailability | None:
    """Pick the cheapest GPUAvailability row that fits the requested resources.

    The SDK returns availability rows whose `disk`, `vcpu`, `memory` carry min/max
    bounds — we filter to rows that can satisfy our request and sort by hourly price.
    """

    rows = availability.get(gpu_type, [])
    eligible: list[tuple[float, GPUAvailability]] = []
    for row in rows:
        if row.gpu_count != gpu_count:
            continue
        if not _fits_in_range(disk_size_gb, row.disk):
            continue
        if not _fits_in_range(vcpus, row.vcpu):
            continue
        if not _fits_in_range(memory_gb, row.memory):
            continue
        price = price_per_hour(row.prices)
        if price is None:
            continue
        eligible.append((price, row))
    if not eligible:
        return None
    eligible.sort(key=lambda x: x[0])
    return eligible[0][1]


def _fits_in_range(requested: int, config: Any) -> bool:
    """Generic min/max fit-check that tolerates missing bounds."""
    lo = getattr(config, "min_count", None)
    hi = getattr(config, "max_count", None)
    if lo is not None and requested < lo:
        return False
    return not (hi is not None and requested > hi)


def build_pod_config(
    *,
    name: str,
    gpu: GPUAvailability,
    gpu_count: int,
    disk_size_gb: int,
    vcpus: int,
    memory_gb: int,
    image: str,
    env_vars: dict[str, str] | None,
    team_id: str | None,
) -> dict[str, Any]:
    """Build the dict that `PodsClient.create()` accepts.

    Field names mirror the official `prime` CLI's pod-creation flow
    (packages/prime/src/prime_cli/commands/pods.py)."""

    pod: dict[str, Any] = {
        "name": name,
        "cloudId": gpu.cloud_id,
        "gpuType": gpu.gpu_type,
        "socket": gpu.socket,
        "gpuCount": gpu_count,
        "diskSize": disk_size_gb,
        "vcpus": vcpus,
        "memory": memory_gb,
        "image": image,
    }
    if gpu.data_center:
        pod["dataCenterId"] = gpu.data_center
    if env_vars:
        pod["envVars"] = env_vars

    payload: dict[str, Any] = {
        "pod": pod,
        "provider": {"type": gpu.provider},
    }
    if team_id:
        payload["team"] = {"teamId": team_id}
    return payload


def normalise_ssh(value: str | list[str] | None) -> str | None:
    """SSH connection field is sometimes wrapped in a single-item list."""
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return value


def translate_api_error(exc: Exception) -> str:
    """Turn an SDK exception into a model-readable message."""
    if isinstance(exc, UnauthorizedError):
        return (
            "Prime Intellect API rejected the API key. Set a valid PRIME_API_KEY "
            "(generate at https://app.primeintellect.ai/dashboard/api-keys)."
        )
    if isinstance(exc, PaymentRequiredError):
        return (
            "Prime Intellect wallet balance is insufficient. "
            "Top up at https://app.primeintellect.ai/wallet."
        )
    if isinstance(exc, APIError):
        return f"Prime Intellect API error: {exc}"
    return f"Unexpected error: {exc!r}"


__all__ = [
    "Clients",
    "ConfigError",
    "GPUAvailability",
    "Pod",
    "PodStatus",
    "Wallet",
    "build_pod_config",
    "cheapest_match",
    "make_clients",
    "normalise_ssh",
    "price_per_hour",
    "translate_api_error",
]
