import pandas as pd
from rich.table import Table
from rich.console import Group, Console
from base_module import Module
from cli.db import fbn_db
from tui import multi_select

class FBNModule(Module):
    name = "FBN"
    emoji = "📊"

    def __init__(self, app):
        super().__init__(app)
        self.df = pd.DataFrame()
        self.monthly_df = pd.DataFrame()
        self.yearly_df = pd.DataFrame()
        self.output_content = ""
        self.account_filter = []

        self.load_fbn_data()

        self.accounts = [
            {'name': 'MARGE', 'portfolio': 'Personnel', 'currency': 'CAD'},
            {'name': 'REER', 'portfolio': 'Personnel', 'currency': 'CAD'},
            {'name': 'CRI', 'portfolio': 'Personnel', 'currency': 'CAD'},
            {'name': 'REEE', 'portfolio': 'Personnel', 'currency': 'CAD'},
            {'name': 'CELI', 'portfolio': 'Personnel', 'currency': 'CAD'},
            {'name': 'MM MARGE', 'portfolio': 'Personnel', 'currency': 'CAD'},
            {'name': 'MM CELI', 'portfolio': 'Personnel', 'currency': 'CAD'},
            {'name': 'GFZ CAD', 'portfolio': 'Gestion FZ', 'currency': 'CAD'},
            {'name': 'GFZ USD', 'portfolio': 'Gestion FZ', 'currency': 'USD'},
        ]

    def load_fbn_data(self):
        self.df = fbn_db.fetch_fbn_data()

        if not self.df.empty:
            self.df['date'] = pd.to_datetime(self.df['date'])

            # Apply Currency Conversion (USD -> CAD)
            cols_to_convert = ['investment', 'deposit', 'asset', 'fee', 'dividend', 'interest', 'tax', 'other', 'cash', 'distribution']
            mask = self.df['currency'] == 'USD'
            for col in cols_to_convert:
                self.df.loc[mask, col] = self.df.loc[mask, col] * self.df.loc[mask, 'rate']

            self.monthly_df, self.yearly_df = self._aggregate(self.df)
        else:
            self.app.console.print("[error]No FBN data found.[/]")

    def _apply_arg_filter(self, arg):
        portfolio_by_shortcut = {'g': 'Gestion FZ', 'p': 'Personnel'}
        custom_filters = {
            'f': ['MARGE', 'REER', 'CELI', 'REEE', 'CRI', 'GFZ CAD', 'GFZ USD'],
            'm': ['MM MARGE', 'MM CELI'],
        }
        if arg in custom_filters:
            self.account_filter = sorted(custom_filters[arg])
            return True
        portfolio = portfolio_by_shortcut.get(arg)
        if portfolio is None:
            return False
        self.account_filter = sorted(a['name'] for a in self.accounts if a['portfolio'] == portfolio)
        return True

    def _filtered_df(self):
        if self.df.empty or not self.account_filter:
            return self.df
        return self.df[self.df['account'].isin(self.account_filter)]

    def _aggregate(self, df):
        """Return (monthly_df, yearly_df) aggregated from the given currency-converted df."""
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()

        monthly_df = (
            df.groupby('date', as_index=False)[['deposit', 'asset', 'fee']]
            .sum()
            .sort_values('date')
            .reset_index(drop=True)
        )
        monthly_df['prev_asset'] = monthly_df['asset'].shift(1).fillna(0.0)
        monthly_df['pnl'] = monthly_df['asset'] - monthly_df['deposit'] - monthly_df['prev_asset']
        monthly_df['pct'] = monthly_df.apply(
            lambda row: (row['pnl'] / row['prev_asset']) * 100 if row['prev_asset'] != 0 else 0.0,
            axis=1,
        )

        temp_df = monthly_df.copy()
        temp_df['year'] = temp_df['date'].dt.year
        yearly_agg = []
        for year, group in temp_df.groupby('year'):
            yearly_agg.append({
                'year': year,
                'deposit': group['deposit'].sum(),
                'asset': group.iloc[-1]['asset'],
                'fee': group['fee'].sum(),
            })
        yearly_df = pd.DataFrame(yearly_agg)
        if not yearly_df.empty:
            yearly_df = yearly_df.sort_values('year').reset_index(drop=True)
            yearly_df['prev_asset'] = yearly_df['asset'].shift(1).fillna(0.0)
            yearly_df['pnl'] = yearly_df['asset'] - yearly_df['deposit'] - yearly_df['prev_asset']
            yearly_df['pct'] = yearly_df.apply(
                lambda row: (row['pnl'] / row['prev_asset']) * 100 if row['prev_asset'] != 0 else 0.0,
                axis=1,
            )
        return monthly_df, yearly_df

    def handle_command(self, command):
        cmd = command.lower().strip()
        tokens = cmd.split()
        arg = None
        if len(tokens) >= 2 and tokens[0] in ('lm', 'ly', 'fa'):
            cmd = tokens[0]
            arg = tokens[1]
        if cmd in ['q', 'quit']:
            # Local import to avoid circular dependency
            from home_module import HomeModule
            self.app.switch_module(HomeModule(self.app))
        elif cmd in ['qq', 'quit quit']:
            self.app.quit()
        elif cmd in ['h', 'help']:
            self.output_content = '''FBN commands:
        - LM  | list monthly        > List monthly stats
        - LY  | list yearly         > List yearly stats
        - LMA | list monthly assets > List all accounts separately, monthly
        - LYA | list yearly assets  > List all accounts separately, yearly
        - FA  | filter account      > Multi-select account filter
        - FR  | filter reset        > Clear the account filter
        - Q   | quit                > Return to main menu
        - QQ  | quit quit           > Exit the application

LM, LY and FA accept an optional filter argument:
        - p : Personnal
        - g : Gestion FZ
        - f : Francois
        - m : Marie-Pierre'''
        elif cmd in ['fa', 'filter account']:
            if arg:
                if self._apply_arg_filter(arg):
                    self.output_content = f"[success]Account filter set: {', '.join(self.account_filter)}[/]"
                else:
                    self.output_content = f"[error]Unknown filter shortcut: {arg} (use 'g', 'p', 'f', or 'm')[/]"
            else:
                self.filter_accounts()
        elif cmd in ['fr', 'filter reset']:
            self.account_filter = []
            self.output_content = "[success]Account filter cleared.[/]"
        elif cmd in ['lm', 'list monthly']:
            if arg and not self._apply_arg_filter(arg):
                self.output_content = f"[error]Unknown filter shortcut: {arg} (use 'g', 'p', 'f', or 'm')[/]"
                return
            self.list_monthly()
        elif cmd in ['lma', 'list monthly assets']:
            self.list_monthly_assets()
        elif cmd in ['ly', 'list yearly']:
            if arg and not self._apply_arg_filter(arg):
                self.output_content = f"[error]Unknown filter shortcut: {arg} (use 'g', 'p', 'f', or 'm')[/]"
                return
            self.list_yearly()
        elif cmd in ['lya', 'list yearly assets']:
            self.list_yearly_assets()
        elif cmd in ['a', 'add', 'e', 'edit']:
            self.add_monthly_data()
        elif cmd == "":
            pass
        else:
            self.output_content = f"Unknown command: {command}\nType 'help' for valid commands."

    def list_monthly(self):
        try:
            monthly_df, _ = self._aggregate(self._filtered_df())
            if monthly_df.empty:
                self.output_content = "[info]No monthly data available.[/]"
                return

            title_suffix = f" — {', '.join(self.account_filter)}" if self.account_filter else ""
            table = Table(title=f"FBN Monthly Stats{title_suffix}", expand=False)
            table.add_column("Date", style="cyan")
            table.add_column("Deposit", justify="right")
            table.add_column("Asset", justify="right", style="magenta")
            table.add_column("Fee", justify="right")
            table.add_column("PnL", justify="right")
            table.add_column("Pct", justify="right")

            for _, row in monthly_df.tail(90).iterrows():
                date_str = row['date'].strftime('%Y-%m-%d')
                
                deposit = row['deposit']
                asset = row['asset']
                fee = row['fee']
                pnl = row['pnl']
                pct = row['pct']
                
                # Formatting
                pnl_style = "bold blue" if pnl > 0 else "bold orange1" if pnl < 0 else "dim"
                pct_style = "bold blue" if pct > 0 else "bold orange1" if pct < 0 else "dim"
                
                table.add_row(
                    date_str,
                    f"{deposit:,.2f}" if deposit != 0 else "-",
                    f"{asset:,.2f}",
                    f"{fee:,.2f}" if fee != 0 else "-",
                    f"[{pnl_style}]{pnl:,.2f}[/{pnl_style}]",
                    f"[{pct_style}]{pct:,.2f}%[/{pct_style}]"
                )

            # Direct print if needed, or return via output_content
            # ibkr_module often does direct print for lists, let's stick to output_content for now unless it's too long
            # If it's too long, main.py layout handles scrolling? No, rich layout doesn't scroll natively without a pager.
            # ibkr_module used `self.app.console.print(table)` and `skip_render=True` for long lists. 
            # Given 10 years of monthly data ~ 120 rows, it might be long.

            self.app.console.print(table)
            self.app.skip_render = True

        except Exception as e:
            self.output_content = f"[error]Error listing monthly stats: {e}[/]"

    def list_yearly(self):
        try:
            _, yearly_df = self._aggregate(self._filtered_df())
            if yearly_df.empty:
                self.output_content = "[info]No yearly data available.[/]"
                return

            title_suffix = f" — {', '.join(self.account_filter)}" if self.account_filter else ""
            table = Table(title=f"FBN Yearly Stats{title_suffix}", expand=False)
            table.add_column("Year", style="cyan")
            table.add_column("Deposit", justify="right")
            table.add_column("Asset", justify="right", style="magenta")
            table.add_column("Fee", justify="right")
            table.add_column("PnL", justify="right")
            table.add_column("Pct", justify="right")

            for _, row in yearly_df.iterrows():
                year_str = str(row['year'])
                
                deposit = row['deposit']
                asset = row['asset']
                fee = row['fee']
                pnl = row['pnl']
                pct = row['pct']
                
                # Formatting
                pnl_style = "bold blue" if pnl > 0 else "bold orange1" if pnl < 0 else "dim"
                pct_style = "bold blue" if pct > 0 else "bold orange1" if pct < 0 else "dim"
                
                table.add_row(
                    year_str,
                    f"{deposit:,.2f}" if deposit != 0 else "-",
                    f"{asset:,.2f}",
                    f"{fee:,.2f}" if fee != 0 else "-",
                    f"[{pnl_style}]{pnl:,.2f}[/{pnl_style}]",
                    f"[{pct_style}]{pct:,.2f}%[/{pct_style}]"
                )

            # Calculate Totals
            total_deposit = yearly_df['deposit'].sum()
            total_fee = yearly_df['fee'].sum()
            total_pnl = yearly_df['pnl'].sum()
            current_asset = yearly_df.iloc[-1]['asset']
            
            total_pnl_style = "bold blue" if total_pnl > 0 else "bold orange1" if total_pnl < 0 else "dim"
            
            table.add_section()
            table.add_row(
                "Total",
                f"{total_deposit:,.2f}",
                f"{current_asset:,.2f}",
                f"{total_fee:,.2f}",
                f"[{total_pnl_style}]{total_pnl:,.2f}[/{total_pnl_style}]",
                "-"
            )

            self.app.console.print(table)
            self.app.skip_render = True
            
        except Exception as e:
            self.output_content = f"[error]Error listing yearly stats: {e}[/]"

    def list_monthly_assets(self):
        try:
            if self.df.empty:
                self.output_content = "[info]No data available.[/]"
                return

            # Pivot table: Date as index, Account as columns, Asset as values
            pivot_df = self.df.pivot_table(index='date', columns='account', values='asset', aggfunc='sum')
            
            # Sort by date
            pivot_df = pivot_df.sort_index()

            # Ensure columns are in the correct order (as defined in self.accounts)
            ordered_columns = [acc['name'] for acc in self.accounts if acc['name'] in pivot_df.columns]
            # Add any extra columns that might exist but aren't in the predefined list
            extra_columns = [col for col in pivot_df.columns if col not in ordered_columns]
            final_columns = ordered_columns + extra_columns
            pivot_df = pivot_df[final_columns]

            # Create Rich Table
            table = Table(title="FBN Monthly Assets Matrix", expand=False)
            table.add_column("Date", style="cyan", no_wrap=True)
            for col in final_columns:
                table.add_column(col, justify="right")
            
            # Add Total column
            table.add_column("Total", justify="right", style="bold magenta")

            for date, row in pivot_df.tail(90).iterrows():
                row_data = [date.strftime('%Y-%m-%d')]
                total_assets = 0
                for col in final_columns:
                    val = row[col]
                    if pd.notna(val):
                        row_data.append(f"{val:,.2f}")
                        total_assets += val
                    else:
                        row_data.append("-")
                
                row_data.append(f"{total_assets:,.2f}")
                table.add_row(*row_data)

            self.app.console.print(table)
            self.app.skip_render = True

        except Exception as e:
             self.output_content = f"[error]Error listing monthly assets matrix: {e}[/]"

    def list_yearly_assets(self):
        try:
            if self.df.empty:
                self.output_content = "[info]No data available.[/]"
                return

            # Create a copy to work with
            temp_df = self.df.copy()
            temp_df['year'] = temp_df['date'].dt.year

            # Group by year and account, then take the last entry (by date) for each
            # We sort by date first to ensure 'last' is essentially max date
            temp_df = temp_df.sort_values('date')
            yearly_last = temp_df.groupby(['year', 'account']).last().reset_index()

            # Pivot table
            pivot_df = yearly_last.pivot_table(index='year', columns='account', values='asset', aggfunc='sum')
            pivot_df = pivot_df.sort_index()

            # Ensure columns order
            ordered_columns = [acc['name'] for acc in self.accounts if acc['name'] in pivot_df.columns]
            extra_columns = [col for col in pivot_df.columns if col not in ordered_columns]
            final_columns = ordered_columns + extra_columns
            pivot_df = pivot_df[final_columns]

            # Create Rich Table
            table = Table(title="FBN Yearly Assets Matrix", expand=False)
            table.add_column("Year", style="cyan", no_wrap=True)
            for col in final_columns:
                table.add_column(col, justify="right")
            
            # Add Total column
            table.add_column("Total", justify="right", style="bold magenta")


            for year, row in pivot_df.iterrows():
                row_data = [str(year)]
                total_assets = 0
                for col in final_columns:
                    val = row[col]
                    if pd.notna(val):
                        row_data.append(f"{val:,.2f}")
                        total_assets += val
                    else:
                        row_data.append("-")
                
                row_data.append(f"{total_assets:,.2f}")
                table.add_row(*row_data)

            self.app.console.print(table)
            self.app.skip_render = True

        except Exception as e:
             self.output_content = f"[error]Error listing yearly assets matrix: {e}[/]"

    def add_monthly_data(self):
        self.app.console.clear()
        self.app.console.print("[bold cyan]--- Add/Edit Monthly Data ---[/]")
        
        # 1. Date Selection
        target_date = self.get_target_date()
        if not target_date:
            self.output_content = "[info]Operation cancelled.[/]"
            return

        self.app.console.print(f"[info]Selected Date: {target_date.strftime('%Y-%m-%d')}[/]")

        # 2. Account Loop replaced by Menu Selection
        while True:
            self.app.console.print("\n[bold]Select Account to Edit:[/]")
            for idx, acc in enumerate(self.accounts, 1):
                self.app.console.print(f" {idx}. {acc['name']} ([dim]{acc['currency']}[/dim])")
            
            choice = self.app.console.input("\n[prompt]Select account # (or 'q' to finish) >> [/]").lower()
            
            if choice in ['q', 'quit']:
                break
            
            try:
                idx = int(choice)
                if 1 <= idx <= len(self.accounts):
                    account_info = self.accounts[idx-1]
                    self.process_account_entry(account_info, target_date)
                else:
                    self.app.console.print("[error]Invalid selection.[/]")
            except ValueError:
                self.app.console.print("[error]Invalid input.[/]")
        
        # Refresh Data
        self.load_fbn_data()
        self.output_content = "[success]Data entry completed and reloaded.[/]"

    def get_target_date(self):
        from datetime import datetime, timedelta
        import calendar

        # Default: Last day of previous month
        today = datetime.now()
        first = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month = first - timedelta(days=1)
        default_date_str = last_month.strftime("%Y-%m-%d") # Use full date for internal consistency, user thinks in month/year

        date_input = self.app.console.input(f"[prompt]Enter date (YYYY-MM-DD) or Month/Year (MM/YYYY) [[dim]{default_date_str}[/dim]] >> [/]")
        
        if not date_input:
            return last_month
            
        try:
             # Try YYYY-MM-DD
            return datetime.strptime(date_input, "%Y-%m-%d")
        except ValueError:
            pass
            
        try:
            # Try MM/YYYY -> convert to last day of that month
            month, year = map(int, date_input.split('/'))
            last_day = calendar.monthrange(year, month)[1]
            return datetime(year, month, last_day)
        except ValueError:
            self.app.console.print("[error]Invalid date format.[/]")
            return None

    def process_account_entry(self, account_info, date):
        acc_name = account_info['name']
        currency = account_info['currency']
        
        self.app.console.print(f"\n[bold magenta]--- Account: {acc_name} ({currency}) ---[/]")
        
        # Get existing row if any
        existing_row = pd.Series()
        if not self.df.empty:
            mask = (self.df['date'] == date) & (self.df['account'] == acc_name)
            if mask.any():
                existing_row = self.df[mask].iloc[0]
                
        # 2. Print current asset value if available
        current_asset = existing_row.get('asset', 'N/A')
        if current_asset != 'N/A':
             self.app.console.print(f"Current Asset Value: [bold]{current_asset:,.2f}[/]")
        else:
             self.app.console.print(f"Current Asset Value: [dim]N/A[/]")

        # 3. Values Input
        fields = ['investment', 'deposit', 'interest', 'dividend', 'distribution', 'tax', 'fee', 'other', 'cash', 'asset']
        values = {}
        
        for field in fields:
            default = existing_row.get(field, 0.0) if not existing_row.empty else 0.0
            val_input = self.app.console.input(f"{field.capitalize()} [[dim]{default}[/dim]] >> ")
            try:
                values[field] = float(val_input) if val_input else float(default)
            except ValueError:
                self.app.console.print(f"[warning]Invalid number, using default: {default}[/]")
                values[field] = float(default)

        if acc_name == 'GFZ USD':
            rate_default = existing_row.get('rate', 1.0) if not existing_row.empty else 1.0
            rate_input = self.app.console.input(f"Rate [[dim]{rate_default}[/dim]] >> ")
            try:
                values['rate'] = float(rate_input) if rate_input else float(rate_default)
            except ValueError:
                 values['rate'] = float(rate_default)
        else:
            values['rate'] = 1.0 # Default for CAD

        # 4. Validation
        variation_encaisse = sum([values[k] for k in ['investment', 'deposit', 'interest', 'dividend', 'distribution', 'tax', 'fee', 'other']])
        total_placements = values['asset'] - values['cash']
        
        self.app.console.print("\n[bold]Validation:[/]")
        self.app.console.print(f"Variation Encaisse: [cyan]{variation_encaisse:,.2f}[/]")
        self.app.console.print(f"Total Placements:   [cyan]{total_placements:,.2f}[/]")
        
        confirm = self.app.console.input("[prompt]Confirm these values? (Y/n/r[retry]) >> [/]").lower()
        
        if confirm == 'n':
            self.app.console.print("[info]Skipping this account.[/]")
            return
        elif confirm == 'r':
            return self.process_account_entry(account_info, date) # Recursive retry
            
        # 5. Insert or Replace
        entry_data = {
            'date': date.strftime("%Y-%m-%d"),
            'account': acc_name,
            'portfolio': account_info['portfolio'],
            'currency': currency,
            **values
        }
        
        fbn_db.save_account_entry(entry_data)
        self.app.console.print(f"[success]Saved entry for {acc_name}[/]")

    def get_status(self):
        base = f"{self.emoji} {self.name}"
        if self.account_filter:
            return f"{base} · Accounts: {', '.join(self.account_filter)}"
        return base

    def filter_accounts(self):
        if self.df.empty or 'account' not in self.df.columns:
            self.output_content = "[info]No accounts available to filter.[/]"
            return

        accounts = sorted(a for a in self.df['account'].dropna().unique().tolist())
        if not accounts:
            self.output_content = "[info]No accounts available to filter.[/]"
            return

        result = multi_select(
            self.app.console,
            accounts,
            preselected=self.account_filter,
            title="Select accounts to filter on",
        )
        self.app.skip_render = True

        if result is None:
            self.output_content = ""
            return

        self.account_filter = sorted(result)
        if self.account_filter:
            self.output_content = f"[success]Account filter set: {', '.join(self.account_filter)}[/]"
        else:
            self.output_content = "[success]Account filter cleared.[/]"
        self.app.skip_render = False

    def get_output(self):
        return self.output_content
