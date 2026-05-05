# Claude Code MCP config snippets

## Per-user (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, or `%APPDATA%\Claude\claude_desktop_config.json` on Windows)

```json
{
  "mcpServers": {
    "prime-intellect": {
      "command": "uvx",
      "args": ["prime-intellect-mcp"],
      "env": {
        "PRIME_API_KEY": "pi-...",
        "PRIME_MAX_HOURLY_USD": "5",
        "PRIME_MAX_TOTAL_USD": "40"
      }
    }
  }
}
```

## Project-scoped (`.mcp.json` at the project root)

Same shape, but lives next to your repo. This is the recommended form when you want to commit the config so collaborators inherit it (just keep the API key out — read it from `${PRIME_API_KEY}` or a `.env`).

```json
{
  "mcpServers": {
    "prime-intellect": {
      "command": "uvx",
      "args": ["prime-intellect-mcp"],
      "env": {
        "PRIME_API_KEY": "${PRIME_API_KEY}",
        "PRIME_MAX_HOURLY_USD": "5",
        "PRIME_MAX_TOTAL_USD": "40"
      }
    }
  }
}
```

## Without `uvx` (system-installed)

If you've installed the package globally with `pip install prime-intellect-mcp` and your Python's `bin/` is on PATH:

```json
{
  "mcpServers": {
    "prime-intellect": {
      "command": "prime-intellect-mcp",
      "env": {
        "PRIME_API_KEY": "pi-..."
      }
    }
  }
}
```

## Verifying it loaded

After saving the config and restarting Claude Code, ask:

> What MCP tools do you have access to?

You should see `list_gpu_types`, `pod_quote`, `pod_create`, … (9 total). Then try:

> What's my Prime Intellect wallet balance?

That exercises the auth path. If it errors with "PRIME_API_KEY is not set", your env block didn't make it through — double-check the JSON for typos.
