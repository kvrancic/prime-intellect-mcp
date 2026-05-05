# Marketing playbook

A 2–3 day campaign, not a `git push`. Don't skip the manual parts.

---

## T-minus 3 days: outreach

### DM Vincent Weisser ([@VincentWeisser](https://x.com/VincentWeisser)) on X

> Hi Vincent — I built `prime-intellect-mcp`, a Model Context Protocol server that lets Claude Code rent and manage Prime Intellect GPU pods autonomously, with built-in spend caps. Wraps your `prime` SDK. Two questions before I launch publicly: (1) is your team building an official MCP server I should not duplicate, and (2) if not, would you be open to RTing the launch? Repo (private until launch): [link]

Send the same DM to whoever runs Prime Intellect's DevRel.

**If they reply "we have one coming":** pivot. Either ship a sandboxes-specific MCP, an Environments Hub MCP, or a multi-provider GPU MCP that includes them.
**If they reply "go for it":** ask if they'd be willing to retweet the launch. Offer them an early link.
**If they don't reply:** wait 24 hours, ship anyway.

### DM the Anthropic DevRel team

Soft pitch — they care about MCP ecosystem. *"Built this MCP server for Prime Intellect, would love a heads up if you're going to feature any GPU-rental MCP in the directory soon."*

---

## T-minus 1 day: artifact prep

| Artifact | Where it lives |
|---|---|
| 30-second demo video (or GIF) | embedded in README hero, uploaded to YouTube unlisted |
| Tweet thread (5 tweets) | drafted in Notes, ready to paste |
| Show HN post | drafted, ready for Tuesday/Wednesday morning ET |
| r/LocalLLaMA + r/ClaudeAI cross-posts | drafted |
| LinkedIn post | drafted, leveraging MIT/Harvard/AISST network |
| `awesome-mcp-servers` PR | branch ready, PR drafted |

### Tweet thread template

> 🧵 1/5 — I built `prime-intellect-mcp`: an MCP server that lets Claude Code rent, drive, and terminate Prime Intellect GPU pods autonomously, with built-in spend caps. [video]

> 2/5 — Setup is 3 lines. `pip install prime-intellect-mcp`, `prime config set-api-key`, drop a snippet into `claude_desktop_config.json`. Claude Code can now spin up an H100 on its own.

> 3/5 — The trick is the spend gate. `pod_quote` returns a price, `pod_create` requires `confirm=True`, env-var hard caps refuse anything above your threshold. No more 3am "ignore the budget" prompt-injection horror stories.

> 4/5 — When the pod is ready, the server hands the SSH string back to Claude's `Bash` tool. The agent then `ssh`/`scp`s into its own GPU. Composable, no reinvented wheels.

> 5/5 — Open source, MIT, [github.com/kvrancic/prime-intellect-mcp]. h/t to @PrimeIntellect for the SDK that did 90% of the work, and @AnthropicAI for MCP. RTs appreciated 🙏

### Show HN template

**Title:** Show HN: Prime Intellect MCP – Claude Code can now rent its own GPUs

**Body:**

> I shipped a Model Context Protocol server that lets Claude Code (or any MCP client) rent and manage GPU pods on Prime Intellect autonomously, with hard spend caps in env vars and a two-step quote→confirm flow so an agent loop can't quietly spin up an 8×H200.
>
> Use case I built it for: telling Claude "rent the cheapest H100 you can find, run my training script overnight, terminate it" and not waking up to a $400 bill.
>
> The server wraps Prime Intellect's official `prime` Python SDK. After provisioning, it hands the SSH connection string back to the agent's `Bash` tool, which then drives the pod directly. About 600 lines of Python, 9 tools, 32 unit tests, MIT.
>
> Repo: github.com/kvrancic/prime-intellect-mcp
> Demo (30s): [youtube link]
> Backstory: I'm teaching agentic environments at MIT and got tired of doing the rent/terminate dance manually.

### r/LocalLLaMA + r/ClaudeAI

Same content as Show HN, slightly more conversational. Lead with the demo gif.

### LinkedIn

> Shipped my first open-source MCP server: it lets Claude Code rent GPUs on Prime Intellect autonomously, with strict spend caps. Built it because manually provisioning compute every time I wanted to fine-tune something was breaking my flow. [github link] [demo]
>
> If you're teaching agentic environments — like I do for 6.S192 at MIT — this is the kind of thing your students should be running into in week 1: the agent doesn't get useful until it can act on the world, and acting on the world means dollars.

---

## Launch day (Tue or Wed, 9am ET)

Strict order:

1. **Push tag `v0.1.0`.** GitHub Action publishes to PyPI.
2. **Verify install** in a fresh venv: `uvx prime-intellect-mcp --help`.
3. **Update README hero** with the YouTube link or final GIF. Push.
4. **Tweet thread** — paste it. Pin tweet 1.
5. **Show HN** — submit at exactly 9am ET. That's the historical sweet spot for English-speaking weekday traffic.
6. **Reddit** — r/LocalLLaMA first, then r/ClaudeAI ~30 min later (don't blast simultaneously, looks spammy).
7. **LinkedIn** — post.
8. **Awesome lists PRs** — open them with the launched repo URL:
   - [`modelcontextprotocol/servers`](https://github.com/modelcontextprotocol/servers) — community list section
   - [`punkpeye/awesome-mcp-servers`](https://github.com/punkpeye/awesome-mcp-servers)
   - [`mcpservers.org`](https://mcpservers.org) submission form
9. **Reply to every comment** for the next 2 hours. This is THE highest-leverage move. If 5 comments come in and you reply to all of them within 10 minutes, you keep the post on the front page.

---

## Days 2–7: nurture

- Daily check on issues + PRs. Aim for <24h response.
- If Prime Intellect amplifies → follow-up tweet thanking them with a *new* prompt example (don't just retweet).
- Day 5–7: write *"What I learned shipping my first MCP server"* on LinkedIn. Good for your agentic-environments lecturer brand. Reference: tooling choices, the spend-gate design, what surprised you.
- If issues come in around environments / sandboxes / multi-provider, that's your v0.2 signal.

---

## What to automate vs do by hand

| ✅ Automate | ❌ Do by hand |
|---|---|
| PyPI publishing on tag (`release.yml`) | Demo video |
| Version bump + changelog (`release-please`) | DM to PI |
| Badge updates | Launch tweet timing |
| Dependabot / Renovate | First 2 hours of replies |
| Test matrix | HN submission timing |

Bot-tone tanks the early-engagement window. The launch is a deliberate event.
