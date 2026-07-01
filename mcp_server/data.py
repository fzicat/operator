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
from datetime import date
from typing import Any

# Make the project root importable so ``cli.*`` and ``shared.*`` resolve the same
# way they do when running the CLI (see cli/main.py).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd  # noqa: E402

from cli.domain.contracts import build_contract_key_from_trade_row  # noqa: E402
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


def _text(value: Any) -> str | None:
    """Return a stripped string or None for empty/NaN-ish values."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _parse_date(value: str | None, field_name: str) -> date | None:
    if not value:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"{field_name} must be a valid date or datetime")
    return parsed.date()


def _iso_datetime(value: Any) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.isoformat()


def _date_string(value: Any) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m-%d")


def _limit(value: int | None, default: int = 200, maximum: int = 1000) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, maximum))


def _offset(value: int | None) -> int:
    if value is None:
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _open_close_tokens(value: Any) -> set[str]:
    """Normalize IBKR open/close indicators such as 'O', 'C', or 'D;O'."""
    raw = _upper(value)
    if not raw:
        return set()
    return {token.strip() for token in raw.replace(",", ";").split(";") if token.strip()}


def _open_close_label(value: Any) -> str | None:
    tokens = _open_close_tokens(value)
    if "O" in tokens and "C" in tokens:
        return "open_close"
    if "O" in tokens:
        return "open"
    if "C" in tokens:
        return "close"
    return _text(value)


def _instrument_type(row: Any) -> str:
    if _is_option(row.get("putCall") if hasattr(row, "get") else None):
        return "option"
    symbol = _upper(row.get("symbol") if hasattr(row, "get") else None)
    if symbol in {"USD.CAD", "CAD.USD"} or "." in symbol:
        return "fx"
    return "stock"


def _underlying_symbol(row: Any) -> str | None:
    if not hasattr(row, "get"):
        return None
    return _text(row.get("underlyingSymbol")) or _text(row.get("symbol"))


def _trade_side(row: Any) -> str | None:
    qty = _num(row.get("quantity") if hasattr(row, "get") else None)
    if qty is None or abs(qty) < 1e-12:
        return None
    return "buy" if qty > 0 else "sell"


def _strategy_bucket(row: Any) -> str:
    """Classify a trade into a compact, strategy-ish bucket for summaries."""
    instrument = _instrument_type(row)
    qty = _num(row.get("quantity") if hasattr(row, "get") else None) or 0.0
    price = _num(row.get("tradePrice") if hasattr(row, "get") else None) or 0.0

    if instrument == "fx":
        return "fx"
    if instrument != "option":
        if qty > 0:
            return "stock_buy"
        if qty < 0:
            return "stock_sell"
        return "stock"

    put_call = "call" if _upper(row.get("putCall")) == "C" else "put"
    tokens = _open_close_tokens(row.get("openCloseIndicator"))
    is_open = "O" in tokens
    is_close = "C" in tokens

    if is_close and abs(price) < 1e-9 and qty > 0:
        return f"short_{put_call}_zero_price_close"
    if qty < 0 and (is_open or not is_close):
        return f"short_{put_call}_open"
    if qty > 0 and is_close:
        return f"short_{put_call}_close"
    if qty > 0 and is_open:
        return f"long_{put_call}_open"
    if qty < 0 and is_close:
        return f"long_{put_call}_close"
    return f"{put_call}_option"


def _normalize_trade_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Add normalized/computed columns used by the trade-facing MCP tools."""
    if df.empty:
        return df.copy()

    normalized = df.copy()
    for column in [
        "quantity",
        "tradePrice",
        "multiplier",
        "ibCommission",
        "strike",
        "delta",
        "und_price",
        "realized_pnl",
        "remaining_qty",
        "credit",
        "mtm_price",
        "mtm_value",
        "unrealized_pnl",
    ]:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    if "dateTime" in normalized.columns:
        normalized["_trade_ts"] = pd.to_datetime(normalized["dateTime"], errors="coerce")
        normalized["_trade_date"] = normalized["_trade_ts"].dt.date
        normalized["_trade_month"] = normalized["_trade_ts"].dt.strftime("%Y-%m")
    else:
        normalized["_trade_ts"] = pd.NaT
        normalized["_trade_date"] = pd.NaT
        normalized["_trade_month"] = None

    normalized["_instrument_type"] = normalized.apply(_instrument_type, axis=1)
    normalized["_underlying"] = normalized.apply(_underlying_symbol, axis=1)
    normalized["_put_call"] = normalized["putCall"].map(lambda v: _upper(v) or None)
    normalized["_open_close"] = normalized["openCloseIndicator"].map(_open_close_label)
    normalized["_trade_side"] = normalized.apply(_trade_side, axis=1)
    normalized["_strategy_bucket"] = normalized.apply(_strategy_bucket, axis=1)

    multiplier = normalized.get("multiplier", pd.Series(1.0, index=normalized.index)).fillna(1.0)
    quantity = normalized.get("quantity", pd.Series(0.0, index=normalized.index)).fillna(0.0)
    price = normalized.get("tradePrice", pd.Series(0.0, index=normalized.index)).fillna(0.0)
    commission = normalized.get("ibCommission", pd.Series(0.0, index=normalized.index)).fillna(0.0)
    normalized["_trade_cashflow"] = -quantity * price * multiplier
    normalized["_net_cashflow"] = normalized["_trade_cashflow"] + commission
    return normalized


