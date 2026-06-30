"""Read-only data access for the Operator MCP server.

Every function here READS from Supabase only. No insert/update/delete/upsert call
is ever made. Portfolio holdings reuse the exact same FIFO/quote pipeline the CLI
and web apps use (``cli.services.quote_service`` + ``cli.services.valuation_service``)
so numbers match the apps rather than re-implementing the logic.
"""
from __future__ import annotations

import math
import os
import sys
from typing import Any

# Make the project root importable so ``cli.*`` and ``shared.*`` resolve the same
# way they do when running the CLI (see cli/main.py).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd  # noqa: E402

from cli.db import equity_db, ibkr_db, market_quote_db  # noqa: E402
from cli.services import quote_service, valuation_service  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _num(value: Any, digits: int | None = None) -> float | None:
    """Coerce to a JSON-safe float (NaN/inf -> None), optionally rounded."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits) if digits is not None else number


def _is_option(put_call: Any) -> bool:
    return str(put_call or "").strip().upper() in {"C", "P"}


# --------------------------------------------------------------------------- #
# IBKR portfolio holdings
# --------------------------------------------------------------------------- #
def _load_valued_trades() -> pd.DataFrame:
    """Trades with FIFO PnL, credit, contract keys and latest MTM applied."""
    trades = quote_service.prepare_trades(ibkr_db.fetch_all_trades_as_df())
    if trades.empty:
        return trades
    quotes_by_key = market_quote_db.fetch_latest_quotes()
    return valuation_service.apply_quotes(trades, quotes_by_key)


def get_portfolio_holdings(include_legs: bool = False) -> dict[str, Any]:
    """Aggregate current IBKR holdings by underlying symbol.

    Mirrors the position aggregation used by the apps: positions are grouped by
    underlying symbol and split into stock / call / put buckets. Only symbols
    with a non-zero open position or non-zero realized PnL are returned.
    """
    df = _load_valued_trades()
    if df.empty:
        return {"positions": [], "totals": {}, "as_of": None}

    target_percent = ibkr_db.fetch_symbol_targets()
    baskets = ibkr_db.fetch_symbol_baskets()
    scores = ibkr_db.fetch_symbol_scores()

    df = df.copy()
    df["_underlying"] = df["underlyingSymbol"].where(
        df["underlyingSymbol"].notna() & (df["underlyingSymbol"] != ""), df["symbol"]
    )
    df["_is_option"] = df["putCall"].apply(_is_option)

    positions: list[dict[str, Any]] = []
    for symbol, group in df.groupby("_underlying"):
        stock = group[~group["_is_option"]]
        calls = group[group["putCall"].str.upper() == "C"]
        puts = group[group["putCall"].str.upper() == "P"]

        stock_credit = stock["credit"].sum()
        stock_value = -stock_credit
        stock_mtm = stock["mtm_value"].sum()
        call_mtm = calls["mtm_value"].sum()
        put_mtm = puts["mtm_value"].sum()
        mtm = stock_mtm + call_mtm + put_mtm

        stock_qty = stock["remaining_qty"].sum()
        call_qty = calls["remaining_qty"].sum()
        put_qty = puts["remaining_qty"].sum()

        stock_pnl = stock["realized_pnl"].sum()
        call_pnl = calls["realized_pnl"].sum()
        put_pnl = puts["realized_pnl"].sum()
        realized_pnl = stock_pnl + call_pnl + put_pnl

        unrealized_pnl = group["unrealized_pnl"].sum()
        book_price = stock_credit / stock_qty if stock_qty else 0.0

        if all(
            abs(v) < 1e-9
            for v in (stock_value, mtm, stock_qty, call_qty, put_qty, realized_pnl)
        ):
            continue

        position = {
            "symbol": symbol,
            "stock_qty": _num(stock_qty),
            "call_qty": _num(call_qty),
            "put_qty": _num(put_qty),
            "book_price": _num(book_price, 4),
            "cost_basis": _num(stock_value, 2),
            "stock_mtm": _num(stock_mtm, 2),
            "call_mtm": _num(call_mtm, 2),
            "put_mtm": _num(put_mtm, 2),
            "mtm": _num(mtm, 2),
            "unrealized_pnl": _num(unrealized_pnl, 2),
            "realized_pnl": _num(realized_pnl, 2),
            "target_percent": _num(target_percent.get(symbol)),
            "basket": baskets.get(symbol),
            "score": scores.get(symbol),
        }
        if include_legs:
            position["legs"] = _open_legs(group)
        positions.append(position)

    total_mtm = sum(p["mtm"] or 0.0 for p in positions)
    for p in positions:
        p["mtm_percent"] = _num((p["mtm"] / total_mtm * 100) if total_mtm else 0.0, 2)

    positions.sort(key=lambda p: abs(p["mtm"] or 0.0), reverse=True)

    totals = {
        "total_mtm": _num(total_mtm, 2),
        "total_cost_basis": _num(sum(p["cost_basis"] or 0.0 for p in positions), 2),
        "total_unrealized_pnl": _num(
            sum(p["unrealized_pnl"] or 0.0 for p in positions), 2
        ),
        "total_realized_pnl": _num(
            sum(p["realized_pnl"] or 0.0 for p in positions), 2
        ),
        "position_count": len(positions),
    }
    return {"positions": positions, "totals": totals}


def _open_legs(group: pd.DataFrame) -> list[dict[str, Any]]:
    """Per-contract open legs (remaining_qty != 0) for a symbol group."""
    legs = []
    open_rows = group[group["remaining_qty"] != 0]
    for _, row in open_rows.iterrows():
        legs.append(
            {
                "symbol": row.get("symbol"),
                "contract_key": row.get("contract_key"),
                "put_call": row.get("putCall") or None,
                "strike": _num(row.get("strike")),
                "expiry": row.get("expiry") or None,
                "remaining_qty": _num(row.get("remaining_qty")),
                "mtm_price": _num(row.get("mtm_price"), 4),
                "mtm_value": _num(row.get("mtm_value"), 2),
                "unrealized_pnl": _num(row.get("unrealized_pnl"), 2),
                "quote_status": row.get("quote_status"),
            }
        )
    return legs


# --------------------------------------------------------------------------- #
# Latest mark-to-market prices
# --------------------------------------------------------------------------- #
def get_market_prices(
    symbol: str | None = None, instrument_type: str | None = None
) -> dict[str, Any]:
    """Latest mark-to-market quotes from the ``market_quotes`` table.

    ``symbol`` matches against both the contract symbol and the underlying
    symbol (case-insensitive). ``instrument_type`` filters by 'equity' / 'option'.
    """
    quotes = market_quote_db.fetch_latest_quotes()
    sym = symbol.strip().upper() if symbol else None
    itype = instrument_type.strip().lower() if instrument_type else None

    rows: list[dict[str, Any]] = []
    for q in quotes.values():
        q_symbol = str(q.get("symbol") or "").upper()
        q_under = str(q.get("underlying_symbol") or "").upper()
        if sym and sym not in (q_symbol, q_under):
            continue
        if itype and str(q.get("instrument_type") or "").lower() != itype:
            continue
        rows.append(
            {
                "contract_key": q.get("contract_key"),
                "symbol": q.get("symbol"),
                "underlying_symbol": q.get("underlying_symbol"),
                "instrument_type": q.get("instrument_type"),
                "mark": _num(q.get("mark"), 4),
                "bid": _num(q.get("bid"), 4),
                "ask": _num(q.get("ask"), 4),
                "last": _num(q.get("last"), 4),
                "close": _num(q.get("close"), 4),
                "status": q.get("status"),
                "source": q.get("source"),
                "quote_time": q.get("quote_time"),
                "updated_at": q.get("updated_at"),
            }
        )

    rows.sort(key=lambda r: (r["symbol"] or ""))
    return {"prices": rows, "count": len(rows)}


# --------------------------------------------------------------------------- #
# Equity module
# --------------------------------------------------------------------------- #
def _equity_frame() -> pd.DataFrame:
    """Equity entries with the same computed columns as the Equity module."""
    df = equity_db.fetch_equity_data()
    if df.empty:
        return df
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["rate"] = pd.to_numeric(df["rate"], errors="coerce")
    df["balance"] = pd.to_numeric(df["balance"], errors="coerce")
    df["tax"] = pd.to_numeric(df["tax"], errors="coerce").fillna(0.0)
    df["balance_cad"] = df["balance"] * df["rate"]
    sat = df["currency"] == "SAT"
    df.loc[sat, "balance_cad"] = df.loc[sat, "balance_cad"] / 100_000_000.0
    df["balance_net"] = df["balance_cad"] * (1 - df["tax"])
    return df


def get_equity_entries(
    date: str | None = None,
    latest_only: bool = False,
    account: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Equity entries (net-worth tracking). Optionally filter by date/account/category.

    ``latest_only`` returns entries for the most recent snapshot date only.
    """
    df = _equity_frame()
    if df.empty:
        return {"entries": [], "count": 0, "date": None}

    if date:
        df = df[df["date"] == date]
    elif latest_only:
        latest = df["date"].max()
        df = df[df["date"] == latest]
    if account:
        df = df[df["account"].str.lower() == account.strip().lower()]
    if category:
        df = df[df["category"].str.lower() == category.strip().lower()]

    df = df.sort_values(["date", "description"], ascending=[False, True])
    entries = [
        {
            "id": int(row["id"]) if pd.notna(row["id"]) else None,
            "date": row["date"],
            "description": row["description"],
            "account": row["account"],
            "category": row["category"],
            "currency": row["currency"],
            "rate": _num(row["rate"], 6),
            "balance": _num(row["balance"], 2),
            "tax": _num(row["tax"], 4),
            "balance_cad": _num(row["balance_cad"], 2),
            "balance_net": _num(row["balance_net"], 2),
        }
        for _, row in df.iterrows()
    ]
    return {
        "entries": entries,
        "count": len(entries),
        "date": entries[0]["date"] if (date or latest_only) and entries else None,
    }


