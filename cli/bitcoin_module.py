import pandas as pd
from rich.table import Table
from rich.columns import Columns
from base_module import Module
from cli.db import bitcoin_db
from datetime import datetime

EXCHANGES = {
    '1': 'Coinbase',
    '2': 'Bitcoin Well',
    '3': 'Bull Bitcoin',
    '4': 'Crypto.com',
}

ACCOUNTS = {
    '1': 'FZ',
    '2': 'MPM',
    '3': 'GFZ',
}


class BitcoinModule(Module):
    name = "BITCOIN"
    emoji = "₿"

    def __init__(self, app):
        super().__init__(app)
        self.btc_df = pd.DataFrame()
        self.output_content = ""
        self.current_subset = None  # Currently displayed rows (for edit/delete)
        self.load_data()

    def load_data(self):
        self.btc_df = bitcoin_db.fetch_bitcoin_data()
        cols = ['id', 'exchange', 'date', 'date_on_chain', 'quantity', 'cost_cad',
                'account', 'fees_cad', 'fees_sats', 'notes']
        if self.btc_df.empty:
            self.btc_df = pd.DataFrame(columns=cols)
            return

        self.btc_df['date'] = pd.to_datetime(self.btc_df['date'])
        self.btc_df['quantity'] = pd.to_numeric(self.btc_df['quantity'], errors='coerce').fillna(0.0)
        self.btc_df['cost_cad'] = pd.to_numeric(self.btc_df['cost_cad'], errors='coerce').fillna(0.0)

        # Derived columns
        self.btc_df['sats'] = (self.btc_df['quantity'] * 100_000_000).round().astype('int64')
        self.btc_df['buy_price'] = self.btc_df.apply(
            lambda r: r['cost_cad'] / r['quantity'] if r['quantity'] else 0.0, axis=1
        )

        self.btc_df.sort_values('date', ascending=False, inplace=True)

    def handle_command(self, command):
        cmd = command.lower().strip()
        if cmd in ['q', 'quit']:
            from home_module import HomeModule
            self.app.switch_module(HomeModule(self.app))
        elif cmd == 'qq':
            self.app.quit()
        elif cmd in ['h', 'help']:
            self.output_content = '''Bitcoin Commands:
    - a | add     : Add a new buy
    - l | list    : List all buys
    - r | report  : Show stats report (totals, average cost, by account/exchange)
    - e <number>  : Edit a buy by its index (list first)
    - d <number>  : Delete a buy by its index (list first)
    - q | quit    : Return to main menu
    - qq          : Exit application'''
        elif cmd in ['a', 'add']:
            self.add_entry()
        elif cmd in ['l', 'list']:
            self.show_list()
        elif cmd in ['r', 'report']:
            self.show_report()
        elif cmd == 'e' or cmd == 'edit' or cmd.startswith('e ') or cmd.startswith('edit '):
            parts = cmd.split()
            if len(parts) == 1:
                self.show_list()
                choice = self.app.console.input("\nEdit which # >> ")
                try:
                    self.edit_entry(int(choice))
                except ValueError:
                    self.output_content = "[error]Invalid line number.[/]"
            elif len(parts) == 2:
                try:
                    self.edit_entry(int(parts[1]))
                except ValueError:
                    self.output_content = "[error]Invalid line number.[/]"
            else:
                self.output_content = "[error]Usage: e [line_number][/]"
        elif cmd.startswith('d ') or cmd.startswith('delete '):
            parts = cmd.split()
            if len(parts) == 2:
                try:
                    self.delete_entry(int(parts[1]))
                except ValueError:
                    self.output_content = "[error]Invalid line number.[/]"
            else:
                self.output_content = "[error]Usage: d <line_number>[/]"
        elif cmd == "":
            pass
        else:
            self.output_content = f"Unknown command: {command}"

    # ------------------------------------------------------------------
    # Add
    # ------------------------------------------------------------------
    def add_entry(self):
        self.app.console.clear()
        self.app.console.print("[bold cyan]--- Add Bitcoin Buy ---[/]")

        default_date_str = datetime.now().strftime("%Y-%m-%d")

        while True:
            # Exchange
            self.app.console.print("Exchange:\n[1] Coinbase,\n[2] Bitcoin Well,\n[3] Bull Bitcoin,\n[4] Crypto.com")
            exc_choice = self.app.console.input("Exchange >> ").strip()
            exchange_val = EXCHANGES.get(exc_choice, exc_choice)

            # Date
            date_in = self.app.console.input(f"Date [[dim]{default_date_str}[/dim]] >> ")
            date_val = date_in if date_in else default_date_str

            # Date on chain (optional)
            chain_in = self.app.console.input("Date on chain (optional) >> ").strip()
            date_on_chain_val = chain_in if chain_in else None

            # Account
            self.app.console.print("Account:\n[1] FZ,\n[2] MPM,\n[3] GFZ")
            acc_choice = self.app.console.input("Account >> ").strip()
            account_val = ACCOUNTS.get(acc_choice, acc_choice.upper())

            # Quantity
            qty_val = self._input_float("Quantity (BTC) >> ", 0.0)

            # Cost in CAD
            cost_val = self._input_float("Cost in CAD >> ", 0.0)

            # Fees $ (optional)
            fees_cad_val = self._input_float("Fees $ (optional) >> ", None)

            # Fees Sats (optional)
            fees_sats_val = self._input_int("Fees Sats (optional) >> ", None)

            # Notes
            notes_in = self.app.console.input("Notes (optional) >> ").strip()
            notes_val = notes_in if notes_in else None

            # Preview derived
            sats = round(qty_val * 100_000_000)
            price = cost_val / qty_val if qty_val else 0.0
            self.app.console.print(
                f"[dim]-> {sats:,} sats @ {price:,.2f} CAD/BTC[/]"
            )

            entry = {
                'exchange': exchange_val,
                'date': date_val,
                'date_on_chain': date_on_chain_val,
                'quantity': qty_val,
                'cost_cad': cost_val,
                'account': account_val,
                'fees_cad': fees_cad_val,
                'fees_sats': fees_sats_val,
                'notes': notes_val,
            }

            if bitcoin_db.save_bitcoin_entry(entry):
                self.app.console.print("[success]Buy added![/]")
            else:
                self.app.console.print("[error]Failed to add buy.[/]")

            again = self.app.console.input("\nAdd another? (y/n) >> ").lower()
            if again == 'y':
                default_date_str = date_val
            else:
                break

        self.load_data()
        self.output_content = "Data updated."

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    def show_list(self):
        if self.btc_df.empty:
            self.output_content = "[info]No bitcoin buys found.[/]"
            return

        subset = self.btc_df.reset_index(drop=True)
        self.current_subset = subset

        table = Table(title="Bitcoin Buys", expand=False, row_styles=["", "on #1d2021"])
        table.add_column("#", style="dim", justify="right")
        table.add_column("Date", style="dim")
        table.add_column("Exchange", style="cyan")
        table.add_column("Acct", style="magenta")
        table.add_column("Quantity", justify="right")
        table.add_column("Sats", justify="right")
        table.add_column("Cost CAD", justify="right", style="green")
        table.add_column("Price", justify="right", style="yellow")
        table.add_column("Fees $", justify="right")
        table.add_column("Notes", style="dim")

        for i, row in subset.iterrows():
            table.add_row(
                str(i + 1),
                pd.to_datetime(row['date']).strftime('%Y-%m-%d'),
                str(row['exchange']),
                str(row['account']),
                f"{row['quantity']:.8f}",
                f"{int(row['sats']):,}",
                f"{row['cost_cad']:,.2f}",
                f"{row['buy_price']:,.2f}",
                f"{row['fees_cad']:,.2f}" if pd.notna(row.get('fees_cad')) else "",
                str(row['notes']) if pd.notna(row.get('notes')) else "",
            )

        total_qty = subset['quantity'].sum()
        total_cost = subset['cost_cad'].sum()
        avg_price = total_cost / total_qty if total_qty else 0.0
        table.add_section()
        table.add_row(
            "", "", "TOTAL", "",
            f"{total_qty:.8f}",
            f"{int(round(total_qty * 100_000_000)):,}",
            f"{total_cost:,.2f}",
            f"{avg_price:,.2f}",
            "", "",
            style="bold"
        )

        self.app.console.clear()
        self.app.console.print(table)
        self.app.skip_render = True
        self.output_content = ""

    # ------------------------------------------------------------------
    # Report (stats)
    # ------------------------------------------------------------------
    def show_report(self):
        if self.btc_df.empty:
            self.output_content = "[info]No bitcoin buys found.[/]"
            return

        df = self.btc_df

        def stats_table(title, group_col, color):
            grp = df.groupby(group_col).agg(
                buys=('quantity', 'size'),
                quantity=('quantity', 'sum'),
                cost=('cost_cad', 'sum'),
            ).reset_index().sort_values('cost', ascending=False)

            t = Table(title=title)
            t.add_column(group_col.capitalize(), style=color)
            t.add_column("Buys", justify="right")
            t.add_column("BTC", justify="right")
            t.add_column("Cost CAD", justify="right", style="green")
            t.add_column("Avg Cost", justify="right", style="yellow")

            for _, r in grp.iterrows():
                avg = r['cost'] / r['quantity'] if r['quantity'] else 0.0
                t.add_row(
                    str(r[group_col]),
                    str(int(r['buys'])),
                    f"{r['quantity']:.8f}",
                    f"{r['cost']:,.2f}",
                    f"{avg:,.2f}",
                )
            t_qty = grp['quantity'].sum()
            t_cost = grp['cost'].sum()
            t_avg = t_cost / t_qty if t_qty else 0.0
            t.add_section()
            t.add_row("TOTAL", str(int(grp['buys'].sum())), f"{t_qty:.8f}",
                      f"{t_cost:,.2f}", f"{t_avg:,.2f}", style="bold")
            return t

        # Overall summary
        total_qty = df['quantity'].sum()
        total_cost = df['cost_cad'].sum()
        avg_price = total_cost / total_qty if total_qty else 0.0
        total_sats = int(round(total_qty * 100_000_000))
        total_buys = len(df)
        total_fees = pd.to_numeric(df.get('fees_cad'), errors='coerce').fillna(0).sum()

        summary = Table(title="Bitcoin Summary", show_header=False)
        summary.add_column("Metric", style="cyan")
        summary.add_column("Value", justify="right", style="bold")
        summary.add_row("Total buys", f"{total_buys:,}")
        summary.add_row("Total BTC", f"{total_qty:.8f}")
        summary.add_row("Total Sats", f"{total_sats:,}")
        summary.add_row("Total Cost CAD", f"{total_cost:,.2f}")
        summary.add_row("Average Cost (CAD/BTC)", f"{avg_price:,.2f}")
        summary.add_row("Total Fees CAD", f"{total_fees:,.2f}")

        self.app.console.clear()
        self.app.console.print(summary)
        self.app.console.print()
        self.app.console.print(
            Columns(
                [stats_table("By Account", 'account', 'magenta'),
                 stats_table("By Exchange", 'exchange', 'cyan')],
                equal=True, expand=True,
            )
        )
        self.app.skip_render = True
        self.output_content = ""

    # ------------------------------------------------------------------
    # Edit
    # ------------------------------------------------------------------
    def edit_entry(self, line_num):
        if self.current_subset is None or self.current_subset.empty:
            self.output_content = "[error]No buys to edit. Use 'l' to list first.[/]"
            return

        row_idx = line_num - 1
        if row_idx < 0 or row_idx >= len(self.current_subset):
            self.output_content = f"[error]Line {line_num} not found. Valid range: 1-{len(self.current_subset)}[/]"
            return

        row = self.current_subset.iloc[row_idx]
        entry_id = int(row['id'])

        self.app.console.clear()
        self.app.console.print(f"[bold cyan]--- Edit Buy #{line_num} ---[/]")
        self.app.console.print(f"[dim]{pd.to_datetime(row['date']).strftime('%Y-%m-%d')} - {row['exchange']} ({row['account']})[/]\n")

        # Exchange
        current_exc = str(row['exchange'])
        self.app.console.print("Exchange:\n[1] Coinbase,\n[2] Bitcoin Well,\n[3] Bull Bitcoin,\n[4] Crypto.com")
        exc_in = self.app.console.input(f"Exchange [[dim]{current_exc}[/dim]] >> ").strip()
        exchange_val = EXCHANGES.get(exc_in, exc_in) if exc_in else current_exc

        # Date
        current_date = pd.to_datetime(row['date']).strftime('%Y-%m-%d')
        date_in = self.app.console.input(f"Date [[dim]{current_date}[/dim]] >> ")
        date_val = date_in if date_in else current_date

        # Date on chain
        current_chain = row['date_on_chain']
        current_chain_str = pd.to_datetime(current_chain).strftime('%Y-%m-%d') if pd.notna(current_chain) else ""
        chain_in = self.app.console.input(f"Date on chain [[dim]{current_chain_str or 'none'}[/dim]] (- to clear) >> ").strip()
        if chain_in == '-':
            date_on_chain_val = None
        elif chain_in:
            date_on_chain_val = chain_in
        else:
            date_on_chain_val = current_chain_str if current_chain_str else None

        # Account
        current_acc = str(row['account'])
        self.app.console.print("Account:\n[1] FZ,\n[2] MPM,\n[3] GFZ")
        acc_in = self.app.console.input(f"Account [[dim]{current_acc}[/dim]] >> ").strip()
        account_val = ACCOUNTS.get(acc_in, acc_in.upper()) if acc_in else current_acc

        # Quantity
        qty_val = self._input_float(f"Quantity [[dim]{row['quantity']:.8f}[/dim]] >> ", float(row['quantity']))

        # Cost
        cost_val = self._input_float(f"Cost CAD [[dim]{row['cost_cad']:,.2f}[/dim]] >> ", float(row['cost_cad']))

        # Fees $
        cur_fees_cad = row['fees_cad'] if pd.notna(row.get('fees_cad')) else None
        fees_cad_val = self._input_float(f"Fees $ [[dim]{cur_fees_cad if cur_fees_cad is not None else 'none'}[/dim]] (- to clear) >> ", cur_fees_cad, allow_clear=True)

        # Fees Sats
        cur_fees_sats = int(row['fees_sats']) if pd.notna(row.get('fees_sats')) else None
        fees_sats_val = self._input_int(f"Fees Sats [[dim]{cur_fees_sats if cur_fees_sats is not None else 'none'}[/dim]] (- to clear) >> ", cur_fees_sats, allow_clear=True)

        # Notes
        cur_notes = str(row['notes']) if pd.notna(row.get('notes')) else ""
        notes_in = self.app.console.input(f"Notes [[dim]{cur_notes or 'none'}[/dim]] (- to clear) >> ").strip()
        if notes_in == '-':
            notes_val = None
        elif notes_in:
            notes_val = notes_in
        else:
            notes_val = cur_notes if cur_notes else None

        entry = {
            'exchange': exchange_val,
            'date': date_val,
            'date_on_chain': date_on_chain_val,
            'quantity': qty_val,
            'cost_cad': cost_val,
            'account': account_val,
            'fees_cad': fees_cad_val,
            'fees_sats': fees_sats_val,
            'notes': notes_val,
        }

        confirm = self.app.console.input("\nConfirm update? (y/n) >> ").lower()
        if confirm == 'y':
            if bitcoin_db.update_bitcoin_entry(entry_id, entry):
                self.app.console.print("[success]Buy updated![/]")
                self.load_data()
                self.output_content = "Data updated."
            else:
                self.app.console.print("[error]Failed to update buy.[/]")
                self.output_content = "Update failed."
        else:
            self.output_content = "Edit cancelled."

        self.current_subset = None

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------
    def delete_entry(self, line_num):
        if self.current_subset is None or self.current_subset.empty:
            self.output_content = "[error]No buys to delete. Use 'l' to list first.[/]"
            return

        row_idx = line_num - 1
        if row_idx < 0 or row_idx >= len(self.current_subset):
            self.output_content = f"[error]Line {line_num} not found. Valid range: 1-{len(self.current_subset)}[/]"
            return

        row = self.current_subset.iloc[row_idx]
        entry_id = int(row['id'])

        self.app.console.clear()
        self.app.console.print(f"[bold red]--- Delete Buy #{line_num} ---[/]")
        self.app.console.print(f"  Date:     {pd.to_datetime(row['date']).strftime('%Y-%m-%d')}")
        self.app.console.print(f"  Exchange: {row['exchange']}")
        self.app.console.print(f"  Account:  {row['account']}")
        self.app.console.print(f"  Quantity: {row['quantity']:.8f}")
        self.app.console.print(f"  Cost CAD: {row['cost_cad']:,.2f}")

        confirm = self.app.console.input("\n[bold red]Confirm DELETE?[/] (y/n) >> ").lower()
        if confirm == 'y':
            if bitcoin_db.delete_bitcoin_entry(entry_id):
                self.app.console.print("[success]Buy deleted![/]")
                self.load_data()
                self.output_content = "Entry deleted."
            else:
                self.app.console.print("[error]Failed to delete buy.[/]")
                self.output_content = "Delete failed."
        else:
            self.output_content = "Delete cancelled."

        self.current_subset = None

    # ------------------------------------------------------------------
    # Input helpers
    # ------------------------------------------------------------------
    def _input_float(self, prompt, default, allow_clear=False):
        raw = self.app.console.input(prompt).strip()
        if raw == '' :
            return default
        if allow_clear and raw == '-':
            return None
        try:
            return float(raw)
        except ValueError:
            return default

    def _input_int(self, prompt, default, allow_clear=False):
        raw = self.app.console.input(prompt).strip()
        if raw == '':
            return default
        if allow_clear and raw == '-':
            return None
        try:
            return int(float(raw))
        except ValueError:
            return default

    def get_output(self):
        return self.output_content
