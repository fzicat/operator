import csv
import io
from datetime import datetime, date
from pathlib import Path

import pandas as pd
import requests
import time
import xml.etree.ElementTree as ET
from rich.table import Table
from rich.console import Group
from rich.panel import Panel
from shared import config
from cli.db import ibkr_db, market_quote_db
from cli.services import quote_service, valuation_service
from base_module import Module


PERFORMANCE_FILE = Path(__file__).resolve().parent / "data" / "ibkr_performance_2026.csv"


def _parse_option_expiry(row) -> date | None:
    """Return option expiry date from a trade row (symbol like 'GOOGL 260618P00370000'), or None for non-options."""
    symbol = row.get('symbol')
    if isinstance(symbol, str):
        parts = symbol.strip().split()
        if len(parts) >= 2:
            contract = parts[1]
            if len(contract) >= 7 and contract[:6].isdigit():
                try:
                    return datetime.strptime(contract[:6], '%y%m%d').date()
                except ValueError:
                    pass
    expiry = row.get('expiry')
    if expiry:
        digits = ''.join(ch for ch in str(expiry) if ch.isdigit())
        if len(digits) == 8:
            try:
                return datetime.strptime(digits, '%Y%m%d').date()
            except ValueError:
                pass
    return None

class IBKRModule(Module):
    name = "IBKR"
    emoji = "🗠"

    def __init__(self, app):
        super().__init__(app)
        self.trades_df = pd.DataFrame()
        self.position_map = {}
        self.current_symbol = None
        self.output_content = ""
        
        # Load target percentages from database
        self.target_percent = ibkr_db.fetch_symbol_targets()
        self.symbol_basket = ibkr_db.fetch_symbol_baskets()
        self.margin_requirements = ibkr_db.fetch_symbol_margin_requirements()
        
        self.load_trades()

    def load_trades(self):
        self.trades_df = quote_service.prepare_trades(ibkr_db.fetch_all_trades_as_df())
        if not self.trades_df.empty:
            quotes_by_key = market_quote_db.fetch_latest_quotes()
            self.trades_df = valuation_service.apply_quotes(self.trades_df, quotes_by_key)

        count = len(self.trades_df)
        self.app.console.print(f"[info]Trades loaded: {count}[/]")

    def calculate_pnl(self):
        if self.trades_df.empty:
            return

        # Initialize columns
        self.trades_df['realized_pnl'] = 0.0
        self.trades_df['remaining_qty'] = 0.0
        self.trades_df['dte'] = pd.NA
        self.trades_df['dit'] = pd.NA

        # Inventory: symbol -> list of dicts {idx, qty, price, dt}
        inventory = {}

        for idx, row in self.trades_df.iterrows():
            symbol = row['symbol']
            qty = row['quantity']
            price = row['tradePrice']
            multiplier = row['multiplier']

            # Ensure safe floats
            qty = float(qty) if qty is not None else 0.0
            price = float(price) if price is not None else 0.0
            multiplier = float(multiplier) if multiplier is not None else 1.0

            trade_ts = pd.to_datetime(row['dateTime'], errors='coerce')
            trade_date = trade_ts.date() if pd.notnull(trade_ts) else None

            expiry_date = _parse_option_expiry(row)
            if expiry_date and trade_date:
                self.trades_df.at[idx, 'dte'] = (expiry_date - trade_date).days

            if symbol not in inventory:
                inventory[symbol] = []

            # Determine if we are increasing or decreasing/closing position
            # We assume FIFO matching against opposite sign

            # If inventory is empty, always open/add
            if not inventory[symbol]:
                self.trades_df.at[idx, 'remaining_qty'] = qty
                inventory[symbol].append({'idx': idx, 'qty': qty, 'price': price, 'dt': trade_date})
                continue

            # Check head of inventory
            head = inventory[symbol][0]
            # Same sign means adding to position
            if (qty > 0 and head['qty'] > 0) or (qty < 0 and head['qty'] < 0):
                self.trades_df.at[idx, 'remaining_qty'] = qty
                inventory[symbol].append({'idx': idx, 'qty': qty, 'price': price, 'dt': trade_date})
            else:
                # Opposite sign: Close/Reduce position
                qty_to_process = qty # e.g. -100 (Sell)
                total_pnl = 0.0
                first_open_date = None

                while qty_to_process != 0 and inventory[symbol]:
                    item = inventory[symbol][0]
                    open_qty = item['qty']   # e.g. 50 (Buy)
                    open_price = item['price']
                    open_idx = item['idx']
                    if first_open_date is None:
                        first_open_date = item.get('dt')

                    # Check match amount
                    # We are reducing open_qty by some amount
                    # signs are opposite.

                    if abs(qty_to_process) >= abs(open_qty):
                        # Fully consume this open lot
                        match_qty = -open_qty # The amount of the current trade used to close the open lot

                        term_pnl = -(price - open_price) * match_qty * multiplier
                        total_pnl += term_pnl

                        qty_to_process -= match_qty

                        # Update matched open lot
                        self.trades_df.at[open_idx, 'remaining_qty'] = 0
                        inventory[symbol].pop(0)

                    else:
                        # Partially consume open lot
                        term_pnl = -(price - open_price) * qty_to_process * multiplier
                        total_pnl += term_pnl

                        # Update Inventory item
                        item['qty'] += qty_to_process
                        self.trades_df.at[open_idx, 'remaining_qty'] = item['qty']

                        qty_to_process = 0

                self.trades_df.at[idx, 'realized_pnl'] = total_pnl

                if first_open_date and trade_date:
                    self.trades_df.at[idx, 'dit'] = (trade_date - first_open_date).days

                # If we still have quantity left after closing everything, it becomes new position
                if qty_to_process != 0:
                    self.trades_df.at[idx, 'remaining_qty'] = qty_to_process
                    inventory[symbol].append({'idx': idx, 'qty': qty_to_process, 'price': price, 'dt': trade_date})

    def process_mtm_update(self, skip_options: bool = False, verbose: bool = False):
        try:
            result = quote_service.refresh_mtm_quotes(self.trades_df, skip_options=skip_options)
            self.load_trades()
            message = result.get('message', 'Quote refresh complete.')
            if verbose:
                quotes = result.get('quotes', {}) or {}
                lines = []
                for quote in quotes.values():
                    symbol = quote.get('symbol') if isinstance(quote, dict) else getattr(quote, 'symbol', None)
                    mark = quote.get('mark') if isinstance(quote, dict) else getattr(quote, 'mark', None)
                    if symbol is None:
                        continue
                    mark_str = f"{mark:.4f}" if isinstance(mark, (int, float)) else "n/a"
                    lines.append(f"{symbol} -> {mark_str}")
                lines.sort()
                for line in lines:
                    self.app.console.print(line)
                self.app.console.print(message)
                self.app.skip_render = True
            else:
                self.output_content = message
        except Exception as e:
            self.output_content = f"[error]Error fetching prices: {e}[/]"

    def _load_performance_reference(self):
        """Load starting value and cash flows used for year performance calculations."""
        if not PERFORMANCE_FILE.exists():
            raise FileNotFoundError(
                f"Performance file not found: {PERFORMANCE_FILE}"
            )

        rows = []
        with PERFORMANCE_FILE.open("r", newline="") as handle:
            reader = csv.DictReader(handle)
            for idx, row in enumerate(reader, start=2):
                date_str = (row.get("date") or "").strip()
                entry_type = (row.get("type") or "").strip().lower()
                amount_str = (row.get("amount") or "").strip()

                if not date_str and not entry_type and not amount_str:
                    continue

                if not date_str or not entry_type or not amount_str:
                    raise ValueError(
                        f"Invalid row in performance file at line {idx}: {row}"
                    )

                try:
                    amount = float(amount_str)
                except ValueError as e:
                    raise ValueError(
                        f"Invalid amount in performance file at line {idx}: {amount_str}"
                    ) from e

                rows.append({
                    "date": pd.Timestamp(date_str).normalize(),
                    "type": entry_type,
                    "amount": amount,
                })

        start_rows = [row for row in rows if row["type"] == "start"]
        if not start_rows:
            raise ValueError(
                f"Performance file must contain one 'start' row: {PERFORMANCE_FILE}"
            )
        if len(start_rows) > 1:
            raise ValueError(
                f"Performance file must contain only one 'start' row: {PERFORMANCE_FILE}"
            )

        start_row = start_rows[0]
        start_date = start_row["date"]
        starting_value = start_row["amount"]

        net_flows = 0.0
        for row in rows:
            if row["date"] < start_date or row["type"] == "start":
                continue

            if row["type"] == "deposit":
                net_flows += row["amount"]
            elif row["type"] == "withdrawal":
                net_flows -= row["amount"]
            elif row["type"] == "flow":
                net_flows += row["amount"]
            else:
                raise ValueError(
                    "Unsupported performance type "
                    f"'{row['type']}' in {PERFORMANCE_FILE}. "
                    "Use: start, deposit, withdrawal, or flow."
                )

        return {
            "path": PERFORMANCE_FILE,
            "start_date": start_date,
            "starting_value": starting_value,
            "net_flows": net_flows,
            "base_value": starting_value + net_flows,
        }

    def _format_performance_value(self, value, percent=False):
        if abs(value) < 1e-9:
            return "-"

        formatted = f"{value:.2f}%" if percent else f"{value:,.2f}"
        if value > 0:
            return f"[neutral_blue]{formatted}[/neutral_blue]"
        return f"[bright_red]{formatted}[/bright_red]"

    def show_performance(self):
        try:
            if self.trades_df.empty:
                self.output_content = "[info]No trades loaded.[/]"
                return

            reference = self._load_performance_reference()
            start_date = reference["start_date"]
            base_value = reference["base_value"]

            df = self.trades_df.copy()
            df["dateTime"] = pd.to_datetime(
                df["dateTime"], errors="coerce", utc=True
            ).dt.tz_localize(None)

            df = df[df["dateTime"] >= start_date].copy()

            stock_realized = df.loc[~df["putCall"].isin(["C", "P"]), "realized_pnl"].sum()
            call_realized = df.loc[df["putCall"] == "C", "realized_pnl"].sum()
            put_realized = df.loc[df["putCall"] == "P", "realized_pnl"].sum()

            all_stock_rows = self.trades_df[~self.trades_df["putCall"].isin(["C", "P"])]
            call_rows = self.trades_df[self.trades_df["putCall"] == "C"]
            put_rows = self.trades_df[self.trades_df["putCall"] == "P"]

            stock_value = all_stock_rows["credit"].sum() * -1
            stock_mtm = all_stock_rows["mtm_value"].sum()
            stock_unrealized = all_stock_rows["unrealized_pnl"].sum()

            call_unrealized = call_rows["unrealized_pnl"].sum()
            put_unrealized = put_rows["unrealized_pnl"].sum()

            realized_total = stock_realized + call_realized + put_realized
            unrealized_total = stock_unrealized + call_unrealized + put_unrealized

            dollar_rows = [
                ("Realized PnL", stock_realized, call_realized, put_realized, realized_total),
                ("Unrealized PnL", stock_unrealized, call_unrealized, put_unrealized, unrealized_total),
                (
                    "Total",
                    stock_realized + stock_unrealized,
                    call_realized + call_unrealized,
                    put_realized + put_unrealized,
                    realized_total + unrealized_total,
                ),
            ]

            percent_rows = []
            for label, shares, calls, puts, total in dollar_rows:
                if base_value != 0:
                    percent_rows.append(
                        (
                            label,
                            shares / base_value * 100,
                            calls / base_value * 100,
                            puts / base_value * 100,
                            total / base_value * 100,
                        )
                    )
                else:
                    percent_rows.append((label, 0.0, 0.0, 0.0, 0.0))

            summary = Table.grid(padding=(0, 2))
            summary.add_column(style="cyan")
            summary.add_column(justify="right")
            summary.add_row("Period Start", start_date.strftime("%Y-%m-%d"))
            summary.add_row("Starting Value", f"{reference['starting_value']:,.2f}")
            summary.add_row("Net Deposits / Withdrawals", f"{reference['net_flows']:,.2f}")
            summary.add_row("Performance Base", f"{base_value:,.2f}")
            summary.add_row("CSV", str(reference["path"]))
            summary.add_row("Call Unrealized", f"{call_unrealized:,.2f}")
            summary.add_row("Put Unrealized", f"{put_unrealized:,.2f}")

            percent_table = Table(
                title="Performance %",
                expand=False,
                row_styles=["", "on #1d2021"],
            )
            percent_table.add_column("Performance %", style="bold yellow")
            percent_table.add_column("Shares", justify="right")
            percent_table.add_column("Calls", justify="right")
            percent_table.add_column("Puts", justify="right")
            percent_table.add_column("Total", justify="right")

            for label, shares, calls, puts, total in percent_rows:
                percent_table.add_row(
                    label,
                    self._format_performance_value(shares, percent=True),
                    self._format_performance_value(calls, percent=True),
                    self._format_performance_value(puts, percent=True),
                    self._format_performance_value(total, percent=True),
                )

            dollar_table = Table(
                title="Performance $",
                expand=False,
                row_styles=["", "on #1d2021"],
            )
            dollar_table.add_column("Performance $", style="bold yellow")
            dollar_table.add_column("Shares", justify="right")
            dollar_table.add_column("Calls", justify="right")
            dollar_table.add_column("Puts", justify="right")
            dollar_table.add_column("Total", justify="right")

            for label, shares, calls, puts, total in dollar_rows:
                dollar_table.add_row(
                    label,
                    self._format_performance_value(shares),
                    self._format_performance_value(calls),
                    self._format_performance_value(puts),
                    self._format_performance_value(total),
                )

            self.output_content = Group(summary, percent_table, dollar_table)
        except Exception as e:
            self.output_content = f"[error]Error calculating performance: {e}[/]"

    
    def handle_command(self, command):
        # Route to active sub-module if one is open (q exits back to IBKR)
        if self.active_submodule is not None:
            cmd = command.lower().strip()
            if cmd == 'q':
                self.exit_submodule()
                return
            self.active_submodule.handle_command(command)
            return

        cmd = command.lower().strip()
        if cmd in ['q', 'quit']:
            # Local import to avoid circular dependency
            from home_module import HomeModule
            self.app.switch_module(HomeModule(self.app))
        elif cmd in ['qq', 'quit quit']:
            self.app.quit()
        elif cmd in ['h', 'help']:
            self.output_content = '''IBKR commands:\n
        - I   | import     > Import daily trades
        - I W | import w   > Import weekly trades
        - M   | mtm        > Get Mark-to-Market Values
        - MS  | mtm stock  > Get MTM Values (stocks only, skip options)
        - MV  | mtm verbose > Get MTM Values (verbose, print each symbol -> price)
        - PF  | performance > Year performance in $ and %
        - S   | stats      > Enter STATS sub-module (tables + plots)
        - SD  | stats day  > Daily PnL Stats
        - SW  | stats week > Weekly PnL Stats
        - LM  | list mtm    > List all positions (by MTM)
        - LV  | list value  > List all positions (by Value)
        - LS  | list symbol > List all positions (by Symbol)
        - LQ  | list qty    > List all positions (by Quantity)
        - LD  | list diff   > List all positions (by Diff)
        - LDR | list diff % > List all positions (by Diff %)
        - LT  | list target > List all positions (by Tgt S)
        - LC  | list call   > List all positions (by Call qty)
        - LP  | list put    > List all positions (by Put qty)
        - LZ  | list total  > List all positions (by Total Realized PnL)
        - LB  | list basket > List positions grouped by Basket
        - CSV | list csv    > Print positions as CSV (sorted by Symbol)
        - T   | trades     > List trades (last 7 days) [oo: opening options only]
        - TT  | trades all > List all trades [oo: opening options only]
        - CA  | calls assigned > List assigned call trades with assignment cost
        - R   | reload     > Reload trades from DB
        - P x | p <sym>    > List positions for a symbol
        - DEB | debug      > Debug (print trades_df)
        - H   | help       > Show this message
        - Q   | quit       > Return to main menu
        - QQ  | quit quit  > Exit the application'''
        elif cmd in ['m', 'mtm']:
            self.process_mtm_update()
        elif cmd in ['ms', 'mtm stock', 'mtm stocks']:
            self.process_mtm_update(skip_options=True)
        elif cmd in ['mv', 'mtm verbose']:
            self.process_mtm_update(verbose=True)
        elif cmd in ['s', 'stats']:
            from ibkr_stats_submodule import StatsSubModule
            self.enter_submodule(StatsSubModule(self))
        elif cmd in ['sd', 'stats day']:
            self.stats_daily()
        elif cmd in ['sw', 'stats week']:
            self.stats_weekly()
        elif cmd in ['pf', 'perf', 'performance']:
            self.show_performance()
        elif cmd in ['deb', 'debug']:
            self.debug()
        elif cmd in ['tt', 'trades all']:
            self.list_all_trades()
        elif cmd in ['tt oo', 'trades all oo']:
            self.list_all_trades(opening_options_only=True)
        elif cmd in ['t', 'trades']:
            self.list_all_trades(days=7)
        elif cmd in ['t oo', 'trades oo']:
            self.list_all_trades(days=7, opening_options_only=True)
        elif cmd in ['ca', 'calls assigned', 'assigned calls']:
            self.list_assigned_calls()
        elif cmd in ['r', 'reload']:
            self.load_trades()
            self.output_content = f"Trades reloaded. Total: {len(self.trades_df)}"
        elif cmd.startswith('p '):
            parts = command.split()
            if len(parts) >= 2:
                symbol = parts[1].upper()
                self.list_position(symbol)
            else:
                self.output_content = "[error]Usage: p <symbol>[/]"
        elif cmd in ['i', 'import']:
            self.import_trades(config.QUERY_ID_DAILY, "Daily")
        elif cmd in ['i w', 'import w', 'import weekly']:
            self.import_trades(config.QUERY_ID_WEEKLY, "Weekly")
        elif cmd in ['l', 'lm', 'list', 'list mtm']:
            self.list_all_positions(order_by='mtm', ascending=False)
        elif cmd in ['lv', 'list value']:
            self.list_all_positions(order_by='value', ascending=False)
        elif cmd in ['ls', 'list symbol']:
            self.list_all_positions(order_by='symbol', ascending=True)
        elif cmd in ['lq', 'list quantity']:
            self.list_all_positions(order_by='s_qty', ascending=False)
        elif cmd in ['ld', 'list diff']:
            self.list_all_positions(order_by='diff', ascending=True)
        elif cmd in ['ldr', 'list diff %', 'list diff pct']:
            self.list_all_positions(order_by='diff_pct', ascending=True)
        elif cmd in ['lt', 'list target']:
            self.list_all_positions(order_by='tgt_s', ascending=False)
        elif cmd in ['lc', 'list call']:
            self.list_all_positions(order_by='c_qty', ascending=True)
        elif cmd in ['lp', 'list put']:
            self.list_all_positions(order_by='p_qty', ascending=True)
        elif cmd in ['lz', 'list total']:
            self.list_all_positions(order_by='t_pnl', ascending=False)
        elif cmd in ['lb', 'list basket']:
            self.list_positions_by_basket()
        elif cmd in ['csp', 'cash secured put']:
            self.list_csp()
        elif cmd in ['csv', 'list csv']:
            self.list_positions_csv()
        elif cmd == 'e' or cmd == 'edit' or cmd.startswith('e ') or cmd.startswith('edit '):
            parts = command.split()
            if len(parts) >= 2:
                try:
                    idx = int(parts[1])
                    self.edit_trade(idx)
                except ValueError:
                    self.output_content = "[error]Usage: edit <index>[/]"
            elif self.current_symbol:
                self.edit_trade(1)
            else:
                self.output_content = "[error]Usage: edit <index>[/]"
        elif cmd == "":
            pass
        else:
            self.output_content = f"Unknown command: {command}\nType 'help' for valid commands."

    def import_trades(self, query_id, label):
        self.app.console.print(f"[info]Requesting {label} trades report...[/]")
        token = config.IBKR_TOKEN
        
        # Step 1: Send Request
        url_req = f"https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={token}&q={query_id}&v=3"
        try:
            resp = requests.get(url_req)
            resp.raise_for_status()
            
            # Use ElementTree.fromstring directly
            root = ET.fromstring(resp.content)
            
            # Check for Status
            status = root.find('Status')
            if status is not None and status.text == 'Success':
                ref_code = root.find('ReferenceCode').text
                base_url = root.find('Url').text
                self.app.console.print(f"[info]Report requested. Reference Code: {ref_code}. Waiting for generation...[/]")
            else:
                err_code = root.find('ErrorCode').text if root.find('ErrorCode') is not None else "Unknown"
                err_msg = root.find('ErrorMessage').text if root.find('ErrorMessage') is not None else "Unknown Error"
                self.output_content = f"[error]Error requesting report: {err_code} - {err_msg}[/]"
                return

            # Step 2: Get Statement
            # Retry loop
            url_dl = f"{base_url}?q={ref_code}&t={token}&v=3"
            print(url_dl)
            
            max_retries = 10
            for i in range(max_retries):
                time.sleep(2) # Wait a bit
                resp_dl = requests.get(url_dl)
                if resp_dl.status_code == 200:
                    # Check if it is actual XML content we want or still processing
                    if b'<FlexStatement' in resp_dl.content or b'<FlexQueryResponse' in resp_dl.content:
                        self.process_xml(resp_dl.content)
                        return
                    else:
                        self.app.console.print("[info]Waiting for report...[/]")
                else:
                    self.app.console.print(f"[info]Waiting for report... (Status: {resp_dl.status_code})[/]")
            
            self.output_content = "[error]Timeout waiting for report generation.[/]"

        except Exception as e:
            self.output_content = f"[error]Exception during import: {e}[/]"

    def process_xml(self, xml_content):
        try:
            root = ET.fromstring(xml_content)
            # Use iteration to be namespace agnostic and handle both Trade and TradeConfirm
            trades_list = [elem for elem in root.iter() if elem.tag.endswith('Trade') or elem.tag.endswith('TradeConfirm')]
            
            if not trades_list:
                self.output_content = "[info]No trades found in the report.[/]"
                return

            count_new = 0
            for trade in trades_list:
                data = trade.attrib # ElementTree attributes are a dictionary
                
                # Sanitize numeric fields
                safe_float = lambda k: float(data[k]) if data.get(k) and data[k].strip() else None
                
                # Map alternate field names if present (TradeConfirm vs Trade)
                trade_price = safe_float('tradePrice') if 'tradePrice' in data else safe_float('price')
                ib_commission = safe_float('ibCommission') if 'ibCommission' in data else safe_float('commission')
                
                open_close = data.get('openCloseIndicator')
                if open_close is None and 'code' in data:
                    c_val = data.get('code', '')
                    if 'O' in c_val: 
                        open_close = 'O'
                    elif 'C' in c_val: 
                        open_close = 'C'

                row = {
                    'tradeID': data.get('tradeID'),
                    'accountId': data.get('accountId'),
                    'underlyingSymbol': data.get('underlyingSymbol'),
                    'symbol': data.get('symbol'),
                    'description': data.get('description'),
                    'expiry': data.get('expiry'),
                    'putCall': data.get('putCall'),
                    'strike': safe_float('strike'),
                    'dateTime': data.get('dateTime'),
                    'quantity': safe_float('quantity'),
                    'tradePrice': trade_price,
                    'multiplier': safe_float('multiplier'),
                    'ibCommission': ib_commission,
                    'currency': data.get('currency'),
                    'notes': data.get('notes'),
                    'openCloseIndicator': open_close
                }
                
                if ibkr_db.save_trade(row):
                    count_new += 1
            
            
            self.output_content = f"Import complete. {count_new} new trades imported."
            self.load_trades()
            
        except Exception as e:
            self.output_content = f"[error]Error parsing XML or saving to DB: {e}[/]"

    def list_position(self, symbol):
        try:
            if self.trades_df.empty:
                df = pd.DataFrame()
            else:
                mask = (self.trades_df['symbol'] == symbol) | (self.trades_df['underlyingSymbol'] == symbol)
                # Sort by date ascending (oldest on top)
                df = self.trades_df[mask].copy()
                df['dateTime'] = pd.to_datetime(df['dateTime'], errors='coerce')
                df = df.sort_values(by='dateTime', ascending=False)

            if df.empty:
                self.output_content = f"[info]No trades found for {symbol}[/]"
                return

            # Partition DataFrames
            # stock_df: putCall is not 'C' or 'P'
            # options_df: putCall is 'C' or 'P'
            stock_df = df[~df['putCall'].isin(['C', 'P'])]
            options_df = df[df['putCall'].isin(['C', 'P'])]
            
            # Further partition options into open and closing trades
            open_options_df = options_df[options_df['openCloseIndicator'] == 'O']
            closing_options_df = options_df[options_df['openCloseIndicator'] == 'C']

            # Calculate Summaries (using original partitions for backward compatibility)
            call_df = df[df['putCall'] == 'C']
            put_df = df[df['putCall'] == 'P']
            
            stock_rem_qty_sum = stock_df['remaining_qty'].sum() if not stock_df.empty else 0.0
            call_rem_qty_sum = call_df['remaining_qty'].sum() if not call_df.empty else 0.0
            put_rem_qty_sum = put_df['remaining_qty'].sum() if not put_df.empty else 0.0

            stock_pnl_sum = stock_df['realized_pnl'].sum() if not stock_df.empty else 0.0
            call_pnl_sum = call_df['realized_pnl'].sum() if not call_df.empty else 0.0
            put_pnl_sum = put_df['realized_pnl'].sum() if not put_df.empty else 0.0

            # Book Price Calculation
            # sum(stock_df.credit) / sum(stock_df.remaining_qty)
            stock_credit_sum = stock_df['credit'].sum() if not stock_df.empty else 0.0
            
            if stock_rem_qty_sum != 0:
                book_price = stock_credit_sum / stock_rem_qty_sum
            else:
                book_price = 0.0

            # Portfolio-level MTM for MTM % and target shares calculation
            total_portfolio_mtm = self.trades_df['mtm_value'].sum() if 'mtm_value' in self.trades_df.columns else 0.0
            position_mtm = df['mtm_value'].sum() if 'mtm_value' in df.columns else 0.0
            mtm_pct = (position_mtm / total_portfolio_mtm * 100) if total_portfolio_mtm else 0.0
            target_pct = self.target_percent.get(symbol, 0.0)
            share_price = stock_df['mtm_price'].max() if not stock_df.empty else 0.0
            if target_pct and share_price:
                target_shares = round(total_portfolio_mtm * target_pct / 100 / share_price)
            else:
                target_shares = 0

            # Create Summary Table
            summary_table = Table(title=f"Position Summary: {symbol}", expand=False, row_styles=["", "on #1d2021"])
            summary_table.add_column("Symbol", style="bold yellow")
            summary_table.add_column("Book Price", justify="right")
            summary_table.add_column("Shares", justify="right", style="magenta")
            summary_table.add_column("Tgt Shares", justify="right", style="neutral_aqua")
            summary_table.add_column("MTM %", justify="right", style="neutral_blue")
            summary_table.add_column("Tgt %", justify="right", style="neutral_aqua")
            summary_table.add_column("Call Rem Qty", justify="right", style="magenta")
            summary_table.add_column("Put Rem Qty", justify="right", style="magenta")
            summary_table.add_column("Stk PnL", justify="right", style="bold red")
            summary_table.add_column("Call PnL", justify="right", style="bold red")
            summary_table.add_column("Put PnL", justify="right", style="bold red")

            summary_table.add_row(
                symbol,
                f"{book_price:.2f}",
                f"{stock_rem_qty_sum:.0f}",
                f"{target_shares:,}" if target_shares != 0 else "",
                f"{mtm_pct:.2f}%" if mtm_pct != 0 else "",
                f"{target_pct:.2f}%" if target_pct != 0 else "",
                f"{call_rem_qty_sum:.0f}",
                f"{put_rem_qty_sum:.0f}",
                f"{stock_pnl_sum:.2f}",
                f"{call_pnl_sum:.2f}",
                f"{put_pnl_sum:.2f}"
            )

            self.current_symbol = symbol
            self.position_map = {}
            row_idx = 1

            # ===== STOCK TRADES TABLE =====
            # Columns: #, Date, Desc, Qty, Price, Comm, O/C, Realized PnL, Remaining Qty, Credit
            # (removed: P/C, Delta, Und Price)
            def create_stock_table(title):
                tbl = Table(title=title, expand=True)
                tbl.add_column("#", justify="right", style="cyan")
                tbl.add_column("Date", style="cyan")
                tbl.add_column("Desc")
                tbl.add_column("Qty", justify="right", style="magenta")
                tbl.add_column("Price", justify="right", style="green")
                tbl.add_column("Comm", justify="right")
                tbl.add_column("O/C", justify="center")
                tbl.add_column("Realized PnL", justify="right")
                tbl.add_column("Remaining Qty", justify="right", style="blue")
                tbl.add_column("Credit", justify="right", style="blue")
                return tbl

            def add_stock_rows(tbl, data_df, apply_dim_style=False):
                nonlocal row_idx
                for _, row in data_df.iterrows():
                    date_str = row['dateTime'].strftime('%Y-%m-%d %H:%M') if pd.notnull(row['dateTime']) else ""
                    self.position_map[row_idx] = row['tradeID']
                    rem_qty = row.get('remaining_qty', 0.0)
                    row_style = "dim italic" if apply_dim_style and rem_qty == 0 else None
                    
                    realized_pnl = row.get('realized_pnl', 0.0)
                    if realized_pnl > 0:
                        pnl_str = f"[neutral_blue]{realized_pnl:.2f}[/neutral_blue]"
                    elif realized_pnl < 0:
                        pnl_str = f"[bright_red]{realized_pnl:.2f}[/bright_red]"
                    else:
                        pnl_str = ""

                    tbl.add_row(
                        str(row_idx),
                        date_str,
                        str(row['description']),
                        f"{row['quantity']:.0f}" if pd.notnull(row['quantity']) else "",
                        f"{row['tradePrice']:.2f}" if pd.notnull(row['tradePrice']) else "",
                        f"{row['ibCommission']:.2f}" if pd.notnull(row['ibCommission']) else "",
                        str(row['openCloseIndicator']),
                        pnl_str,
                        f"{rem_qty:.0f}" if rem_qty != 0 else "",
                        f"{row.get('credit', 0.0):.2f}" if row.get('credit', 0) != 0 else "",
                        style=row_style
                    )
                    row_idx += 1

            # ===== CLOSING OPTIONS TABLE =====
            # Columns: #, Date, Desc, Qty, Price, Comm, Realized PnL
            # (removed: P/C, O/C, Rem Qty, Credit, Delta, Und Price)
            def create_closing_options_table(title):
                tbl = Table(title=title, expand=True)
                tbl.add_column("#", justify="right", style="cyan")
                tbl.add_column("Date", style="cyan")
                tbl.add_column("Desc")
                tbl.add_column("Qty", justify="right", style="magenta")
                tbl.add_column("Price", justify="right", style="green")
                tbl.add_column("Comm", justify="right")
                tbl.add_column("Realized PnL", justify="right")
                tbl.add_column("DTE", justify="right", style="neutral_aqua")
                tbl.add_column("DIT", justify="right", style="neutral_aqua")
                return tbl

            def add_closing_options_rows(tbl, data_df):
                nonlocal row_idx
                for _, row in data_df.iterrows():
                    date_str = row['dateTime'].strftime('%Y-%m-%d %H:%M') if pd.notnull(row['dateTime']) else ""
                    self.position_map[row_idx] = row['tradeID']

                    realized_pnl = row.get('realized_pnl', 0.0)
                    if realized_pnl > 0:
                        pnl_str = f"[neutral_blue]{realized_pnl:.2f}[/neutral_blue]"
                    elif realized_pnl < 0:
                        pnl_str = f"[bright_red]{realized_pnl:.2f}[/bright_red]"
                    else:
                        pnl_str = ""

                    dte = row.get('dte')
                    dit = row.get('dit')

                    tbl.add_row(
                        str(row_idx),
                        date_str,
                        str(row['description']),
                        f"{row['quantity']:.0f}" if pd.notnull(row['quantity']) else "",
                        f"{row['tradePrice']:.2f}" if pd.notnull(row['tradePrice']) else "",
                        f"{row['ibCommission']:.2f}" if pd.notnull(row['ibCommission']) else "",
                        pnl_str,
                        f"{int(dte)}" if pd.notnull(dte) else "",
                        f"{int(dit)}" if pd.notnull(dit) else "",
                    )
                    row_idx += 1

            # ===== OPEN OPTIONS TABLE =====
            # Columns: #, Date, Desc, Qty, Price, Comm, Remaining Qty, Credit, Delta, Und Price
            # (removed: P/C, O/C, Realized PnL)
            def create_open_options_table(title):
                tbl = Table(title=title, expand=True)
                tbl.add_column("#", justify="right", style="cyan")
                tbl.add_column("Date", style="cyan")
                tbl.add_column("Desc")
                tbl.add_column("Qty", justify="right", style="magenta")
                tbl.add_column("Price", justify="right", style="green")
                tbl.add_column("Comm", justify="right")
                tbl.add_column("Remaining Qty", justify="right", style="blue")
                tbl.add_column("Credit", justify="right", style="blue")
                tbl.add_column("DTE", justify="right", style="neutral_aqua")
                tbl.add_column("Delta", justify="right", style="yellow")
                tbl.add_column("Und Price", justify="right", style="yellow")
                return tbl

            def add_open_options_rows(tbl, data_df, apply_dim_style=False):
                nonlocal row_idx
                for _, row in data_df.iterrows():
                    date_str = row['dateTime'].strftime('%Y-%m-%d %H:%M') if pd.notnull(row['dateTime']) else ""
                    self.position_map[row_idx] = row['tradeID']
                    rem_qty = row.get('remaining_qty', 0.0)
                    row_style = "dim italic" if apply_dim_style and rem_qty == 0 else None
                    dte = row.get('dte')

                    tbl.add_row(
                        str(row_idx),
                        date_str,
                        str(row['description']),
                        f"{row['quantity']:.0f}" if pd.notnull(row['quantity']) else "",
                        f"{row['tradePrice']:.2f}" if pd.notnull(row['tradePrice']) else "",
                        f"{row['ibCommission']:.2f}" if pd.notnull(row['ibCommission']) else "",
                        f"{rem_qty:.0f}" if rem_qty != 0 else "",
                        f"{row.get('credit', 0.0):.2f}" if row.get('credit', 0) != 0 else "",
                        f"{int(dte)}" if pd.notnull(dte) else "",
                        f"{row.get('delta', 0.0):.4f}" if pd.notnull(row.get('delta')) else "",
                        f"{row.get('und_price', 0.0):.2f}" if pd.notnull(row.get('und_price')) else "",
                        style=row_style
                    )
                    row_idx += 1

            # Build the tables list
            tables = [summary_table]

            # Table 1: Open Options Trades (P/C with O/C = 'O')
            if not open_options_df.empty:
                open_options_table = create_open_options_table(f"Open Options: {symbol}")
                add_open_options_rows(open_options_table, open_options_df, apply_dim_style=True)
                tables.append(open_options_table)

            # Table 2: Closing Options Trades (P/C with O/C = 'C')
            if not closing_options_df.empty:
                closing_options_table = create_closing_options_table(f"Closing Options: {symbol}")
                add_closing_options_rows(closing_options_table, closing_options_df)
                tables.append(closing_options_table)

            # Table 3: Stock Trades (not P/C)
            if not stock_df.empty:
                stock_table = create_stock_table(f"Stock Trades: {symbol}")
                add_stock_rows(stock_table, stock_df, apply_dim_style=True)
                tables.append(stock_table)
            
            self.output_content = Group(*tables)
        except Exception as e:
            self.output_content = f"[error]Error listing positions: {e}[/]"

    def edit_trade(self, idx):
        if idx not in self.position_map:
            self.output_content = f"[error]Invalid trade index: {idx}[/]"
            return

        trade_id = self.position_map[idx]
        
        # We need to find the current values to show (optional, but good UX)
        # But we can just ask for new values.
        
        self.app.console.print(f"[info]Editing trade #{idx} (ID: {trade_id})[/]")

        description = ""
        if not self.trades_df.empty:
            row = self.trades_df[self.trades_df['tradeID'] == trade_id]
            if not row.empty:
                description = str(row.iloc[0].get('description', '') or '')

        delta_label = f"{description} Delta" if description else "Delta"

        try:
            delta_str = self.app.console.input(f"[prompt]{delta_label}: [/]")
            und_price_str = self.app.console.input("[prompt]Price: [/]")

            updates = {}
            delta_str = delta_str.strip()
            if delta_str:
                if '.' in delta_str:
                    updates['delta'] = float(delta_str)
                else:
                    sign = -1 if delta_str.startswith('-') else 1
                    digits = delta_str.lstrip('+-')
                    if digits.isdigit() and digits:
                        updates['delta'] = sign * int(digits) / (10 ** len(digits))
                    else:
                        updates['delta'] = float(delta_str)
            if und_price_str.strip():
                updates['und_price'] = float(und_price_str)
                
            if updates:
                if ibkr_db.update_trade_fields(trade_id, updates):
                    self.app.console.print("[info]Trade updated successfully.[/]")
                    self.load_trades() # Reload DF
                    if self.current_symbol:
                        self.list_position(self.current_symbol) # Refresh view
                    else:
                        self.output_content = "Trade updated."
                else:
                    self.output_content = "[error]Failed to update trade.[/]"
            else:
                 self.output_content = "[info]No changes made.[/]"

        except ValueError:
            self.output_content = "[error]Invalid input (expected float).[/]"
        except Exception as e:
            self.output_content = f"[error]Error updating trade: {e}[/]"

    def debug(self):
        # Direct print to allow terminal scrolling
        self.app.console.clear()
        groups = self.trades_df.groupby('underlyingSymbol')
        for name, group in groups:
            print(name)
            print(group)
            print("\n")
        print("-----------\n")
        print(self.trades_df.to_string())
        # self.app.console.print(self.trades_df.to_string())
        
        # Skip the next render cycle in main loop to prevent clearing the screen
        self.app.skip_render = True

    def list_all_trades(self, days=None, opening_options_only=False):
        try:
            if self.trades_df.empty:
                self.output_content = "[info]No trades loaded.[/]"
                return

            df = self.trades_df
            if days is not None:
                dt = pd.to_datetime(df['dateTime'], errors='coerce')
                cutoff = pd.Timestamp.now(tz=dt.dt.tz) - pd.Timedelta(days=days) if dt.dt.tz is not None else pd.Timestamp.now() - pd.Timedelta(days=days)
                df = df[dt >= cutoff]
                title = f"Trades (last {days} days)"
            else:
                title = "All Trades"

            if opening_options_only:
                df = df[df['putCall'].isin(['C', 'P']) & (df['openCloseIndicator'] == 'O')]
                title = f"{title} (opening options only)"

            if df.empty:
                if opening_options_only:
                    self.output_content = "[info]No opening option trades found.[/]"
                else:
                    self.output_content = f"[info]No trades in the last {days} days.[/]"
                return

            table = Table(title=title, expand=True)
            table.add_column("Date", style="cyan")
            table.add_column("Symbol", style="bold yellow")
            table.add_column("Desc")
            table.add_column("Qty", justify="right", style="magenta")
            table.add_column("Price", justify="right", style="green")
            table.add_column("Comm", justify="right")
            table.add_column("O/C", justify="center")
            table.add_column("PnL", justify="right", style="bold red")
            table.add_column("Rem Qty", justify="right", style="blue")
            table.add_column("DTE", justify="right", style="neutral_aqua")
            table.add_column("DIT", justify="right", style="neutral_aqua")
            table.add_column("Delta", justify="right", style="yellow")
            table.add_column("Und Price", justify="right", style="yellow")

            for _, row in df.iterrows():
                pnl = row.get('realized_pnl', 0.0)
                rem_qty = row.get('remaining_qty', 0.0)
                dte = row.get('dte')
                dit = row.get('dit')

                table.add_row(
                    pd.to_datetime(row['dateTime']).strftime('%Y-%m-%d %H:%M') if pd.notnull(row['dateTime']) else "",
                    str(row['symbol']),
                    str(row['description']),
                    f"{row['quantity']:.0f}" if pd.notnull(row['quantity']) else "",
                    f"{row['tradePrice']:.2f}" if pd.notnull(row['tradePrice']) else "",
                    f"{row['ibCommission']:.2f}" if pd.notnull(row['ibCommission']) else "",
                    str(row['openCloseIndicator']),
                    f"{pnl:.2f}" if pnl != 0 else "",
                    f"{rem_qty:.0f}" if rem_qty != 0 else "",
                    f"{int(dte)}" if pd.notnull(dte) else "",
                    f"{int(dit)}" if pd.notnull(dit) else "",
                    f"{row.get('delta', 0.0):.4f}" if pd.notnull(row.get('delta')) else "",
                    f"{row.get('und_price', 0.0):.2f}" if pd.notnull(row.get('und_price')) else ""
                )

            # Direct print to allow terminal scrolling
            self.app.console.clear()
            self.app.console.print(table)
            
            # Skip the next render cycle in main loop to prevent clearing the screen
            self.app.skip_render = True

            # We do NOT set output_content here because it won't be displayed
            # (since render is skipped and the loop goes straight to input)
        except Exception as e:
            self.output_content = f"[error]Error listing trades: {e}[/]"

    def list_assigned_calls(self):
        try:
            if self.trades_df.empty:
                self.output_content = "[info]No trades loaded.[/]"
                return

            df = self.trades_df.copy()
            notes_str = df['notes'].fillna('').astype(str).str.strip()
            mask = (df['putCall'] == 'C') & (notes_str == 'A')
            assigned = df[mask].copy()

            if assigned.empty:
                self.output_content = "[info]No assigned call trades found.[/]"
                return

            assigned['dateTime'] = pd.to_datetime(assigned['dateTime'], errors='coerce').dt.tz_localize(None)
            assigned = assigned.sort_values('dateTime', ascending=False)

            # Fetch Friday's closing prices for each underlying on each assignment date.
            close_lookup = {}
            symbols = sorted({s for s in assigned['underlyingSymbol'].dropna().unique() if s})
            if symbols:
                try:
                    from yahooquery import Ticker
                    min_d = assigned['dateTime'].min().normalize()
                    max_d = assigned['dateTime'].max().normalize() + pd.Timedelta(days=1)
                    ticker = Ticker(symbols, asynchronous=True)
                    hist = ticker.history(start=min_d.strftime('%Y-%m-%d'), end=max_d.strftime('%Y-%m-%d'))
                    if isinstance(hist, pd.DataFrame) and not hist.empty:
                        for idx, row in hist.iterrows():
                            sym, dt = idx if isinstance(idx, tuple) else (symbols[0], idx)
                            date_str = pd.Timestamp(dt).strftime('%Y-%m-%d')
                            close_val = row.get('close')
                            if close_val is not None and pd.notnull(close_val):
                                close_lookup[(sym, date_str)] = float(close_val)
                except Exception as e:
                    self.app.console.print(f"[error]Yahoo history fetch failed: {e}[/]")

            table = Table(title="Assigned Call Trades", expand=True)
            table.add_column("Date", style="cyan")
            table.add_column("Symbol", style="bold yellow")
            table.add_column("Desc")
            table.add_column("Qty", justify="right", style="magenta")
            table.add_column("Price", justify="right", style="green")
            table.add_column("Comm", justify="right")
            table.add_column("O/C", justify="center")
            table.add_column("PnL", justify="right", style="bold red")
            table.add_column("Rem Qty", justify="right", style="blue")
            table.add_column("Delta", justify="right", style="yellow")
            table.add_column("Und Price", justify="right", style="yellow")
            table.add_column("Strike", justify="right")
            table.add_column("Fri Close", justify="right")
            table.add_column("Premium/Sh", justify="right")
            table.add_column("Assignment Cost", justify="right", style="bold")

            total_cost = 0.0
            total_known = False

            for _, row in assigned.iterrows():
                qty = float(row['quantity']) if pd.notnull(row['quantity']) else 0.0
                multiplier = float(row['multiplier']) if pd.notnull(row['multiplier']) else 100.0
                strike = float(row['strike']) if pd.notnull(row['strike']) else 0.0
                trade_price = float(row['tradePrice']) if pd.notnull(row['tradePrice']) else 0.0
                realized_pnl = float(row.get('realized_pnl', 0.0) or 0.0)
                rem_qty = float(row.get('remaining_qty', 0.0) or 0.0)

                shares = abs(qty) * multiplier
                premium_per_share = (realized_pnl / shares + trade_price) if shares else 0.0

                und_sym = row.get('underlyingSymbol')
                date_str = row['dateTime'].strftime('%Y-%m-%d') if pd.notnull(row['dateTime']) else ""
                fri_close = close_lookup.get((und_sym, date_str))

                if fri_close is not None and shares and strike:
                    assignment_cost = (fri_close - strike - premium_per_share) * shares
                    total_cost += assignment_cost
                    total_known = True
                    if assignment_cost > 0:
                        cost_str = f"[bright_red]{assignment_cost:,.2f}[/bright_red]"
                    elif assignment_cost < 0:
                        cost_str = f"[neutral_blue]{assignment_cost:,.2f}[/neutral_blue]"
                    else:
                        cost_str = f"{assignment_cost:,.2f}"
                    fri_close_str = f"{fri_close:.2f}"
                else:
                    cost_str = "[dim]N/A[/dim]"
                    fri_close_str = "[dim]N/A[/dim]"

                table.add_row(
                    row['dateTime'].strftime('%Y-%m-%d %H:%M') if pd.notnull(row['dateTime']) else "",
                    str(row['symbol']),
                    str(row['description']),
                    f"{qty:.0f}",
                    f"{trade_price:.2f}",
                    f"{row['ibCommission']:.2f}" if pd.notnull(row['ibCommission']) else "",
                    str(row['openCloseIndicator']),
                    f"{realized_pnl:.2f}" if realized_pnl != 0 else "",
                    f"{rem_qty:.0f}" if rem_qty != 0 else "",
                    f"{row.get('delta', 0.0):.4f}" if pd.notnull(row.get('delta')) else "",
                    f"{row.get('und_price', 0.0):.2f}" if pd.notnull(row.get('und_price')) else "",
                    f"{strike:.2f}",
                    fri_close_str,
                    f"{premium_per_share:.2f}",
                    cost_str,
                )

            if total_known:
                table.add_section()
                if total_cost > 0:
                    total_str = f"[bright_red]{total_cost:,.2f}[/bright_red]"
                elif total_cost < 0:
                    total_str = f"[neutral_blue]{total_cost:,.2f}[/neutral_blue]"
                else:
                    total_str = f"{total_cost:,.2f}"
                table.add_row("TOTAL", "", "", "", "", "", "", "", "", "", "", "", "", "", total_str, style="bold")

            self.app.console.clear()
            self.app.console.print(table)
            self.app.skip_render = True

        except Exception as e:
            self.output_content = f"[error]Error listing assigned calls: {e}[/]"

    def stats_daily(self):
        try:
            if self.trades_df.empty:
                self.output_content = "[info]No trades to analyze.[/]"
                return

            # Create a working copy
            df = self.trades_df.copy()
            df['dateTime'] = pd.to_datetime(df['dateTime']).dt.tz_localize(None)
            
            # Extract date (normalize to midnight)
            df['date_only'] = df['dateTime'].dt.normalize()

            # Group by date and sum PnL
            daily_stats = df.groupby('date_only')['realized_pnl'].sum()

            if daily_stats.empty:
                 self.output_content = "[info]No realized PnL found.[/]"
                 return

            # Create full date range starting from Monday January 5, 2026
            start_date = pd.Timestamp('2026-01-05')
            max_date = daily_stats.index.max()
            min_date = max(start_date, daily_stats.index.min()) if daily_stats.index.min() > start_date else start_date
            
            # Generate all calendar days to check for weekends with trades
            all_days = pd.date_range(start=min_date, end=max_date, freq='D')
            
            # Reindex to include all days, filling missing with 0
            daily_stats = daily_stats.reindex(all_days, fill_value=0.0)

            # Filter: Keep if Weekday (Mon=0, Sun=6) < 5 OR PnL != 0
            # This keeps all Mon-Fri (even if 0) and any Sat/Sun with non-zero PnL
            mask = (daily_stats.index.dayofweek < 5) | (daily_stats != 0)
            daily_stats = daily_stats[mask]

            # Prepare table
            table = Table(title="Daily Stats (PnL)", expand=False)
            table.add_column("Date", style="cyan")
            table.add_column("Day", style="yellow")
            table.add_column("Realized PnL", justify="right")

            total_pnl = 0.0
            weekday_count = 0

            for date, pnl in daily_stats.items():
                total_pnl += pnl
                if date.dayofweek < 5:
                    weekday_count += 1
                day_name = date.strftime("%A")
                date_str = date.strftime("%Y-%m-%d")
                
                style = "blue" if pnl > 0 else "orange1" if pnl < 0 else "dim"
                pnl_str = f"{pnl:,.2f}" if pnl != 0 else "-"
                
                table.add_row(date_str, day_name, f"[{style}]{pnl_str}[/{style}]")

            table.add_section()
            # Average row (over weekdays only)
            avg_pnl = total_pnl / weekday_count if weekday_count > 0 else 0.0
            avg_style = "blue" if avg_pnl > 0 else "orange1" if avg_pnl < 0 else "white"
            table.add_row("AVERAGE", "", f"[{avg_style}]{avg_pnl:,.2f}[/{avg_style}]")
            # Total row
            style = "bold blue" if total_pnl > 0 else "bold orange1" if total_pnl < 0 else "white"
            table.add_row("TOTAL", "", f"[{style}]{total_pnl:,.2f}[/{style}]", style="bold")

            self.output_content = table
        except Exception as e:
            self.output_content = f"[error]Error calculating stats: {e}[/]"

    def stats_weekly(self):
        try:
            if self.trades_df.empty:
                 self.output_content = "[info]No trades to analyze.[/]"
                 return

            # Create working copy
            df = self.trades_df.copy()
            df['dateTime'] = pd.to_datetime(df['dateTime']).dt.tz_localize(None)
            
            # Set index for resampling
            df.set_index('dateTime', inplace=True)
            
            # Resample by Week Ending Friday (W-FRI)
            weekly_stats = df['realized_pnl'].resample('W-FRI').sum()

            if weekly_stats.empty:
                self.output_content = "[info]No realized PnL found.[/]"
                return
            
            # Filter to start from the week of January 5, 2026
            # The first W-FRI bin ending on or after Jan 5 is Jan 9, 2026 (Friday)
            start_week = pd.Timestamp('2026-01-09')
            weekly_stats = weekly_stats[weekly_stats.index >= start_week]
            
            # Fill any missing weeks in the range with 0
            if not weekly_stats.empty:
                full_weeks = pd.date_range(start=weekly_stats.index.min(), end=weekly_stats.index.max(), freq='W-FRI')
                weekly_stats = weekly_stats.reindex(full_weeks, fill_value=0.0)
            
            # Prepare table
            table = Table(title="Weekly Stats (PnL - Ending Friday)", expand=False)
            table.add_column("Week Ending", style="cyan")
            table.add_column("Realized PnL", justify="right")
            
            total_pnl = 0.0
            week_count = 0
            
            for date, pnl in weekly_stats.items():
                total_pnl += pnl
                week_count += 1
                date_str = date.strftime("%Y-%m-%d")
                
                # Highlight if non-zero
                style = "bold blue" if pnl > 0 else "bold orange1" if pnl < 0 else "dim"
                pnl_str = f"{pnl:,.2f}" if pnl != 0 else "-"
                
                table.add_row(date_str, f"[{style}]{pnl_str}[/{style}]")
                
            table.add_section()
            # Average row
            avg_pnl = total_pnl / week_count if week_count > 0 else 0.0
            avg_style = "blue" if avg_pnl > 0 else "orange1" if avg_pnl < 0 else "white"
            table.add_row("AVERAGE", f"[{avg_style}]{avg_pnl:,.2f}[/{avg_style}]")
            # Total row
            style = "bold blue" if total_pnl > 0 else "bold orange1" if total_pnl < 0 else "white"
            table.add_row("TOTAL", f"[{style}]{total_pnl:,.2f}[/{style}]", style="bold")
            
            self.output_content = table

        except Exception as e:
            self.output_content = f"[error]Error calculating weekly stats: {e}[/]"

    def _fmt_diff(self, diff):
        """Format the Diff column value with color based on thresholds."""
        if diff == 0:
            return ""
        if diff > 1.5:
            color = "bright_aqua"
        elif diff > 1.0:
            color = "neutral_aqua"
        elif diff > 0.5:
            color = "faded_aqua"
        elif diff < -1.5:
            color = "bright_orange"
        elif diff < -1.0:
            color = "neutral_orange"
        elif diff < -0.5:
            color = "faded_orange"
        else:
            color = "dark4"
        return f"[{color}]{diff:.2f}[/{color}]"

    def _fmt_diff_pct(self, mtm_pct, target_pct):
        """Format the Diff % column (MTM% / TGT%) with color based on thresholds."""
        if target_pct == 0 or mtm_pct == 0:
            return ""
        ratio = mtm_pct / target_pct
        if ratio > 1.5:
            color = "bright_aqua"
        elif ratio > 1.25:
            color = "neutral_aqua"
        elif ratio > 1.1:
            color = "faded_aqua"
        elif ratio < 0.5:
            color = "bright_orange"
        elif ratio < 0.75:
            color = "neutral_orange"
        elif ratio < 0.9:
            color = "faded_orange"
        else:
            color = "dark4"
        return f"[{color}]{round(ratio * 100)}[/{color}]"

    def list_all_positions(self, order_by='mtm', ascending=False):
        try:
            if self.trades_df.empty:
                self.output_content = "[info]No trades loaded.[/]"
                return

            # Group by underlyingSymbol
            # We assume underlyingSymbol is present. If NaN, it might be skipped.
            # Usually IBKR report provides it.
            groups = self.trades_df.groupby('underlyingSymbol')
            
            def _hdr(label, ch):
                idx = label.lower().find(ch.lower())
                if idx < 0:
                    return f"[bold underline]{ch}[/] {label}"
                return f"{label[:idx]}[bold underline]{label[idx]}[/]{label[idx+1:]}"

            is_lz = order_by == 't_pnl'
            is_lq = order_by == 's_qty'

            table = Table(title="All Positions", expand=False, row_styles=["", "on #1d2021"])
            table.add_column(_hdr("Symbol", "s"), style="neutral_yellow")
            if is_lz:
                table.add_column(_hdr("MTM Value", "m"), justify="right", style="neutral_blue")
                table.add_column("MTM %", justify="right", style="neutral_blue")
                table.add_column("S Unr PnL", justify="right")
                table.add_column("C Unr PnL", justify="right")
                table.add_column("P Unr PnL", justify="right")
                table.add_column("T Unr PnL", justify="right")
                table.add_column("S Rlzd PnL", justify="right")
                table.add_column("C Rlzd PnL", justify="right")
                table.add_column("P Rlzd PnL", justify="right")
                table.add_column(_hdr("T Rlzd PnL", "z"), justify="right")
            elif is_lq:
                table.add_column(_hdr("Tgt Q", "t"), justify="right", style="neutral_aqua")
                table.add_column(_hdr("Qty", "q"), justify="right", style="neutral_purple")
                table.add_column(_hdr("Call", "c"), justify="right", style="neutral_purple")
                table.add_column(_hdr("Put", "p"), justify="right", style="neutral_purple")
                table.add_column("Tgt %", justify="right", style="neutral_aqua")
                table.add_column(_hdr("Diff", "d"), justify="right", style="light4")
                table.add_column("Diff %", justify="right", style="light4")
                table.add_column("Book Price", justify="right", style="dark4")
                table.add_column(_hdr("Book Value", "v"), justify="right", style="neutral_yellow")
                table.add_column(_hdr("MTM Value", "m"), justify="right", style="neutral_blue")
                table.add_column("MTM %", justify="right", style="neutral_blue")
                table.add_column("S Unr PnL", justify="right")
                table.add_column("C Unr PnL", justify="right")
                table.add_column("P Unr PnL", justify="right")
                table.add_column("T Unr PnL", justify="right")
            else:
                table.add_column("Book Price", justify="right", style="dark4")
                table.add_column(_hdr("Book Value", "v"), justify="right", style="neutral_yellow")
                table.add_column(_hdr("MTM Value", "m"), justify="right", style="neutral_blue")
                table.add_column("MTM %", justify="right", style="neutral_blue")
                table.add_column("Tgt %", justify="right", style="neutral_aqua")
                table.add_column(_hdr("Diff", "d"), justify="right", style="light4")
                table.add_column("Diff %", justify="right", style="light4")
                table.add_column("S Unr PnL", justify="right")
                table.add_column("C Unr PnL", justify="right")
                table.add_column("P Unr PnL", justify="right")
                table.add_column("T Unr PnL", justify="right")
                table.add_column(_hdr("Tgt Q", "t"), justify="right", style="neutral_aqua")
                table.add_column(_hdr("Qty", "q"), justify="right", style="neutral_purple")
                table.add_column(_hdr("Call", "c"), justify="right", style="neutral_purple")
                table.add_column(_hdr("Put", "p"), justify="right", style="neutral_purple")

            data_rows = []

            for symbol, group in groups:
                 # Partition DataFrames
                 stock_df = group[~group['putCall'].isin(['C', 'P'])]
                 call_df = group[group['putCall'] == 'C']
                 put_df = group[group['putCall'] == 'P']

                 stock_credit_sum = stock_df['credit'].sum() if not stock_df.empty else 0.0
                 stock_rem_qty_sum = stock_df['remaining_qty'].sum() if not stock_df.empty else 0.0
                 book_price = (stock_credit_sum / stock_rem_qty_sum) if stock_rem_qty_sum else 0.0
                 value = stock_credit_sum * -1
                 # MTM Value / MTM % consider shares only (ignore calls and puts)
                 mtm = stock_df['mtm_value'].sum()
                 
                 # Get share price for target shares calculation
                 share_price = stock_df['mtm_price'].max() if not stock_df.empty else 0.0
                 s_unrlzd = stock_df['unrealized_pnl'].sum()
                 c_unrlzd = call_df['unrealized_pnl'].sum()
                 p_unrlzd = put_df['unrealized_pnl'].sum()
                 unrlzd_pnl = s_unrlzd + c_unrlzd + p_unrlzd

                 s_qty = stock_df['remaining_qty'].sum()
                 c_qty = call_df['remaining_qty'].sum()
                 p_qty = put_df['remaining_qty'].sum()
                 
                 s_pnl = stock_df['realized_pnl'].sum()
                 c_pnl = call_df['realized_pnl'].sum()
                 p_pnl = put_df['realized_pnl'].sum()
                 
                 # Only add row if there is something interesting
                 if any(x != 0 for x in [value, mtm, s_qty, c_qty, p_qty, s_pnl, c_pnl, p_pnl]):
                     data_rows.append({
                        'symbol': symbol,
                        'book_price': book_price,
                        'value': value,
                        'mtm': mtm,
                        's_unrlzd': s_unrlzd,
                        'c_unrlzd': c_unrlzd,
                        'p_unrlzd': p_unrlzd,
                        'unrlzd_pnl': unrlzd_pnl,
                        's_qty': s_qty,
                        'c_qty': c_qty,
                        'p_qty': p_qty,
                        's_pnl': s_pnl,
                        'c_pnl': c_pnl,
                        'p_pnl': p_pnl,
                        'target_pct': self.target_percent.get(symbol, 0.0),
                        'share_price': share_price
                     })

            # Sort
            if order_by == 'value':
                data_rows.sort(key=lambda x: x['value'], reverse=not ascending)
            elif order_by == 'mtm':
                data_rows.sort(key=lambda x: x['mtm'], reverse=not ascending)
            elif order_by == 'symbol':
                data_rows.sort(key=lambda x: x['symbol'], reverse=not ascending)
            elif order_by == 's_qty':
                data_rows.sort(key=lambda x: x['s_qty'], reverse=not ascending)
            elif order_by == 'c_qty':
                data_rows.sort(key=lambda x: (x['c_qty'], x['p_qty']), reverse=not ascending)
            elif order_by == 'p_qty':
                data_rows.sort(key=lambda x: (x['p_qty'], x['c_qty']), reverse=not ascending)
            elif order_by == 't_pnl':
                data_rows.sort(key=lambda x: x['s_pnl'] + x['c_pnl'] + x['p_pnl'], reverse=not ascending)


            # Calculate totals
            total_value = sum(row['value'] for row in data_rows)
            total_mtm = sum(row['mtm'] for row in data_rows)
            total_s_unrlzd = sum(row['s_unrlzd'] for row in data_rows)
            total_c_unrlzd = sum(row['c_unrlzd'] for row in data_rows)
            total_p_unrlzd = sum(row['p_unrlzd'] for row in data_rows)
            total_unrlzd_pnl = sum(row['unrlzd_pnl'] for row in data_rows)
            total_s_qty = sum(row['s_qty'] for row in data_rows)
            total_c_qty = sum(row['c_qty'] for row in data_rows)
            total_p_qty = sum(row['p_qty'] for row in data_rows)
            total_s_pnl = sum(row['s_pnl'] for row in data_rows)
            total_c_pnl = sum(row['c_pnl'] for row in data_rows)
            total_p_pnl = sum(row['p_pnl'] for row in data_rows)
            total_target_pct = sum(row['target_pct'] for row in data_rows)

            # Sort by diff (needs total_mtm, so done after totals)
            if order_by == 'diff':
                data_rows.sort(key=lambda x: (x['mtm'] / total_mtm * 100 if total_mtm != 0 and x['mtm'] != 0 else 0) - x['target_pct'], reverse=not ascending)
            elif order_by == 'diff_pct':
                def _diff_pct(x):
                    mtm_pct = x['mtm'] / total_mtm * 100 if total_mtm != 0 and x['mtm'] != 0 else 0
                    if x['target_pct'] == 0 or mtm_pct == 0:
                        return float('inf') if ascending else float('-inf')
                    return mtm_pct / x['target_pct']
                data_rows.sort(key=_diff_pct, reverse=not ascending)
            elif order_by == 'tgt_s':
                def _tgt_s(x):
                    if x['target_pct'] and x['share_price']:
                        return round(total_mtm * x['target_pct'] / 100 / x['share_price'])
                    return 0
                data_rows.sort(key=_tgt_s, reverse=not ascending)

            def fmt_pnl(val):
                if val == 0: return ""
                if val > 0: return f"[neutral_blue]{val:,.2f}[/neutral_blue]"
                return f"[bright_red]{val:,.2f}[/bright_red]"

            for row in data_rows:
                mtm_pct = row['mtm'] / total_mtm * 100 if total_mtm != 0 and row['mtm'] != 0 else 0
                target_pct = row['target_pct']
                share_price = row['share_price']
                
                # Target Shares = (total_mtm * target_pct / 100) / share_price
                if target_pct != 0 and share_price != 0:
                    tgt_shares = round(total_mtm * target_pct / 100 / share_price)
                else:
                    tgt_shares = 0
                
                mtm_pct_str = f"{mtm_pct:.2f}%" if mtm_pct != 0 else ""
                
                t_pnl = row['s_pnl'] + row['c_pnl'] + row['p_pnl']
                if is_lz:
                    table.add_row(
                        str(row['symbol']),
                        f"{row['mtm']:,.2f}" if row['mtm'] != 0 else "",
                        mtm_pct_str,
                        fmt_pnl(row['s_unrlzd']),
                        fmt_pnl(row['c_unrlzd']),
                        fmt_pnl(row['p_unrlzd']),
                        fmt_pnl(row['unrlzd_pnl']),
                        fmt_pnl(row['s_pnl']),
                        fmt_pnl(row['c_pnl']),
                        fmt_pnl(row['p_pnl']),
                        fmt_pnl(t_pnl)
                    )
                elif is_lq:
                    table.add_row(
                        str(row['symbol']),
                        f"{tgt_shares:,}" if tgt_shares != 0 else "",
                        f"{row['s_qty']:.0f}" if row['s_qty'] != 0 else "",
                        f"{row['c_qty']:.0f}" if row['c_qty'] != 0 else "",
                        f"{row['p_qty']:.0f}" if row['p_qty'] != 0 else "",
                        f"{row['target_pct']:.2f}%" if row['target_pct'] != 0 else "",
                        self._fmt_diff(mtm_pct - target_pct),
                        self._fmt_diff_pct(mtm_pct, target_pct),
                        f"{row['book_price'] * -1:.2f}" if row['book_price'] != 0 else "",
                        f"{row['value']:,.2f}" if row['value'] != 0 else "",
                        f"{row['mtm']:,.2f}" if row['mtm'] != 0 else "",
                        mtm_pct_str,
                        fmt_pnl(row['s_unrlzd']),
                        fmt_pnl(row['c_unrlzd']),
                        fmt_pnl(row['p_unrlzd']),
                        fmt_pnl(row['unrlzd_pnl']),
                    )
                else:
                    table.add_row(
                        str(row['symbol']),
                        f"{row['book_price'] * -1:.2f}" if row['book_price'] != 0 else "",
                        f"{row['value']:,.2f}" if row['value'] != 0 else "",
                        f"{row['mtm']:,.2f}" if row['mtm'] != 0 else "",
                        mtm_pct_str,
                        f"{row['target_pct']:.2f}%" if row['target_pct'] != 0 else "",
                        self._fmt_diff(mtm_pct - target_pct),
                        self._fmt_diff_pct(mtm_pct, target_pct),
                        fmt_pnl(row['s_unrlzd']),
                        fmt_pnl(row['c_unrlzd']),
                        fmt_pnl(row['p_unrlzd']),
                        fmt_pnl(row['unrlzd_pnl']),
                        f"{tgt_shares:,}" if tgt_shares != 0 else "",
                        f"{row['s_qty']:.0f}" if row['s_qty'] != 0 else "",
                        f"{row['c_qty']:.0f}" if row['c_qty'] != 0 else "",
                        f"{row['p_qty']:.0f}" if row['p_qty'] != 0 else "",
                    )

            # Add totals row
            table.add_section()
            if is_lz:
                table.add_row(
                    "TOTAL",
                    f"{total_mtm:,.2f}",
                    f"{total_mtm / total_mtm * 100:.2f}%" if total_mtm != 0 else "",
                    fmt_pnl(total_s_unrlzd),
                    fmt_pnl(total_c_unrlzd),
                    fmt_pnl(total_p_unrlzd),
                    fmt_pnl(total_unrlzd_pnl),
                    fmt_pnl(total_s_pnl),
                    fmt_pnl(total_c_pnl),
                    fmt_pnl(total_p_pnl),
                    fmt_pnl(total_s_pnl + total_c_pnl + total_p_pnl),
                    style="bold"
                )
            elif is_lq:
                table.add_row(
                    "TOTAL",
                    "",  # Tgt Q column - no total
                    f"{total_s_qty:.0f}",
                    f"{total_c_qty:.0f}",
                    f"{total_p_qty:.0f}",
                    f"{total_target_pct:.2f}%" if total_target_pct != 0 else "",
                    "",  # Diff column - no total
                    "",  # Diff % column - no total
                    "",  # Book Price - no aggregate
                    f"{total_value:,.2f}",
                    f"{total_mtm:,.2f}",
                    f"{total_mtm / total_mtm * 100:.2f}%" if total_mtm != 0 else "",
                    fmt_pnl(total_s_unrlzd),
                    fmt_pnl(total_c_unrlzd),
                    fmt_pnl(total_p_unrlzd),
                    fmt_pnl(total_unrlzd_pnl),
                    style="bold"
                )
            else:
                table.add_row(
                    "TOTAL",
                    "",  # Book Price - no aggregate
                    f"{total_value:,.2f}",
                    f"{total_mtm:,.2f}",
                    f"{total_mtm / total_mtm * 100:.2f}%" if total_mtm != 0 else "",
                    f"{total_target_pct:.2f}%" if total_target_pct != 0 else "",
                    "",  # Diff column - no total
                    "",  # Diff % column - no total
                    fmt_pnl(total_s_unrlzd),
                    fmt_pnl(total_c_unrlzd),
                    fmt_pnl(total_p_unrlzd),
                    fmt_pnl(total_unrlzd_pnl),
                    "",  # Tgt Q column - no total
                    f"{total_s_qty:.0f}",
                    f"{total_c_qty:.0f}",
                    f"{total_p_qty:.0f}",
                    style="bold"
                )
            
            self.output_content = table
            
        except Exception as e:
            self.output_content = f"[error]Error listing all positions: {e}[/]"

    def list_positions_by_basket(self):
        try:
            if self.trades_df.empty:
                self.output_content = "[info]No trades loaded.[/]"
                return

            groups = self.trades_df.groupby('underlyingSymbol')

            symbol_rows = []
            for symbol, group in groups:
                stock_df = group[~group['putCall'].isin(['C', 'P'])]
                call_df = group[group['putCall'] == 'C']
                put_df = group[group['putCall'] == 'P']

                stock_credit_sum = stock_df['credit'].sum() if not stock_df.empty else 0.0
                value = stock_credit_sum * -1
                # MTM Value / MTM % consider shares only (ignore calls and puts)
                mtm = stock_df['mtm_value'].sum()
                s_unrlzd = stock_df['unrealized_pnl'].sum()
                c_unrlzd = call_df['unrealized_pnl'].sum()
                p_unrlzd = put_df['unrealized_pnl'].sum()
                unrlzd_pnl = s_unrlzd + c_unrlzd + p_unrlzd

                s_qty = stock_df['remaining_qty'].sum()
                c_qty = call_df['remaining_qty'].sum()
                p_qty = put_df['remaining_qty'].sum()

                s_pnl = stock_df['realized_pnl'].sum()
                c_pnl = call_df['realized_pnl'].sum()
                p_pnl = put_df['realized_pnl'].sum()

                if any(x != 0 for x in [value, mtm, s_qty, c_qty, p_qty, s_pnl, c_pnl, p_pnl]):
                    symbol_rows.append({
                        'symbol': symbol,
                        'basket': self.symbol_basket.get(symbol) or "(none)",
                        'value': value,
                        'mtm': mtm,
                        's_unrlzd': s_unrlzd,
                        'c_unrlzd': c_unrlzd,
                        'p_unrlzd': p_unrlzd,
                        'unrlzd_pnl': unrlzd_pnl,
                        'c_qty': c_qty,
                        'p_qty': p_qty,
                        's_pnl': s_pnl,
                        'c_pnl': c_pnl,
                        'p_pnl': p_pnl,
                        'target_pct': self.target_percent.get(symbol, 0.0),
                    })

            # Aggregate by basket
            basket_map = {}
            for r in symbol_rows:
                b = r['basket']
                if b not in basket_map:
                    basket_map[b] = {
                        'basket': b,
                        'value': 0.0,
                        'mtm': 0.0,
                        's_unrlzd': 0.0,
                        'c_unrlzd': 0.0,
                        'p_unrlzd': 0.0,
                        'unrlzd_pnl': 0.0,
                        'c_qty': 0.0,
                        'p_qty': 0.0,
                        's_pnl': 0.0,
                        'c_pnl': 0.0,
                        'p_pnl': 0.0,
                        'target_pct': 0.0,
                    }
                agg = basket_map[b]
                agg['value'] += r['value']
                agg['mtm'] += r['mtm']
                agg['s_unrlzd'] += r['s_unrlzd']
                agg['c_unrlzd'] += r['c_unrlzd']
                agg['p_unrlzd'] += r['p_unrlzd']
                agg['unrlzd_pnl'] += r['unrlzd_pnl']
                agg['c_qty'] += r['c_qty']
                agg['p_qty'] += r['p_qty']
                agg['s_pnl'] += r['s_pnl']
                agg['c_pnl'] += r['c_pnl']
                agg['p_pnl'] += r['p_pnl']
                agg['target_pct'] += r['target_pct']

            data_rows = sorted(basket_map.values(), key=lambda x: x['mtm'], reverse=True)

            total_value = sum(r['value'] for r in data_rows)
            total_mtm = sum(r['mtm'] for r in data_rows)
            total_s_unrlzd = sum(r['s_unrlzd'] for r in data_rows)
            total_c_unrlzd = sum(r['c_unrlzd'] for r in data_rows)
            total_p_unrlzd = sum(r['p_unrlzd'] for r in data_rows)
            total_unrlzd_pnl = sum(r['unrlzd_pnl'] for r in data_rows)
            total_c_qty = sum(r['c_qty'] for r in data_rows)
            total_p_qty = sum(r['p_qty'] for r in data_rows)
            total_s_pnl = sum(r['s_pnl'] for r in data_rows)
            total_c_pnl = sum(r['c_pnl'] for r in data_rows)
            total_p_pnl = sum(r['p_pnl'] for r in data_rows)
            total_target_pct = sum(r['target_pct'] for r in data_rows)

            table = Table(title="Positions by Basket", expand=False, row_styles=["", "on #1d2021"])
            table.add_column("Basket", style="neutral_yellow")
            table.add_column("Book Value", justify="right", style="neutral_yellow")
            table.add_column("MTM Value", justify="right", style="neutral_blue")
            table.add_column("MTM %", justify="right", style="neutral_blue")
            table.add_column("Tgt %", justify="right", style="neutral_aqua")
            table.add_column("Diff", justify="right", style="light4")
            table.add_column("Diff %", justify="right", style="light4")
            table.add_column("S Unr PnL", justify="right")
            table.add_column("C Unr PnL", justify="right")
            table.add_column("P Unr PnL", justify="right")
            table.add_column("Unrlzd PnL", justify="right")
            table.add_column("Call", justify="right", style="neutral_purple")
            table.add_column("Put", justify="right", style="neutral_purple")
            table.add_column("S Rlzd PnL", justify="right")
            table.add_column("C Rlzd PnL", justify="right")
            table.add_column("P Rlzd PnL", justify="right")
            table.add_column("T Rlzd PnL", justify="right")

            def fmt_pnl(val):
                if val == 0:
                    return ""
                if val > 0:
                    return f"[neutral_blue]{val:,.2f}[/neutral_blue]"
                return f"[bright_red]{val:,.2f}[/bright_red]"

            for r in data_rows:
                mtm_pct = r['mtm'] / total_mtm * 100 if total_mtm != 0 and r['mtm'] != 0 else 0
                t_pnl = r['s_pnl'] + r['c_pnl'] + r['p_pnl']
                table.add_row(
                    str(r['basket']),
                    f"{r['value']:,.2f}" if r['value'] != 0 else "",
                    f"{r['mtm']:,.2f}" if r['mtm'] != 0 else "",
                    f"{mtm_pct:.2f}%" if mtm_pct != 0 else "",
                    f"{r['target_pct']:.2f}%" if r['target_pct'] != 0 else "",
                    self._fmt_diff(mtm_pct - r['target_pct']),
                    self._fmt_diff_pct(mtm_pct, r['target_pct']),
                    fmt_pnl(r['s_unrlzd']),
                    fmt_pnl(r['c_unrlzd']),
                    fmt_pnl(r['p_unrlzd']),
                    fmt_pnl(r['unrlzd_pnl']),
                    f"{r['c_qty']:.0f}" if r['c_qty'] != 0 else "",
                    f"{r['p_qty']:.0f}" if r['p_qty'] != 0 else "",
                    fmt_pnl(r['s_pnl']),
                    fmt_pnl(r['c_pnl']),
                    fmt_pnl(r['p_pnl']),
                    fmt_pnl(t_pnl),
                )

            table.add_section()
            table.add_row(
                "TOTAL",
                f"{total_value:,.2f}",
                f"{total_mtm:,.2f}",
                f"{total_mtm / total_mtm * 100:.2f}%" if total_mtm != 0 else "",
                f"{total_target_pct:.2f}%" if total_target_pct != 0 else "",
                "",
                "",
                fmt_pnl(total_s_unrlzd),
                fmt_pnl(total_c_unrlzd),
                fmt_pnl(total_p_unrlzd),
                fmt_pnl(total_unrlzd_pnl),
                f"{total_c_qty:.0f}",
                f"{total_p_qty:.0f}",
                fmt_pnl(total_s_pnl),
                fmt_pnl(total_c_pnl),
                fmt_pnl(total_p_pnl),
                fmt_pnl(total_s_pnl + total_c_pnl + total_p_pnl),
                style="bold",
            )

            self.output_content = table

        except Exception as e:
            self.output_content = f"[error]Error listing positions by basket: {e}[/]"

    def list_csp(self):
        try:
            if self.trades_df.empty:
                self.output_content = "[info]No trades loaded.[/]"
                return

            groups = self.trades_df.groupby('underlyingSymbol')
            data_rows = []

            for symbol, group in groups:
                stock_df = group[~group['putCall'].isin(['C', 'P'])]
                call_df = group[group['putCall'] == 'C']
                put_df = group[group['putCall'] == 'P']

                stock_credit_sum = stock_df['credit'].sum() if not stock_df.empty else 0.0
                stock_rem_qty_sum = stock_df['remaining_qty'].sum() if not stock_df.empty else 0.0
                book_price = (stock_credit_sum / stock_rem_qty_sum) if stock_rem_qty_sum else 0.0
                value = stock_credit_sum * -1
                # MTM Value / MTM % consider shares only (ignore calls and puts)
                mtm = stock_df['mtm_value'].sum()
                share_price = stock_df['mtm_price'].max() if not stock_df.empty else 0.0

                s_qty = stock_df['remaining_qty'].sum()
                c_qty = call_df['remaining_qty'].sum()
                p_qty = put_df['remaining_qty'].sum()

                # CSP: sum over short put rows of |remaining_qty| * strike * 100
                csp = 0.0
                if not put_df.empty:
                    short_puts = put_df[put_df['remaining_qty'] < 0]
                    if not short_puts.empty:
                        csp = (-short_puts['remaining_qty'] * short_puts['strike'] * 100).sum()

                if any(x != 0 for x in [value, mtm, s_qty, c_qty, p_qty, csp]):
                    data_rows.append({
                        'symbol': symbol,
                        'book_price': book_price,
                        'value': value,
                        'mtm': mtm,
                        's_qty': s_qty,
                        'c_qty': c_qty,
                        'p_qty': p_qty,
                        'target_pct': self.target_percent.get(symbol, 0.0),
                        'share_price': share_price,
                        'csp': csp,
                    })

            data_rows.sort(key=lambda x: x['csp'], reverse=True)

            total_value = sum(r['value'] for r in data_rows)
            total_mtm = sum(r['mtm'] for r in data_rows)
            total_s_qty = sum(r['s_qty'] for r in data_rows)
            total_c_qty = sum(r['c_qty'] for r in data_rows)
            total_p_qty = sum(r['p_qty'] for r in data_rows)
            total_target_pct = sum(r['target_pct'] for r in data_rows)
            total_csp = sum(r['csp'] for r in data_rows)

            table = Table(title="Cash Secured Put", expand=False, row_styles=["", "on #1d2021"])
            table.add_column("Symbol", style="neutral_yellow")
            table.add_column("Book Price", justify="right", style="dark4")
            table.add_column("Book Value", justify="right", style="neutral_yellow")
            table.add_column("MTM Value", justify="right", style="neutral_blue")
            table.add_column("MTM %", justify="right", style="neutral_blue")
            table.add_column("Tgt %", justify="right", style="neutral_aqua")
            table.add_column("Qty", justify="right", style="neutral_purple")
            table.add_column("Tgt S", justify="right", style="neutral_aqua")
            table.add_column("Call", justify="right", style="neutral_purple")
            table.add_column("Put", justify="right", style="neutral_purple")
            table.add_column("CSP", justify="right", style="neutral_orange")

            for row in data_rows:
                mtm_pct = row['mtm'] / total_mtm * 100 if total_mtm != 0 and row['mtm'] != 0 else 0
                target_pct = row['target_pct']
                share_price = row['share_price']

                if target_pct != 0 and share_price != 0:
                    tgt_shares = round(total_mtm * target_pct / 100 / share_price)
                else:
                    tgt_shares = 0

                table.add_row(
                    str(row['symbol']),
                    f"{row['book_price'] * -1:.2f}" if row['book_price'] != 0 else "",
                    f"{row['value']:,.2f}" if row['value'] != 0 else "",
                    f"{row['mtm']:,.2f}" if row['mtm'] != 0 else "",
                    f"{mtm_pct:.2f}%" if mtm_pct != 0 else "",
                    f"{target_pct:.2f}%" if target_pct != 0 else "",
                    f"{row['s_qty']:.0f}" if row['s_qty'] != 0 else "",
                    f"{tgt_shares:,}" if tgt_shares != 0 else "",
                    f"{row['c_qty']:.0f}" if row['c_qty'] != 0 else "",
                    f"{row['p_qty']:.0f}" if row['p_qty'] != 0 else "",
                    f"{row['csp']:,.2f}" if row['csp'] != 0 else "",
                )

            table.add_section()
            table.add_row(
                "TOTAL",
                "",
                f"{total_value:,.2f}",
                f"{total_mtm:,.2f}",
                f"{total_mtm / total_mtm * 100:.2f}%" if total_mtm != 0 else "",
                f"{total_target_pct:.2f}%" if total_target_pct != 0 else "",
                f"{total_s_qty:.0f}",
                "",
                f"{total_c_qty:.0f}",
                f"{total_p_qty:.0f}",
                f"{total_csp:,.2f}",
                style="bold",
            )

            self.output_content = table

        except Exception as e:
            self.output_content = f"[error]Error listing CSP positions: {e}[/]"

    def list_positions_csv(self):
        try:
            if self.trades_df.empty:
                self.output_content = "[info]No trades loaded.[/]"
                return

            data_rows = []
            for symbol, group in self.trades_df.groupby('underlyingSymbol'):
                stock_df = group[~group['putCall'].isin(['C', 'P'])]
                call_df = group[group['putCall'] == 'C']
                put_df = group[group['putCall'] == 'P']

                stock_credit_sum = stock_df['credit'].sum() if not stock_df.empty else 0.0
                stock_rem_qty_sum = stock_df['remaining_qty'].sum() if not stock_df.empty else 0.0
                book_price = (stock_credit_sum / stock_rem_qty_sum) if stock_rem_qty_sum else 0.0
                value = stock_credit_sum * -1
                # MTM Value / MTM % consider shares only (ignore calls and puts)
                mtm = stock_df['mtm_value'].sum()
                share_price = stock_df['mtm_price'].max() if not stock_df.empty else 0.0
                unrlzd_pnl = group['unrealized_pnl'].sum()
                s_qty = stock_df['remaining_qty'].sum()
                c_qty = call_df['remaining_qty'].sum()
                p_qty = put_df['remaining_qty'].sum()
                s_pnl = stock_df['realized_pnl'].sum()
                c_pnl = call_df['realized_pnl'].sum()
                p_pnl = put_df['realized_pnl'].sum()

                if any(x != 0 for x in [value, mtm, s_qty, c_qty, p_qty, s_pnl, c_pnl, p_pnl]):
                    data_rows.append({
                        'symbol': symbol,
                        'book_price': book_price,
                        'value': value,
                        'mtm': mtm,
                        'unrlzd_pnl': unrlzd_pnl,
                        's_qty': s_qty,
                        'c_qty': c_qty,
                        'p_qty': p_qty,
                        's_pnl': s_pnl,
                        'c_pnl': c_pnl,
                        'p_pnl': p_pnl,
                        'target_pct': self.target_percent.get(symbol, 0.0),
                        'share_price': share_price,
                    })

            total_mtm = sum(r['mtm'] for r in data_rows)
            data_rows.sort(key=lambda x: x['symbol'])

            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                "Symbol", "Book Price", "Book Value", "MTM Value", "MTM %",
                "Tgt %", "Tgt S", "Diff", "Diff %", "Unrlzd PnL", "Qty", "Call", "Put",
                "S Rlzd PnL", "C Rlzd PnL", "P Rlzd PnL", "T Rlzd PnL",
            ])

            def num(v, fmt="{:.2f}"):
                return fmt.format(v) if v else ""

            for r in data_rows:
                mtm_pct = r['mtm'] / total_mtm * 100 if total_mtm and r['mtm'] else 0
                tgt = r['target_pct']
                sp = r['share_price']
                tgt_s = round(total_mtm * tgt / 100 / sp) if tgt and sp else 0
                diff = mtm_pct - tgt
                diff_pct = (mtm_pct / tgt * 100) if tgt and mtm_pct else 0
                t_pnl = r['s_pnl'] + r['c_pnl'] + r['p_pnl']
                writer.writerow([
                    r['symbol'],
                    num(r['book_price'] * -1),
                    num(r['value']),
                    num(r['mtm']),
                    num(mtm_pct),
                    num(tgt),
                    tgt_s if tgt_s else "",
                    num(diff),
                    f"{round(diff_pct)}" if diff_pct else "",
                    num(r['unrlzd_pnl']),
                    f"{r['s_qty']:.0f}" if r['s_qty'] else "",
                    f"{r['c_qty']:.0f}" if r['c_qty'] else "",
                    f"{r['p_qty']:.0f}" if r['p_qty'] else "",
                    num(r['s_pnl']),
                    num(r['c_pnl']),
                    num(r['p_pnl']),
                    num(t_pnl),
                ])

            self.app.console.clear()
            self.app.console.print(buf.getvalue(), markup=False, highlight=False)
            self.app.skip_render = True

        except Exception as e:
            self.output_content = f"[error]Error generating CSV: {e}[/]"

    def get_output(self):
        if self.active_submodule is not None:
            return self.active_submodule.get_output()
        return self.output_content