def get_equity_summary(date: str | None = None) -> dict[str, Any]:
    """Net-worth summary for a snapshot date (defaults to the latest date).

    Returns totals plus breakdowns by category and by account, in CAD.
    """
    df = _equity_frame()
    if df.empty:
        return {"date": None, "totals": {}, "by_category": [], "by_account": []}

    snapshot_date = date or df["date"].max()
    snap = df[df["date"] == snapshot_date]
    if snap.empty:
        return {
            "date": snapshot_date,
            "totals": {},
            "by_category": [],
            "by_account": [],
        }

    def _breakdown(field: str) -> list[dict[str, Any]]:
        grouped = (
            snap.groupby(field)[["balance_cad", "balance_net"]]
            .sum()
            .reset_index()
            .sort_values("balance_net", ascending=False)
        )
        return [
            {
                field: row[field],
                "balance_cad": _num(row["balance_cad"], 2),
                "balance_net": _num(row["balance_net"], 2),
            }
            for _, row in grouped.iterrows()
        ]

    return {
        "date": snapshot_date,
        "totals": {
            "balance_cad": _num(snap["balance_cad"].sum(), 2),
            "balance_net": _num(snap["balance_net"].sum(), 2),
            "entry_count": int(len(snap)),
        },
        "by_category": _breakdown("category"),
        "by_account": _breakdown("account"),
    }


def list_equity_dates() -> dict[str, Any]:
    """All distinct equity snapshot dates, most recent first."""
    df = _equity_frame()
    if df.empty:
        return {"dates": []}
    dates = sorted(df["date"].unique().tolist(), reverse=True)
    return {"dates": dates}
