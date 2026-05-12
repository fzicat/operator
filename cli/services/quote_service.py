from __future__ import annotations

from copy import deepcopy
from typing import Any

import pandas as pd

from cli.db import ibkr_db, market_quote_db
from cli.domain.contracts import (
    EquityContract,
    InvalidContract,
    OptionContract,
    build_contract_key_from_trade_row,
    is_option_trade,
    to_equity_contract,
    to_option_contract,
)
from cli.domain.quotes import QuoteRecord
from cli.providers.ibkr_gateway_provider import IBKRGatewayProvider
from cli.providers.yahoo_equity_provider import YahooEquityProvider


UNAVAILABLE_STATUSES = {
    "unavailable",
    "gateway_unreachable",
    "contract_unresolved",
    "permission_denied",
}


def calculate_pnl(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return trades_df.copy()

    df = trades_df.copy()
    df["realized_pnl"] = 0.0
    df["remaining_qty"] = 0.0

    inventory: dict[str, list[dict[str, float | int]]] = {}

    for idx, row in df.iterrows():
        symbol = row["symbol"]
        qty = float(row["quantity"] or 0.0)
        price = float(row["tradePrice"] or 0.0)
        multiplier = float(row["multiplier"] or 1.0)

        if symbol not in inventory:
            inventory[symbol] = []

        if not inventory[symbol]:
            df.at[idx, "remaining_qty"] = qty
            inventory[symbol].append({"idx": idx, "qty": qty, "price": price})
            continue

        head = inventory[symbol][0]
        if (qty > 0 and head["qty"] > 0) or (qty < 0 and head["qty"] < 0):
            df.at[idx, "remaining_qty"] = qty
            inventory[symbol].append({"idx": idx, "qty": qty, "price": price})
            continue

        qty_to_process = qty
        total_pnl = 0.0

        while qty_to_process != 0 and inventory[symbol]:
            item = inventory[symbol][0]
            open_qty = float(item["qty"])
            open_price = float(item["price"])
            open_idx = int(item["idx"])

            if abs(qty_to_process) >= abs(open_qty):
                match_qty = -open_qty
                total_pnl += -(price - open_price) * match_qty * multiplier
                qty_to_process -= match_qty
                df.at[open_idx, "remaining_qty"] = 0.0
                inventory[symbol].pop(0)
            else:
                total_pnl += -(price - open_price) * qty_to_process * multiplier
                item["qty"] = open_qty + qty_to_process
                df.at[open_idx, "remaining_qty"] = item["qty"]
                qty_to_process = 0.0

        df.at[idx, "realized_pnl"] = total_pnl

        if qty_to_process != 0:
            df.at[idx, "remaining_qty"] = qty_to_process
            inventory[symbol].append({"idx": idx, "qty": qty_to_process, "price": price})

    return df


def calculate_credit(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return trades_df.copy()
    df = trades_df.copy()
    multiplier = df["multiplier"].fillna(1.0)
    df["credit"] = df["remaining_qty"] * df["tradePrice"] * multiplier * -1
    return df


def prepare_trades(trades_df: pd.DataFrame | None = None) -> pd.DataFrame:
    if trades_df is None:
        trades_df = ibkr_db.fetch_all_trades_as_df()
    if trades_df.empty:
        return trades_df.copy()

    df = trades_df.copy()
    if "symbol" in df.columns:
        df = df[df["symbol"] != "USD.CAD"].copy()
    df = calculate_pnl(df)
    df = calculate_credit(df)
    df["contract_key"] = df.apply(build_contract_key_from_trade_row, axis=1)
    return df


def _dedupe_contracts(contracts: list[EquityContract | OptionContract]) -> list[EquityContract | OptionContract]:
    deduped: dict[str, EquityContract | OptionContract] = {}
    for contract in contracts:
        deduped[contract.contract_key] = contract
    return list(deduped.values())


def build_open_contracts(trades_df: pd.DataFrame) -> dict[str, Any]:
    open_rows = trades_df[trades_df["remaining_qty"] != 0].copy() if not trades_df.empty else pd.DataFrame()

    equities: list[EquityContract] = []
    options: list[OptionContract] = []
    invalids: list[InvalidContract] = []

    for _, row in open_rows.iterrows():
        if is_option_trade(row):
            contract = to_option_contract(row)
            if isinstance(contract, InvalidContract):
                invalids.append(contract)
            else:
                options.append(contract)
        else:
            contract = to_equity_contract(row)
            if isinstance(contract, InvalidContract):
                invalids.append(contract)
            else:
                equities.append(contract)

    equities = [c for c in _dedupe_contracts(equities) if isinstance(c, EquityContract)]
    options = [c for c in _dedupe_contracts(options) if isinstance(c, OptionContract)]

    return {
        "open_rows": open_rows,
        "equities": equities,
        "options": options,
        "invalids": invalids,
    }


def _overlay_stale_from_existing(base_quote: QuoteRecord, existing: dict | None) -> QuoteRecord:
    if not existing or existing.get("mark") is None:
        return base_quote

    stale_quote = deepcopy(base_quote)
    stale_quote.source = existing.get("source") or stale_quote.source
    stale_quote.bid = existing.get("bid")
    stale_quote.ask = existing.get("ask")
    stale_quote.last = existing.get("last")
    stale_quote.close = existing.get("close")
    stale_quote.mark = existing.get("mark")
    stale_quote.quote_time = existing.get("quote_time")
    stale_quote.status = "stale"
    stale_quote.raw_payload = existing.get("raw_payload")
    stale_quote.conid = existing.get("conid")
    return stale_quote


def refresh_mtm_quotes(trades_df: pd.DataFrame | None = None, skip_options: bool = False) -> dict[str, Any]:
    prepared = prepare_trades(trades_df)
    contract_bundle = build_open_contracts(prepared)
    equities: list[EquityContract] = contract_bundle["equities"]
    options: list[OptionContract] = [] if skip_options else contract_bundle["options"]
    invalids: list[InvalidContract] = contract_bundle["invalids"]

    requested_keys = [contract.contract_key for contract in equities + options if contract.contract_key]
    existing_quotes = market_quote_db.fetch_quotes_by_keys(requested_keys)

    fetched_quotes: list[QuoteRecord] = []
    provider_messages: list[str] = []
    quote_lookup: dict[str, QuoteRecord] = {}

    ib_provider = IBKRGatewayProvider()
    ib_status = ib_provider.connect()

    if ib_status.ok:
        provider_messages.append("ibkr:connected")
        try:
            equity_quotes = ib_provider.fetch_equity_quotes(equities)
            option_quotes = ib_provider.fetch_option_quotes(options)
        finally:
            ib_provider.disconnect()

        equity_quote_lookup = {quote.contract_key: quote for quote in equity_quotes}
        yahoo_fallback_contracts = [
            contract
            for contract in equities
            if (
                (quote := equity_quote_lookup.get(contract.contract_key)) is not None
                and quote.status in {"permission_denied", "unavailable"}
                and quote.mark is None
            )
        ]

        if yahoo_fallback_contracts:
            yahoo_provider = YahooEquityProvider()
            try:
                yahoo_quotes = yahoo_provider.fetch_equity_quotes(yahoo_fallback_contracts)
                provider_messages.append(f"yahoo_fallback:equities:{len(yahoo_fallback_contracts)}")
                for quote in yahoo_quotes:
                    equity_quote_lookup[quote.contract_key] = quote
            except Exception as exc:
                provider_messages.append(f"yahoo_fallback:failed:{exc}")

        fetched_quotes.extend(equity_quote_lookup.values())
        fetched_quotes.extend(option_quotes)
    else:
        provider_messages.append(f"ibkr:{ib_status.status}:{ib_status.message}")
        yahoo_provider = YahooEquityProvider()
        try:
            fetched_quotes.extend(yahoo_provider.fetch_equity_quotes(equities))
            provider_messages.append("yahoo_fallback:equities")
        except Exception as exc:
            provider_messages.append(f"yahoo_fallback:failed:{exc}")

        for contract in options:
            fetched_quotes.append(
                QuoteRecord(
                    contract_key=contract.contract_key,
                    instrument_type="option",
                    source="ibkr",
                    symbol=contract.symbol,
                    underlying_symbol=contract.underlying_symbol,
                    expiry=contract.expiry,
                    put_call=contract.put_call,
                    strike=contract.strike,
                    multiplier=contract.multiplier,
                    status="gateway_unreachable",
                )
            )

    for invalid in invalids:
        if invalid.contract_key:
            fetched_quotes.append(
                QuoteRecord(
                    contract_key=invalid.contract_key,
                    instrument_type=invalid.instrument_type,
                    source="ibkr",
                    symbol=invalid.symbol or invalid.underlying_symbol or "",
                    underlying_symbol=invalid.underlying_symbol,
                    status="contract_unresolved",
                    raw_payload={"reason": invalid.reason},
                )
            )

    for quote in fetched_quotes:
        existing = existing_quotes.get(quote.contract_key)
        if quote.status in UNAVAILABLE_STATUSES:
            quote = _overlay_stale_from_existing(quote, existing)
        quote_lookup[quote.contract_key] = quote

    save_result = market_quote_db.upsert_quotes(list(quote_lookup.values()))
    persisted_quotes = market_quote_db.fetch_quotes_by_keys(requested_keys)

    merged_quotes = {**persisted_quotes}
    for key, quote in quote_lookup.items():
        merged_quotes[key] = quote.to_db_dict() if hasattr(quote, "to_db_dict") else quote

    statuses = {}
    for quote in quote_lookup.values():
        statuses[quote.status] = statuses.get(quote.status, 0) + 1

    return {
        "ok": True,
        "message": _build_summary_message(len(equities), len(options), quote_lookup, provider_messages, save_result),
        "provider_messages": provider_messages,
        "requested_equities": len(equities),
        "requested_options": len(options),
        "invalid_contracts": len(invalids),
        "quotes": merged_quotes,
        "statuses": statuses,
        "save_result": save_result,
    }


def _build_summary_message(
    equity_count: int,
    option_count: int,
    quotes: dict[str, QuoteRecord],
    provider_messages: list[str],
    save_result: dict[str, Any],
) -> str:
    live = sum(1 for quote in quotes.values() if quote.status == "live")
    delayed = sum(1 for quote in quotes.values() if quote.status == "delayed")
    stale = sum(1 for quote in quotes.values() if quote.status == "stale")
    unavailable = sum(1 for quote in quotes.values() if quote.status in UNAVAILABLE_STATUSES)
    return (
        f"Quote refresh complete | equities={equity_count} options={option_count} "
        f"live={live} delayed={delayed} stale={stale} unavailable={unavailable} "
        f"saved={save_result.get('saved', 0)} skipped={save_result.get('skipped', 0)} "
        f"providers={' ; '.join(provider_messages)}"
    )