def _load_trade_analysis_frame() -> pd.DataFrame:
    """All IBKR trades plus FIFO realized PnL and normalized helper columns.

    Unlike ``quote_service.prepare_trades``, this intentionally keeps every raw
    IBKR trade row (including non-position rows such as FX) because these tools
    answer history questions, not only current position questions.
    """
    raw = ibkr_db.fetch_all_trades_as_df()
    if raw.empty:
        return raw
    df = quote_service.calculate_pnl(raw)
    df = quote_service.calculate_credit(df)
    df["contract_key"] = df.apply(build_contract_key_from_trade_row, axis=1)
    return _normalize_trade_frame(df)


def _apply_trade_filters(
    df: pd.DataFrame,
    *,
    symbol: str | None = None,
    underlying: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    instrument_type: str | None = None,
    put_call: str | None = None,
    open_close: str | None = None,
) -> pd.DataFrame:
    """Apply shared trade filters used by list/summary tools."""
    if df.empty:
        return df

    filtered = df.copy()

    if symbol:
        sym = _upper(symbol)
        filtered = filtered[
            (filtered["symbol"].fillna("").astype(str).str.upper() == sym)
            | (filtered["_underlying"].fillna("").astype(str).str.upper() == sym)
        ]

    if underlying:
        und = _upper(underlying)
        filtered = filtered[filtered["_underlying"].fillna("").astype(str).str.upper() == und]

    start = _parse_date(from_date, "from_date")
    if start:
        filtered = filtered[filtered["_trade_date"] >= start]

    end = _parse_date(to_date, "to_date")
    if end:
        filtered = filtered[filtered["_trade_date"] <= end]

    if instrument_type:
        inst = _upper(instrument_type)
        aliases = {
            "EQUITY": "STOCK",
            "SHARE": "STOCK",
            "SHARES": "STOCK",
            "FOREX": "FX",
            "CURRENCY": "FX",
        }
        inst = aliases.get(inst, inst)
        if inst in {"CALL", "C"}:
            filtered = filtered[filtered["_put_call"] == "C"]
        elif inst in {"PUT", "P"}:
            filtered = filtered[filtered["_put_call"] == "P"]
        elif inst != "ALL":
            filtered = filtered[filtered["_instrument_type"].str.upper() == inst]

    if put_call:
        pc = _upper(put_call)
        if pc in {"CALL", "CALLS"}:
            pc = "C"
        elif pc in {"PUT", "PUTS"}:
            pc = "P"
        filtered = filtered[filtered["_put_call"] == pc]

    if open_close:
        desired = _upper(open_close)
        if desired in {"OPEN", "O"}:
            desired_token = "O"
        elif desired in {"CLOSE", "CLOSED", "C"}:
            desired_token = "C"
        else:
            desired_token = desired
        filtered = filtered[
            filtered["openCloseIndicator"].map(
                lambda value: desired_token in _open_close_tokens(value)
            )
        ]

    return filtered


