"""Pydantic models for the MCP-facing tool surface.

The Prime Intellect SDK gives us internal models (Pod, GPUAvailability, ...). We pass
those through directly when possible, but a few public-facing tool responses need
their own shape — most importantly the quote object the model gets back from
`pod_quote` and hands back into `pod_create`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PodQuote(BaseModel):
    """A non-binding price + provisioning preview returned by `pod_quote`.

    The `quote_token` is required by `pod_create` to provision. Tokens expire 60
    seconds after issue so the model cannot act on stale prices.
    """

    quote_token: str = Field(..., description="Pass this back to pod_create(confirm=True) to provision.")
    expires_at_unix: float = Field(..., description="Unix timestamp when this quote stops being valid.")

    gpu_type: str
    gpu_count: int
    gpu_memory_gb: int
    provider: str | None = None
    region: str | None = None  # data_center
    country: str | None = None
    is_spot: bool | None = None
    stock_status: str | None = None

    disk_size_gb: int
    vcpus: int
    memory_gb: int
    image: str

    hourly_usd: float = Field(..., description="Per-hour cost in USD at current pricing.")
    currency: str = "USD"
    is_variable_price: bool | None = None

    wallet_balance_usd: float | None = Field(
        default=None,
        description="Current wallet balance in USD; None if not retrievable.",
    )
    estimated_runway_hours: float | None = Field(
        default=None,
        description="wallet_balance_usd / hourly_usd, if both known.",
    )

    note: str = Field(
        default=(
            "This is a non-binding quote. To provision, call pod_create with this "
            "quote_token and confirm=True. Quote expires in 60 seconds."
        )
    )


class PodCreatePreview(BaseModel):
    """Returned by pod_create when confirm=False — the same data plus a clear gate message."""

    quote: PodQuote
    will_provision: bool = False
    estimated_total_usd: float = Field(
        ..., description="hourly_usd × max_lifetime_hours (the budget we'd commit)."
    )
    max_lifetime_hours: int
    message: str = (
        "Dry run only. Re-call pod_create with confirm=True to actually provision."
    )


class RunawayPod(BaseModel):
    """A pod we tracked locally that has either run past its declared max_lifetime
    or burned more than 80% of PRIME_MAX_TOTAL_USD."""

    pod_id: str
    name: str | None = None
    hourly_usd: float
    started_at_unix: float
    elapsed_hours: float
    estimated_spend_usd: float
    max_lifetime_hours: int
    reason: str  # e.g. "exceeded max_lifetime_hours" or "approaching total cap"
    suggestion: str = (
        "Consider terminating with pod_terminate(pod_id, confirm=True) "
        "if you no longer need this pod."
    )


class TerminateResult(BaseModel):
    pod_id: str
    terminated: bool
    message: str
