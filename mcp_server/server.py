"""Operator MCP server (READ-ONLY).

Exposes a small set of read-only tools so an AI agent can inspect Operator data:
  - current IBKR portfolio holdings
  - latest mark-to-market prices
  - Equity module data (net-worth tracking)

This server NEVER writes: there are no tools to add, edit, or delete data, and
every underlying data-access call is a SELECT only.

Run it (stdio transport, the default for Claude Desktop / Claude Code):
    python -m mcp_server.server
"""
from __future__ import annotations

import os
import sys

# Allow both ``python -m mcp_server.server`` and ``python mcp_server/server.py``.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcp_server import data  # noqa: E402

mcp = FastMCP("operator")


@mcp.tool()
def get_portfolio_holdings(include_legs: bool = False) -> dict:
    """Current IBKR portfolio holdings, aggregated by underlying symbol.

    Each position reports stock/call/put quantities, book (cost) price, cost
    basis, mark-to-market value (stock/call/put and combined), unrealized PnL,
    realized PnL, the portfolio weight (mtm_percent), and the configured target
    weight / basket / score. Only symbols with an open position or realized PnL
    are returned. A `totals` block summarizes the whole portfolio.

    Args:
        include_legs: When true, also include per-contract open legs (each open
            stock/option line with its strike, expiry, quantity and MTM).
    """
    return data.get_portfolio_holdings(include_legs=include_legs)


@mcp.tool()
def get_market_prices(
    symbol: str | None = None, instrument_type: str | None = None
) -> dict:
    """Latest mark-to-market prices for tracked contracts.

    Returns the most recent quote per contract (mark, bid, ask, last, close)
    along with its status, source and timestamps.

    Args:
        symbol: Optional ticker filter; matches the contract symbol or its
            underlying symbol (case-insensitive). Omit for all contracts.
        instrument_type: Optional filter, either "equity" or "option".
    """
    return data.get_market_prices(symbol=symbol, instrument_type=instrument_type)


@mcp.tool()
def get_equity_entries(
    date: str | None = None,
    latest_only: bool = False,
    account: str | None = None,
    category: str | None = None,
) -> dict:
    """Equity module entries (personal net-worth tracking).

    Each entry includes the raw balance plus CAD-converted values: balance_cad
    (balance x rate, with SAT treated as satoshis) and balance_net
    (balance_cad x (1 - tax)).

    Args:
        date: Optional snapshot date filter, format "YYYY-MM-DD".
        latest_only: When true (and no explicit date), return only the most
            recent snapshot date's entries.
        account: Optional account name filter (case-insensitive).
        category: Optional category filter, e.g. "IBKR", "Cash", "Bitcoin".
    """
    return data.get_equity_entries(
        date=date, latest_only=latest_only, account=account, category=category
    )


@mcp.tool()
def get_equity_summary(date: str | None = None) -> dict:
    """Net-worth summary for one equity snapshot date (defaults to latest).

    Returns total balance_cad / balance_net plus breakdowns by category and by
    account, sorted by net balance.

    Args:
        date: Optional snapshot date "YYYY-MM-DD". Defaults to the latest date.
    """
    return data.get_equity_summary(date=date)


@mcp.tool()
def list_equity_dates() -> dict:
    """List all distinct equity snapshot dates, most recent first."""
    return data.list_equity_dates()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