def _trade_record(row: Any) -> dict[str, Any]:
    """Serialize one trade row to JSON-safe primitives."""
    return {
        "trade_id": _text(row.get("tradeID")),
        "account_id": _text(row.get("accountId")),
        "date_time": _iso_datetime(row.get("dateTime")),
        "date": _date_string(row.get("dateTime")),
        "underlying_symbol": _text(row.get("_underlying")),
        "symbol": _text(row.get("symbol")),
        "description": _text(row.get("description")),
        "instrument_type": _text(row.get("_instrument_type")),
        "put_call": _text(row.get("_put_call")),
        "expiry": _text(row.get("expiry")),
        "strike": _num(row.get("strike"), 4),
        "quantity": _num(row.get("quantity"), 4),
        "trade_price": _num(row.get("tradePrice"), 6),
        "multiplier": _num(row.get("multiplier"), 4),
        "commission": _num(row.get("ibCommission"), 4),
        "currency": _text(row.get("currency")),
        "open_close": _text(row.get("_open_close")),
        "raw_open_close_indicator": _text(row.get("openCloseIndicator")),
        "side": _text(row.get("_trade_side")),
        "strategy_bucket": _text(row.get("_strategy_bucket")),
        "trade_cashflow": _num(row.get("_trade_cashflow"), 2),
        "net_cashflow": _num(row.get("_net_cashflow"), 2),
        "realized_pnl": _num(row.get("realized_pnl"), 2),
        "remaining_qty": _num(row.get("remaining_qty"), 4),
        "dte": _num(row.get("dte"), 0),
        "dit": _num(row.get("dit"), 0),
        "delta": _num(row.get("delta"), 6),
        "underlying_price": _num(row.get("und_price"), 4),
        "contract_key": _text(row.get("contract_key")),
        "notes": _text(row.get("notes")),
    }


def _trade_group_summary(group: pd.DataFrame) -> dict[str, Any]:
    if group.empty:
        return {
            "trade_count": 0,
            "option_trade_count": 0,
            "stock_trade_count": 0,
            "fx_trade_count": 0,
            "option_contract_volume": 0.0,
            "stock_share_volume": 0.0,
            "gross_cashflow": 0.0,
            "net_cashflow": 0.0,
            "commissions": 0.0,
            "realized_pnl": 0.0,
        }

    options = group[group["_instrument_type"] == "option"]
    stocks = group[group["_instrument_type"] == "stock"]
    fx = group[group["_instrument_type"] == "fx"]
    return {
        "trade_count": int(len(group)),
        "option_trade_count": int(len(options)),
        "stock_trade_count": int(len(stocks)),
        "fx_trade_count": int(len(fx)),
        "option_contract_volume": _num(options["quantity"].abs().sum(), 4),
        "stock_share_volume": _num(stocks["quantity"].abs().sum(), 4),
        "gross_cashflow": _num(group["_trade_cashflow"].sum(), 2),
        "net_cashflow": _num(group["_net_cashflow"].sum(), 2),
        "commissions": _num(group["ibCommission"].fillna(0).sum(), 2),
        "realized_pnl": _num(group.get("realized_pnl", pd.Series(dtype=float)).fillna(0).sum(), 2),
    }


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
# IBKR trade history and option analytics
# --------------------------------------------------------------------------- #
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
) -> dict[str, Any]:
    """List raw IBKR trades with optional filters and computed FIFO fields."""
    df = _load_trade_analysis_frame()
    if df.empty:
        return {"trades": [], "count": 0, "total_count": 0, "offset": 0, "limit": 0}

    filtered = _apply_trade_filters(
        df,
        symbol=symbol,
        underlying=underlying,
        from_date=from_date,
        to_date=to_date,
        instrument_type=instrument_type,
        put_call=put_call,
        open_close=open_close,
    )

    ascending = _upper(sort_order) in {"OLDEST", "ASC", "ASCENDING"}
    filtered = filtered.sort_values("_trade_ts", ascending=ascending)

    page_size = _limit(limit)
    start = _offset(offset)
    page = filtered.iloc[start : start + page_size]
    trades = [_trade_record(row) for _, row in page.iterrows()]

    return {
        "trades": trades,
        "count": len(trades),
        "total_count": int(len(filtered)),
        "offset": start,
        "limit": page_size,
        "sort_order": "oldest" if ascending else "newest",
        "filters": {
            "symbol": symbol,
            "underlying": underlying,
            "from_date": from_date,
            "to_date": to_date,
            "instrument_type": instrument_type,
            "put_call": put_call,
            "open_close": open_close,
        },
    }


