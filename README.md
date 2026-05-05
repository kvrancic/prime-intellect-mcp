# prime-intellect-mcp

> Let Claude Code rent, drive, and terminate Prime Intellect GPU pods on its own — with hard spend caps you control. 

[![PyPI](https://img.shields.io/pypi/v/prime-intellect-mcp.svg)](https://pypi.org/project/prime-intellect-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/prime-intellect-mcp.svg)](https://pypi.org/project/prime-intellect-mcp/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://github.com/kvrancic/prime-intellect-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/kvrancic/prime-intellect-mcp/actions)
[![MCP](https://img.shields.io/badge/Model%20Context%20Protocol-compatible-blueviolet)](https://modelcontextprotocol.io)

---

## What this is

An [MCP](https://modelcontextprotocol.io) server that connects [Claude Code](https://docs.claude.com/en/docs/claude-code) (or any MCP client) to your [Prime Intellect](https://primeintellect.ai) account. With it, the agent can:

- 🔍 **Find** the cheapest GPU pod that matches your requirements
- 💸 **Quote** a price *before* committing money
- 🛒 **Provision** the pod (only after you say `confirm=True`)
- 🖥️ **SSH** into it (the connection string is handed to the agent's own `Bash` tool)
- 🛑 **Terminate** it when work is done — and warn loudly if you forget

Built for one workflow: telling Claude *"rent the cheapest H100, run my training script, then kill it"* and not waking up to a $400 bill.

---

## Install in 60 seconds

You only need this much to start renting GPUs through Claude Code:

### 1. Get a Prime Intellect API key

[**Click here to generate one**](https://app.primeintellect.ai/dashboard/api-keys) → set permissions:

| Scope | Level |
|---|---|
| **Instances** | Read and write |
| **Availability** | Read only |
| **Billing** | Read only |
| **SSH Keys** | Read only |

Copy the key — it starts with `pit_…`.

### 2. Add the server to Claude Code

Open `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or your project's `.mcp.json`, and paste:

```json
{
  "mcpServers": {
    "prime-intellect": {
      "command": "uvx",
      "args": ["prime-intellect-mcp"],
      "env": {
        "PRIME_API_KEY": "pit_PASTE_YOURS_HERE",
        "PRIME_MAX_HOURLY_USD": "5",
        "PRIME_MAX_TOTAL_USD": "40"
      }
    }
  }
}
```

That's it. Restart Claude Code and ask: *"What GPUs are available right now under $1/hr?"*

> Don't have `uvx`? Install it with `curl -LsSf https://astral.sh/uv/install.sh | sh` (or `brew install uv`). It's a one-liner installer for the `uv` package manager and you'll never have to manage a virtualenv again.

---

## ✨ Add SSH (optional, +2 min) — needed for Claude to actually run code on the pod

The server above can already provision/inspect/terminate pods. But to have Claude Code SSH into a running pod and execute commands on it, Prime Intellect needs to know your machine's public SSH key.

### 3. Find or generate an SSH key on your machine

```bash
ls ~/.ssh/*.pub          # if you have id_ed25519.pub or similar, you're set
# otherwise:
ssh-keygen -t ed25519 -C "you@example.com"   # press Enter through the prompts
```

### 4. Register the public key with Prime Intellect

```bash
cat ~/.ssh/id_ed25519.pub    # or whichever .pub file you have
```

Copy the output (one line starting with `ssh-ed25519 …`), then paste it into the **Add SSH key** form at [app.primeintellect.ai/dashboard/ssh-keys](https://app.primeintellect.ai/dashboard/ssh-keys).

That's it. Future pods will have your public key in `authorized_keys`, and Claude Code's `Bash` tool can SSH straight in:

```
ssh ubuntu@<pod-ip-from-pod_status> "nvidia-smi"
```

> **Coming in v0.2:** a `register_ssh_key` MCP tool that does step 4 from inside Claude (no browser visit). See [the issue tracker](https://github.com/kvrancic/prime-intellect-mcp/issues) to follow along.

---

## What Claude can now do (the 9 tools)

| Tool | Use case |
|---|---|
| `list_gpu_types` | "What GPU types does Prime Intellect offer?" |
| `list_availability` | "Show me 1×H100 pods available under $3/hr." |
| `get_wallet_balance` | "How much credit do I have left?" |
| `pod_quote` | "Quote me a 1×A100 with 200GB disk." (no charge) |
| `pod_create` | "Provision the pod from that quote." (requires `confirm=True`) |
| `pod_list` | "Show me my running pods." |
| `pod_status` | "Is pod X ready? Wait until it has SSH info." |
| `pod_terminate` | "Kill pod X." (requires `confirm=True`) |
| `pod_check_runaway` | "Did I forget to terminate anything?" |

---

## Safety: nothing provisions silently

Three layers, in order:

1. **Quote first.** `pod_quote` returns a price + a 60-second token. No side effects. The dollar amount is now in the agent's context.
2. **Explicit confirm.** `pod_create` (and `pod_terminate`) requires `confirm=True`. Without it, you get a dry-run preview.
3. **Hard env-var caps.** `PRIME_MAX_HOURLY_USD` blocks any pod above the rate. `PRIME_MAX_TOTAL_USD` blocks any (rate × max_lifetime_hours) above the budget. Wallet balance is also enforced. **None of these caps can be overridden by tool arguments** — they're read at every call.

Defaults: `PRIME_MAX_HOURLY_USD=5`, `PRIME_MAX_TOTAL_USD=40`. Set them in your config's `env` block.

Every `pod_create` / `pod_terminate` is appended as JSON to `~/.prime-intellect-mcp/audit.log`, so you have a complete history of what the agent did with your money.

---

## Example prompts (paste these into Claude Code)

```
List the cheapest 1×H100 pods available right now. Show me the top 3 by hourly price.
```

```
Quote a 1×A100 80GB with 100GB disk, 8 vCPU, 64GB RAM. Don't provision yet —
just show me what it would cost.
```

```
I need to fine-tune a 7B model overnight. Find the cheapest 1×H100 with 200GB
disk, max $40 total budget, max 12 hours. Provision it, give me the SSH command,
and remind me to terminate when I'm done.
```

```
Check if I have any running pods I forgot about and show me their hourly cost.
```

```
Terminate pod abc123. Confirm before doing it.
```

---

## Troubleshooting

<details>
<summary><b><code>PRIME_API_KEY is not set</code></b></summary>

Either your Claude Code config didn't pick up the `env` block, or you typed `PRIME_API_KEY` as a different variable. Verify with:
```
$ env | grep PRIME
```
inside the same shell that launches Claude Code, or paste the key directly into the JSON `env` block (instead of using `${PRIME_API_KEY}`).
</details>

<details>
<summary><b><code>Hourly rate $X/hr exceeds PRIME_MAX_HOURLY_USD cap</code></b></summary>

The agent picked a pod above your hard cap. Either:
- Pick a cheaper GPU (`list_availability` with a region filter often surfaces cheaper community-priced rows), or
- Raise `PRIME_MAX_HOURLY_USD` in your config and restart Claude Code.
</details>

<details>
<summary><b><code>Quote token expired</code></b></summary>

Quotes live 60 seconds; the agent waited too long between `pod_quote` and `pod_create`. Just call `pod_quote` again — it's a no-op cost-wise.
</details>

<details>
<summary><b>Pod is "ACTIVE" but <code>ssh_connection</code> is null</b></summary>

Provisioning isn't fully done. The pod is alive but still running its install script. Call `pod_status(pod_id, wait_for_ssh=True)` and it will block (polling every 5s) until SSH comes up.
</details>

<details>
<summary><b><code>ssh: Permission denied (publickey)</code></b></summary>

You haven't told Prime Intellect about your public key (or the pod was provisioned before you registered it). Fix:
1. Verify your pubkey is registered at [app.primeintellect.ai/dashboard/ssh-keys](https://app.primeintellect.ai/dashboard/ssh-keys).
2. **Re-provision** — the pod's `authorized_keys` is set at create time, so existing pods won't pick up keys you registered after.
3. If your private key has a passphrase, run `ssh-add --apple-use-keychain ~/.ssh/your_key` once on macOS so the agent unlocks it silently from now on.
</details>

<details>
<summary><b>Wallet balance is empty / <code>PaymentRequiredError</code></b></summary>

Top up at [app.primeintellect.ai/wallet](https://app.primeintellect.ai/wallet) and try again.
</details>

---

## Why another one?

There's a [`prime-mcp-server` 0.1.2](https://pypi.org/project/prime-mcp-server/) on PyPI. It's a thin proof-of-concept; this isn't a fork. Differences for unattended overnight use:

| | `prime-intellect-mcp` | `prime-mcp-server` 0.1.2 |
|---|---|---|
| Two-step quote → confirm | ✅ | ❌ |
| Env-var hard spend caps | ✅ | ❌ |
| Wallet pre-check | ✅ | ❌ |
| Runaway-pod detection | ✅ | ❌ |
| SSH handoff to agent | ✅ | ❌ |
| Tests | 32 unit + opt-in live | None |

---

## Local development

```bash
git clone https://github.com/kvrancic/prime-intellect-mcp
cd prime-intellect-mcp
uv sync
uv run pytest -m "not live"        # 32 fast tests, no network, no spend
uv run ruff check .
uv run mypy src
```

Live smoke test (provisions cheapest available GPU, runs `nvidia-smi`, terminates; ~$0.05 spend):

```bash
PRIME_API_KEY=pit_... PRIME_LIVE_TEST=1 PRIME_LIVE_MAX_HOURLY=0.60 \
PRIME_MAX_HOURLY_USD=0.60 PRIME_MAX_TOTAL_USD=2.00 \
uv run pytest tests/test_smoke_live.py -v -s
```

---

## Roadmap

- **v0.2** — `register_ssh_key` MCP tool (kill the dashboard step), Sandboxes (`prime-sandboxes` SDK), Environments Hub
- **v0.3** — Optional auto-terminate daemon (server-side enforcement of `max_lifetime_hours`); cost telemetry
- **v1.0+** — Hosted/OAuth deployment when Prime Intellect ships OAuth; submission to Anthropic connector directory

---

## Acknowledgements

- [Prime Intellect](https://primeintellect.ai) for the [`prime` Python SDK](https://github.com/PrimeIntellect-ai/prime) that does 90% of the work
- MIT 6.S192 for the credits that made testing this possible
- [Anthropic](https://anthropic.com) for [MCP](https://modelcontextprotocol.io)
- [FastMCP](https://gofastmcp.com) for the framework

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issues and PRs welcome. Please run `uv run pytest -m "not live"` and `uv run ruff check .` before submitting.
