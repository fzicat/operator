# Operator MCP Server (read-only)

An [MCP](https://modelcontextprotocol.io) server that lets an AI agent read
Operator portfolio data. It is **strictly read-only** — there are no tools to
add, edit, or delete anything, and every underlying call is a `SELECT` against
the shared Supabase database.

## Data exposed

| Tool | Description |
|------|-------------|
| `get_portfolio_holdings` | Current IBKR holdings aggregated by underlying symbol (qty, book price, cost basis, MTM, unrealized/realized PnL, weight, target, basket, score). Pass `include_legs=true` for per-contract detail. |
| `get_market_prices` | Latest mark-to-market quotes (mark/bid/ask/last/close + status). Optional `symbol` and `instrument_type` filters. |
| `get_equity_entries` | Equity module entries (net-worth tracking) with CAD-converted `balance_cad` / `balance_net`. Filter by `date`, `latest_only`, `account`, `category`. |
| `get_equity_summary` | Net-worth summary for a snapshot date (defaults to latest): totals + breakdown by category and account. |
| `list_equity_dates` | All distinct equity snapshot dates, newest first. |

Holdings reuse the **exact same** FIFO + quote pipeline as the CLI and web apps
(`cli/services/quote_service.py`, `cli/services/valuation_service.py`), so the
numbers match the apps rather than being re-derived.

## Install

```bash
pip install -r cli/requirements.txt      # data layer (supabase, pandas, ...)
pip install -r mcp_server/requirements.txt  # the mcp SDK
```

## Configuration

The server reads the same `.env` (project root) as the CLI. It needs at least:

```
SUPABASE_URL=...
SUPABASE_KEY=...
```

## Run

The server speaks MCP over **stdio** (the standard transport for desktop AI
clients). It is normally launched by the AI client rather than by hand, but you
can start it directly to confirm it boots:

```bash
python -m mcp_server.server
```

## Register with an AI client

### Claude Code

```bash
claude mcp add operator -- /home/fzicat/projects/operator/.venv/bin/python -m mcp_server.server
```

(Run from the project root, or add `-e SUPABASE_URL=... -e SUPABASE_KEY=...` if
the `.env` is not discoverable.)

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "operator": {
      "command": "/home/fzicat/projects/operator/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/home/fzicat/projects/operator"
    }
  }
}
```

Using the venv's Python (not a bare `python`) ensures the `mcp`, `supabase`, and
`pandas` dependencies resolve. The `cwd` lets the server find the project root
and `.env`.