def _group_trade_summaries(
    df: pd.DataFrame,
    group_field: str,
    label_field: str,
    *,
    sort_by: str = "realized_pnl_abs",
    limit: int = 50,
) -> list[dict[str, Any]]:
    if df.empty:
        return []

    items: list[dict[str, Any]] = []
    for key, group in df.groupby(group_field, dropna=False):
        label = "unknown" if pd.isna(key) else str(key)
        item = {label_field: label}
        item.update(_trade_group_summary(group))
        items.append(item)

    if sort_by == "label":
        items.sort(key=lambda item: item[label_field])
    elif sort_by == "trade_count":
        items.sort(key=lambda item: item["trade_count"], reverse=True)
    else:
        items.sort(key=lambda item: abs(item.get("realized_pnl") or 0.0), reverse=True)

    return items[:limit]


def get_ibkr_trade_summary(
    symbol: str | None = None,
    underlying: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    instrument_type: str | None = None,
    put_call: str | None = None,
    open_close: str | None = None,
    group_limit: int | None = 50,
) -> dict[str, Any]:
    """Aggregate IBKR trade history by symbol, month, and strategy-ish buckets."""
    df = _load_trade_analysis_frame()
    if df.empty:
        return {
            "totals": _trade_group_summary(df),
            "by_symbol": [],
            "by_month": [],
            "by_strategy": [],
        }

    filtered = _apply_trade_filters(
        df,
        symbol=symbol,
        underlying=underlying,
        from_date=from_date,
        to_date=to_date,
        instrument_type=instrument_type,
        put_call=put_call,
        open_close=open_close,
    )

    max_groups = _limit(group_limit, default=50, maximum=200)
    totals = _trade_group_summary(filtered)
    totals["underlying_count"] = int(filtered["_underlying"].dropna().nunique()) if not filtered.empty else 0
    totals["first_trade_date"] = _date_string(filtered["_trade_ts"].min()) if not filtered.empty else None
    totals["last_trade_date"] = _date_string(filtered["_trade_ts"].max()) if not filtered.empty else None

    return {
        "totals": totals,
        "by_symbol": _group_trade_summaries(
            filtered, "_underlying", "underlying_symbol", limit=max_groups
        ),
        "by_month": _group_trade_summaries(
            filtered, "_trade_month", "month", sort_by="label", limit=max_groups
        ),
        "by_strategy": _group_trade_summaries(
            filtered, "_strategy_bucket", "strategy_bucket", sort_by="trade_count", limit=max_groups
        ),
        "filters": {
            "symbol": symbol,
            "underlying": underlying,
            "from_date": from_date,
            "to_date": to_date,
            "instrument_type": instrument_type,
            "put_call": put_call,
            "open_close": open_close,
        },
    }


def _weighted_average(group: pd.DataFrame, value_field: str, weight_field: str = "remaining_qty") -> float | None:
    if value_field not in group.columns:
        return None
    values = pd.to_numeric(group[value_field], errors="coerce")
    weights = pd.to_numeric(group[weight_field], errors="coerce").abs() if weight_field in group.columns else pd.Series(1.0, index=group.index)
    valid = values.notna() & weights.notna() & (weights > 0)
    if not valid.any():
        return None
    return _num((values[valid] * weights[valid]).sum() / weights[valid].sum(), 6)


def _first_numeric(group: pd.DataFrame, field: str, digits: int | None = None) -> float | None:
    if field not in group.columns:
        return None
    values = pd.to_numeric(group[field], errors="coerce").dropna()
    if values.empty:
        return None
    return _num(values.iloc[0], digits)


