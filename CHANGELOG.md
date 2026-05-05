# Changelog

All notable changes to this project will be documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - Unreleased

### Added
- Initial release. 9 MCP tools wrapping Prime Intellect's `prime` SDK:
  `list_gpu_types`, `list_availability`, `get_wallet_balance`, `pod_quote`,
  `pod_create`, `pod_list`, `pod_status`, `pod_terminate`, `pod_check_runaway`.
- Two-step `pod_quote` → `pod_create(confirm=True)` spend gate.
- Hard caps via `PRIME_MAX_HOURLY_USD` and `PRIME_MAX_TOTAL_USD` env vars.
- Wallet-balance check before provisioning.
- Local audit log + state tracker for runaway-pod detection.
- 32 unit/integration tests + opt-in live smoke test (`PRIME_LIVE_TEST=1`).
