"""Operator MCP server (READ-ONLY).

Exposes a small set of read-only tools so an AI agent can inspect Operator data:
  - current IBKR portfolio holdings
  - latest mark-to-market prices
  - IBKR trade history, summaries, option exposure, and assignment history
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
def list_ibkr_trades(
    symbol: str | None = None,
    underlying: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    instrument_type: str | None = None,
    put_call: str | None = None,
    open_close: str | None = None,
    limit: int | None = 200,
    offset: int | None = 0,
    sort_order: str = "newest",
) -> dict:
    """Raw IBKR trade history with safe filters and pagination.

    Returns every matching trade row from Operator's IBKR trades table, enriched
    with computed FIFO fields such as realized_pnl, remaining_qty, dte/dit,
    cashflow, and a strategy bucket. The query is read-only.

    Args:
        symbol: Optional ticker/underlying/contract filter (case-insensitive).
        underlying: Optional underlying ticker filter.
        from_date: Optional inclusive start date/datetime.
        to_date: Optional inclusive end date/datetime.
        instrument_type: Optional instrument filter: stock/equity, option,
            call, put, fx, or all.
        put_call: Optional option right filter: C/P/call/put.
        open_close: Optional IBKR open/close filter: O/open or C/close.
        limit: Max rows to return (bounded to 1-1000).
        offset: Rows to skip for pagination.
        sort_order: newest (default) or oldest.
    """
    return data.list_ibkr_trades(
        symbol=symbol,
        underlying=underlying,
        from_date=from_date,
        to_date=to_date,
        instrument_type=instrument_type,
        put_call=put_call,
        open_close=open_close,
        limit=limit,
        offset=offset,
        sort_order=sort_order,
    )


@mcp.tool()
def get_ibkr_trade_summary(
    symbol: str | None = None,
    underlying: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    instrument_type: str | None = None,
    put_call: str | None = None,
    open_close: str | None = None,
    group_limit: int | None = 50,
) -> dict:
    """Aggregate IBKR trade history by symbol, month, and strategy bucket.

    Summaries include trade counts, option/stock/FX row counts, option contract
    volume, stock share volume, gross/net cashflow, commissions, and FIFO
    realized PnL.
    """
    return data.get_ibkr_trade_summary(
        symbol=symbol,
        underlying=underlying,
        from_date=from_date,
        to_date=to_date,
        instrument_type=instrument_type,
        put_call=put_call,
        open_close=open_close,
        group_limit=group_limit,
    )


@mcp.tool()
def get_option_exposure(
    symbol: str | None = None,
    underlying: str | None = None,
    put_call: str | None = None,
    side: str = "short",
    expiry: str | None = None,
    include_quotes: bool = True,
) -> dict:
    """Current open option exposure by contract.

    Reports open contracts with side, expiry, strike, current remaining quantity,
    notional, delta/position_delta when available, premium credit remaining,
    mark-to-market value, quote status, and totals by expiry.

    Args:
        symbol: Optional ticker/underlying/contract filter.
        underlying: Optional underlying ticker filter.
        put_call: Optional option right filter: C/P/call/put.
        side: short (default), long, or all.
        expiry: Optional expiry filter, e.g. 20260821 or 2026-08-21.
        include_quotes: When true, joins latest MTM quotes and unrealized PnL.
    """
    return data.get_option_exposure(
        symbol=symbol,
        underlying=underlying,
        put_call=put_call,
        side=side,
        expiry=expiry,
        include_quotes=include_quotes,
    )


@mcp.tool()
def get_assignment_history(
    symbol: str | None = None,
    underlying: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    put_call: str | None = None,
    event_type: str | None = None,
    limit: int | None = 200,
) -> dict:
    """Infer option assignment/exercise events from IBKR trade rows.

    Operator's current Flex rows do not label assignment text directly, so this
    detects high-confidence events where a zero-price option close is paired at
    the same timestamp with a stock trade at the option strike.

    Args:
        symbol: Optional underlying ticker filter.
        underlying: Optional underlying ticker filter.
        from_date: Optional inclusive start date/datetime.
        to_date: Optional inclusive end date/datetime.
        put_call: Optional option right filter: C/P/call/put.
        event_type: Optional event filter, e.g. short_put_assignment or
            short_call_assignment.
        limit: Max events to return (bounded to 1-1000).
    """
    return data.get_assignment_history(
        symbol=symbol,
        underlying=underlying,
        from_date=from_date,
        to_date=to_date,
        put_call=put_call,
        event_type=event_type,
        limit=limit,
    )


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