def get_option_exposure(
    symbol: str | None = None,
    underlying: str | None = None,
    put_call: str | None = None,
    side: str = "short",
    expiry: str | None = None,
    include_quotes: bool = True,
) -> dict[str, Any]:
    """Current option exposure by open contract, including notional and delta."""
    df = _load_valued_trades() if include_quotes else _load_trade_analysis_frame()
    if df.empty:
        return {"exposures": [], "totals": {}, "by_expiry": []}

    df = _normalize_trade_frame(df)
    options = df[(df["_instrument_type"] == "option") & (df["remaining_qty"].fillna(0) != 0)].copy()
    options = _apply_trade_filters(
        options,
        symbol=symbol,
        underlying=underlying,
        put_call=put_call,
        instrument_type="option",
    )

    desired_side = _upper(side)
    if desired_side in {"SHORT", "SOLD"}:
        options = options[options["remaining_qty"] < 0]
    elif desired_side in {"LONG", "BOUGHT"}:
        options = options[options["remaining_qty"] > 0]
    elif desired_side not in {"ALL", "ANY", ""}:
        raise ValueError("side must be 'short', 'long', or 'all'")

    if expiry:
        requested_expiry = "".join(ch for ch in str(expiry) if ch.isdigit())
        options = options[options["expiry"].fillna("").astype(str).str.replace("-", "", regex=False) == requested_expiry]

    exposures: list[dict[str, Any]] = []
    for contract_key, group in options.groupby("contract_key", dropna=False):
        row = group.iloc[0]
        remaining_qty = float(group["remaining_qty"].fillna(0).sum())
        if abs(remaining_qty) < 1e-12:
            continue

        strike = _num(row.get("strike")) or 0.0
        multiplier = _num(row.get("multiplier")) or 100.0
        notional = abs(remaining_qty) * strike * multiplier
        avg_delta = _weighted_average(group, "delta")
        exposure = {
            "underlying_symbol": _text(row.get("_underlying")),
            "symbol": _text(row.get("symbol")),
            "contract_key": _text(contract_key),
            "expiry": _text(row.get("expiry")),
            "put_call": _text(row.get("_put_call")),
            "strike": _num(strike, 4),
            "side": "short" if remaining_qty < 0 else "long",
            "remaining_contracts": _num(remaining_qty, 4),
            "abs_contracts": _num(abs(remaining_qty), 4),
            "multiplier": _num(multiplier, 4),
            "notional": _num(notional, 2),
            "signed_notional": _num(remaining_qty * strike * multiplier, 2),
            "delta": avg_delta,
            "position_delta": _num((avg_delta or 0.0) * remaining_qty * multiplier, 4) if avg_delta is not None else None,
            "underlying_price": _weighted_average(group, "und_price"),
            "premium_credit_remaining": _num(group.get("credit", pd.Series(dtype=float)).fillna(0).sum(), 2),
            "mtm_price": _first_numeric(group, "mtm_price", 4),
            "mtm_value": _num(group.get("mtm_value", pd.Series(dtype=float)).fillna(0).sum(), 2),
            "unrealized_pnl": _num(group.get("unrealized_pnl", pd.Series(dtype=float)).fillna(0).sum(), 2),
            "quote_status": sorted(set(str(v) for v in group.get("quote_status", pd.Series(dtype=str)).dropna() if str(v))),
            "open_lot_count": int(len(group)),
        }
        exposures.append(exposure)

    exposures.sort(key=lambda item: (item.get("expiry") or "", item.get("underlying_symbol") or "", item.get("strike") or 0.0))

    totals = {
        "contract_count": len(exposures),
        "short_put_contracts": _num(sum(e["abs_contracts"] or 0.0 for e in exposures if e["side"] == "short" and e["put_call"] == "P"), 4),
        "short_call_contracts": _num(sum(e["abs_contracts"] or 0.0 for e in exposures if e["side"] == "short" and e["put_call"] == "C"), 4),
        "long_put_contracts": _num(sum(e["abs_contracts"] or 0.0 for e in exposures if e["side"] == "long" and e["put_call"] == "P"), 4),
        "long_call_contracts": _num(sum(e["abs_contracts"] or 0.0 for e in exposures if e["side"] == "long" and e["put_call"] == "C"), 4),
        "total_notional": _num(sum(e["notional"] or 0.0 for e in exposures), 2),
        "short_put_notional": _num(sum(e["notional"] or 0.0 for e in exposures if e["side"] == "short" and e["put_call"] == "P"), 2),
        "short_call_notional": _num(sum(e["notional"] or 0.0 for e in exposures if e["side"] == "short" and e["put_call"] == "C"), 2),
        "mtm_value": _num(sum(e["mtm_value"] or 0.0 for e in exposures), 2),
        "unrealized_pnl": _num(sum(e["unrealized_pnl"] or 0.0 for e in exposures), 2),
        "position_delta": _num(sum(e["position_delta"] or 0.0 for e in exposures), 4),
    }

    by_expiry: list[dict[str, Any]] = []
    if exposures:
        exposure_frame = pd.DataFrame(exposures)
        for exp, rows in exposure_frame.groupby("expiry", dropna=False):
            by_expiry.append(
                {
                    "expiry": None if pd.isna(exp) else str(exp),
                    "contract_count": int(len(rows)),
                    "contracts": _num(rows["abs_contracts"].sum(), 4),
                    "notional": _num(rows["notional"].sum(), 2),
                    "mtm_value": _num(rows["mtm_value"].fillna(0).sum(), 2),
                    "unrealized_pnl": _num(rows["unrealized_pnl"].fillna(0).sum(), 2),
                    "position_delta": _num(rows["position_delta"].fillna(0).sum(), 4),
                }
            )

    return {"exposures": exposures, "totals": totals, "by_expiry": by_expiry}


def _assignment_event_type(put_call: str, stock_qty: float) -> str:
    if put_call == "P" and stock_qty > 0:
        return "short_put_assignment"
    if put_call == "C" and stock_qty < 0:
        return "short_call_assignment"
    if put_call == "C" and stock_qty > 0:
        return "long_call_exercise"
    if put_call == "P" and stock_qty < 0:
        return "long_put_exercise"
    return "option_exercise_or_assignment"


def _infer_assignment_events(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []

    work = df.copy()
    work["_timestamp_key"] = work["_trade_ts"].map(lambda ts: ts.isoformat() if pd.notna(ts) else None)
    work["_price_key"] = work["tradePrice"].round(4)
    work["_strike_key"] = work["strike"].round(4)

    stock_rows = work[(work["_instrument_type"] == "stock") & (work["quantity"].fillna(0) != 0)]
    stock_groups: dict[tuple[Any, Any, Any], pd.DataFrame] = {}
    for key, group in stock_rows.groupby(["_timestamp_key", "_underlying", "_price_key"], dropna=False):
        stock_groups[key] = group

    option_closes = work[
        (work["_instrument_type"] == "option")
        & (work["openCloseIndicator"].map(lambda value: "C" in _open_close_tokens(value)))
        & (work["tradePrice"].fillna(0).abs() < 1e-9)
        & (work["quantity"].fillna(0).abs() > 0)
    ].copy()

    events: list[dict[str, Any]] = []
    group_fields = ["_timestamp_key", "_underlying", "_strike_key", "_put_call", "expiry"]
    for (_, underlying_value, strike_value, put_call_value, expiry_value), option_group in option_closes.groupby(group_fields, dropna=False):
        first_option = option_group.iloc[0]
        stock_group = stock_groups.get((first_option.get("_timestamp_key"), underlying_value, strike_value))
        if stock_group is None or stock_group.empty:
            continue

        option_qty = float(option_group["quantity"].fillna(0).sum())
        contracts = abs(option_qty)
        multiplier = _num(first_option.get("multiplier")) or 100.0
        expected_shares = contracts * multiplier
        stock_qty = float(stock_group["quantity"].fillna(0).sum())
        if expected_shares and abs(abs(stock_qty) - expected_shares) > max(1.0, expected_shares * 0.01):
            continue

        expiry_date = quote_service.parse_option_expiry(first_option)
        event_date = first_option.get("_trade_date")
        days_to_expiry = (expiry_date - event_date).days if expiry_date and event_date else None
        stock_price = _first_numeric(stock_group, "tradePrice", 4)

        events.append(
            {
                "date_time": _iso_datetime(first_option.get("dateTime")),
                "date": _date_string(first_option.get("dateTime")),
                "underlying_symbol": _text(underlying_value),
                "event_type": _assignment_event_type(str(put_call_value), stock_qty),
                "put_call": _text(put_call_value),
                "expiry": None if pd.isna(expiry_value) else str(expiry_value),
                "strike": _num(strike_value, 4),
                "contracts": _num(contracts, 4),
                "multiplier": _num(multiplier, 4),
                "stock_quantity": _num(stock_qty, 4),
                "stock_price": stock_price,
                "stock_notional": _num(abs(stock_qty) * (stock_price or 0.0), 2),
                "option_close_price": 0.0,
                "days_to_expiry": days_to_expiry,
                "option_realized_pnl": _num(option_group.get("realized_pnl", pd.Series(dtype=float)).fillna(0).sum(), 2),
                "stock_realized_pnl": _num(stock_group.get("realized_pnl", pd.Series(dtype=float)).fillna(0).sum(), 2),
                "commissions": _num(
                    option_group.get("ibCommission", pd.Series(dtype=float)).fillna(0).sum()
                    + stock_group.get("ibCommission", pd.Series(dtype=float)).fillna(0).sum(),
                    2,
                ),
                "confidence": "high",
                "match_method": "same_timestamp_zero_price_option_close_at_strike",
                "option_trade_ids": [_text(v) for v in option_group["tradeID"].tolist() if _text(v)],
                "stock_trade_ids": [_text(v) for v in stock_group["tradeID"].tolist() if _text(v)],
                "option_symbols": sorted(set(str(v) for v in option_group["symbol"].dropna())),
            }
        )

    events.sort(key=lambda event: event.get("date_time") or "", reverse=True)
    return events


def get_assignment_history(
    symbol: str | None = None,
    underlying: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    put_call: str | None = None,
    event_type: str | None = None,
    limit: int | None = 200,
) -> dict[str, Any]:
    """Infer option assignment/exercise events from paired option/stock trades.

    IBKR Flex rows in this dataset do not label assignments in the description;
    the reliable signature is a zero-price option close paired at the same
    timestamp with a stock trade in the underlying at the option strike.
    """
    df = _load_trade_analysis_frame()
    events = _infer_assignment_events(df)

    sym = _upper(symbol) if symbol else None
    und = _upper(underlying) if underlying else None
    pc = _upper(put_call) if put_call else None
    if pc in {"CALL", "CALLS"}:
        pc = "C"
    elif pc in {"PUT", "PUTS"}:
        pc = "P"
    requested_event = _upper(event_type) if event_type else None
    start = _parse_date(from_date, "from_date")
    end = _parse_date(to_date, "to_date")

    filtered: list[dict[str, Any]] = []
    for event in events:
        event_underlying = _upper(event.get("underlying_symbol"))
        event_date = _parse_date(event.get("date"), "event.date") if event.get("date") else None
        if sym and event_underlying != sym:
            continue
        if und and event_underlying != und:
            continue
        if pc and event.get("put_call") != pc:
            continue
        if requested_event and _upper(event.get("event_type")) != requested_event:
            continue
        if start and event_date and event_date < start:
            continue
        if end and event_date and event_date > end:
            continue
        filtered.append(event)

    page_size = _limit(limit)
    page = filtered[:page_size]
    totals = {
        "event_count": len(filtered),
        "returned_count": len(page),
        "contracts": _num(sum(event.get("contracts") or 0.0 for event in filtered), 4),
        "stock_notional": _num(sum(event.get("stock_notional") or 0.0 for event in filtered), 2),
        "option_realized_pnl": _num(sum(event.get("option_realized_pnl") or 0.0 for event in filtered), 2),
        "stock_realized_pnl": _num(sum(event.get("stock_realized_pnl") or 0.0 for event in filtered), 2),
        "commissions": _num(sum(event.get("commissions") or 0.0 for event in filtered), 2),
    }

    by_type: list[dict[str, Any]] = []
    for kind in sorted({event["event_type"] for event in filtered}):
        kind_events = [event for event in filtered if event["event_type"] == kind]
        by_type.append(
            {
                "event_type": kind,
                "event_count": len(kind_events),
                "contracts": _num(sum(event.get("contracts") or 0.0 for event in kind_events), 4),
                "stock_notional": _num(sum(event.get("stock_notional") or 0.0 for event in kind_events), 2),
                "option_realized_pnl": _num(sum(event.get("option_realized_pnl") or 0.0 for event in kind_events), 2),
                "stock_realized_pnl": _num(sum(event.get("stock_realized_pnl") or 0.0 for event in kind_events), 2),
            }
        )

    return {
        "events": page,
        "totals": totals,
        "by_type": by_type,
        "limit": page_size,
        "filters": {
            "symbol": symbol,
            "underlying": underlying,
            "from_date": from_date,
            "to_date": to_date,
            "put_call": put_call,
            "event_type": event_type,
        },
    }


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
