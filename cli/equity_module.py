import pandas as pd
from rich.table import Table
from rich.columns import Columns
from base_module import Module
from cli.db import equity_db
from datetime import datetime

class EquityModule(Module):
    name = "EQUITY"
    emoji = "💰"

    def __init__(self, app):
        super().__init__(app)
        self.equity_df = pd.DataFrame()
        self.output_content = ""
        self.current_subset = None  # Store current view for editing
        self.current_date = None    # Store selected date for editing
        self.load_equity_data()

    def load_equity_data(self):
        self.equity_df = equity_db.fetch_equity_data()
        if not self.equity_df.empty:
            self.equity_df['date'] = pd.to_datetime(self.equity_df['date'])
            # Calculated columns
            self.equity_df['balance_cad'] = self.equity_df['balance'] * self.equity_df['rate']
            
            # Special handling for SAT (Satoshis)
            # Assuming rate is BTC price, convert sats to BTC then multiply by rate
            mask_sat = self.equity_df['currency'] == 'SAT'
            self.equity_df.loc[mask_sat, 'balance_cad'] = self.equity_df.loc[mask_sat, 'balance_cad'] / 100_000_000.0
            
            self.equity_df['balance_net'] = self.equity_df['balance_cad'] * (1 - self.equity_df['tax'])
        else:
             # Create empty with expected columns if DB is empty to avoid KeyError later
            self.equity_df = pd.DataFrame(columns=['id', 'date', 'description', 'account', 'category', 'currency', 'rate', 'balance', 'tax', 'balance_cad', 'balance_net'])

        # Sort by Description
        self.equity_df.sort_values('description', key=lambda x: x.str.lower(), inplace=True)

    def handle_command(self, command):
        cmd = command.lower().strip()
        if cmd in ['q', 'quit']:
            from home_module import HomeModule
            self.app.switch_module(HomeModule(self.app))
        elif cmd == 'qq':
            self.app.quit()
        elif cmd in ['h', 'help']:
            self.output_content = '''Equity Commands:
    - a | add    : Add a new entry
    - s | select : Select a date and list its entries
    - l | list   : List entries for the selected date (selects one first if none)
    - e <number> : Edit an entry by its index
    - d <number> : Delete an entry by its index
    - c | copy   : Copy entries from one date to another
    - p | pivot  : Show pivot tables (date x account/category)
    - q | quit   : Return to main menu
    - qq         : Exit to prompt'''
        elif cmd in ['a', 'add']:
            self.add_entry()
        elif cmd in ['s', 'select']:
            self.select_date()
        elif cmd in ['l', 'list']:
            if self.current_date is not None:
                self.show_table_for_date(self.current_date)
            else:
                self.select_date()
        elif cmd in ['c', 'copy']:
            self.copy_entries_for_date()
        elif cmd in ['p', 'pivot']:
            self.show_pivot_tables()
        elif cmd.startswith('e ') or cmd.startswith('edit '):
            # Parse the line number
            parts = cmd.split()
            if len(parts) == 2:
                try:
                    line_num = int(parts[1])
                    self.edit_entry(line_num)
                except ValueError:
                    self.output_content = "[error]Invalid line number.[/]"
            else:
                self.output_content = "[error]Usage: e <line_number>[/]"
        elif cmd.startswith('d ') or cmd.startswith('delete '):
            # Parse the line number for delete
            parts = cmd.split()
            if len(parts) == 2:
                try:
                    line_num = int(parts[1])
                    self.delete_entry(line_num)
                except ValueError:
                    self.output_content = "[error]Invalid line number.[/]"
            else:
                self.output_content = "[error]Usage: d <line_number>[/]"
        elif cmd == "":
            pass
        else:
            self.output_content = f"Unknown command: {command}"

    def get_status(self):
        base = super().get_status()
        if self.current_date is not None:
            date_str = pd.to_datetime(self.current_date).strftime('%Y-%m-%d')
            return f"{base} [{date_str}]"
        return base

    def add_entry(self):
        self.app.console.clear()
        self.app.console.print("[bold cyan]--- Add Equity Entry ---[/]")
        
        default_date_str = datetime.now().strftime("%Y-%m-%d")
        
        while True:
            # 1. Date
            date_in = self.app.console.input(f"Date [[dim]{default_date_str}[/dim]] >> ")
            date_val = date_in if date_in else default_date_str
            
            # 2. Description
            desc_val = self.app.console.input("Description >> ")
            
            # 3. Account
            self.app.console.print("Accounts:\n[1] Personnel,\n[2] Gestion FZ")
            acc_choice = self.app.console.input("Account >> ")
            acc_map = {'1': 'Personnel', '2': 'Gestion FZ', 'personnel': 'Personnel', 'gestion fz': 'Gestion FZ'}
            account_val = acc_map.get(acc_choice.lower(), acc_choice) # Fallback to input if not mapped, though prompts implies strict choice, flexibility is good. User prompt said "choices: ...", usually implies select or type. 
            
            # 4. Category
            self.app.console.print("Categories:\n[1] Bitcoin,\n[2] Cash,\n[3] Immobilier,\n[4] FBN,\n[5] IBKR,\n[6] BZ")
            cat_choice = self.app.console.input("Category >> ")
            cat_map = {'1': 'Bitcoin', '2': 'Cash', '3': 'Immobilier', '4': 'FBN', '5': 'IBKR', '6': 'BZ'}
            # Handle text input or number
            category_val = cat_map.get(cat_choice, cat_choice) # Simplistic mapping, could be more robust
            # Let's clean up case if they typed text
            if category_val.lower() == 'bitcoin': category_val = 'Bitcoin'
            elif category_val.lower() == 'cash': category_val = 'Cash'
            elif category_val.lower() == 'immobilier': category_val = 'Immobilier'
            elif category_val.lower() == 'fbn': category_val = 'FBN'
            elif category_val.lower() == 'ibkr': category_val = 'IBKR'
            
            # 5. Currency
            self.app.console.print("Currency:\n[1] CAD,\n[2] USD,\n[3] SAT")
            cur_choice = self.app.console.input("Currency [[dim]CAD[/dim]] >> ").lower()
            if cur_choice == '2' or cur_choice == 'usd':
                currency_val = 'USD'
            elif cur_choice == '3' or cur_choice == 'sat':
                currency_val = 'SAT'
            else:
                currency_val = 'CAD'
                
            # 6. Rate
            rate_def = "1.0"
            rate_in = self.app.console.input(f"Rate [[dim]{rate_def}[/dim]] >> ")
            try:
                rate_val = float(rate_in) if rate_in else 1.0
            except ValueError:
                rate_val = 1.0
                
            # 7. Balance
            bal_in = self.app.console.input("Balance >> ")
            try:
                balance_val = float(bal_in) if bal_in else 0.0
            except ValueError:
                balance_val = 0.0
                
            # 8. Tax
            tax_in = self.app.console.input("Tax (0.0 - 1.0) [[dim]0.0[/dim]] >> ")
            try:
                tax_val = float(tax_in) if tax_in else 0.0
            except ValueError:
                tax_val = 0.0
                
            # Save
            entry = {
                'date': date_val,
                'description': desc_val,
                'account': account_val,
                'category': category_val,
                'currency': currency_val,
                'rate': rate_val,
                'balance': balance_val,
                'tax': tax_val
            }
            
            if equity_db.save_equity_entry(entry):
                self.app.console.print("[success]Entry added![/]")
            else:
                self.app.console.print("[error]Failed to add entry.[/]")
                
            # Again?
            again = self.app.console.input("\nAdd another with same date? (y/n) >> ").lower()
            if again == 'y':
                default_date_str = date_val
            else:
                break
                
        self.load_equity_data()
        self.output_content = "Data updated."

    def select_date(self):
        if self.equity_df.empty:
            self.output_content = "[info]No equity data found.[/]"
            return

        # Unique dates
        unique_dates = sorted(self.equity_df['date'].unique(), reverse=True)
        
        self.app.console.clear()
        self.app.console.print("[bold cyan]--- Select Date ---[/]")
        
        for i, dt in enumerate(unique_dates, 1):
            dt_str = pd.to_datetime(dt).strftime('%Y-%m-%d')
            self.app.console.print(f"{i}. {dt_str}")
            
        choice = self.app.console.input("\nSelect number >> ")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(unique_dates):
                selected_date = unique_dates[idx]
                self.show_table_for_date(selected_date)
            else:
                self.output_content = "[error]Invalid selection.[/]"
        except ValueError:
             self.output_content = "[error]Invalid input.[/]"
             
    def show_table_for_date(self, date_val):
        # Filter
        mask = self.equity_df['date'] == date_val
        subset = self.equity_df[mask].reset_index(drop=False)  # Keep original index as 'index' column
        
        # Store for editing
        self.current_subset = subset
        self.current_date = date_val
        
        date_str = pd.to_datetime(date_val).strftime('%Y-%m-%d')
        table = Table(title=f"Equity entries for {date_str}", expand=False, row_styles=["", "on #1d2021"])
        
        table.add_column("#", style="dim", justify="right")
        table.add_column("Account", style="cyan")
        table.add_column("Category", style="magenta")
        table.add_column("Desc")
        table.add_column("Curr")
        table.add_column("Bal", justify="right")
        table.add_column("Rate", justify="right")
        table.add_column("Bal CAD", justify="right", style="green")
        table.add_column("Tax", justify="right")
        table.add_column("Bal Net", justify="right", style="bold green")
        
        for i, row in subset.iterrows():
            table.add_row(
                str(i + 1),  # 1-indexed for user display
                str(row['account']),
                str(row['category']),
                str(row['description']),
                str(row['currency']),
                f"{row['balance']:,.2f}",
                f"{row['rate']:.4f}",
                f"{row['balance_cad']:,.2f}",
                f"{row['tax']:.2f}",
                f"{row['balance_net']:,.2f}"
            )
            
        # Add totals
        total_bal_cad = subset['balance_cad'].sum()
        total_bal_net = subset['balance_net'].sum()
        
        table.add_section()
        table.add_row(
            "", "TOTAL", "", "", "", "", "",
            f"{total_bal_cad:,.2f}",
            "",
            f"{total_bal_net:,.2f}",
            style="bold"
        )
        
        self.app.console.clear()
        self.app.console.print(table)
        
        # Table 2: balance_net by account
        account_summary = subset.groupby('account')[['balance_cad', 'balance_net']].sum().reset_index()
        account_summary = account_summary.sort_values('balance_net', ascending=False)
        account_table = Table(title="Balance by Account")
        account_table.add_column("Account", style="cyan")
        account_table.add_column("Balance CAD", justify="right", style="green")
        account_table.add_column("Balance Net", justify="right", style="bold green")
        
        for _, row in account_summary.iterrows():
            account_table.add_row(
                str(row['account']),
                f"{row['balance_cad']:,.2f}",
                f"{row['balance_net']:,.2f}"
            )
        
        # Add total row
        account_table.add_section()
        account_table.add_row("TOTAL", f"{account_summary['balance_cad'].sum():,.2f}", f"{account_summary['balance_net'].sum():,.2f}", style="bold")
        
        self.app.console.print()
        self.app.console.print(account_table)
        
        # Table 3: balance_net by category
        category_summary = subset.groupby('category')[['balance_cad', 'balance_net']].sum().reset_index()
        category_summary = category_summary.sort_values('balance_net', ascending=False)
        category_table = Table(title="Balance by Category")
        category_table.add_column("Category", style="magenta")
        category_table.add_column("Balance CAD", justify="right", style="green")
        category_table.add_column("Balance Net", justify="right", style="bold green")
        
        for _, row in category_summary.iterrows():
            category_table.add_row(
                str(row['category']),
                f"{row['balance_cad']:,.2f}",
                f"{row['balance_net']:,.2f}"
            )
        
        # Add total row
        category_table.add_section()
        category_table.add_row("TOTAL", f"{category_summary['balance_cad'].sum():,.2f}", f"{category_summary['balance_net'].sum():,.2f}", style="bold")
        
        self.app.console.print()
        self.app.console.print(category_table)
        
        self.app.skip_render = True
        self.output_content = "" # Cleared by direct print

    def edit_entry(self, line_num):
        """Edit an existing entry by its display line number"""
        if self.current_subset is None or self.current_subset.empty:
            self.output_content = "[error]No entries to edit. Use 'l' to list entries first.[/]"
            return
        
        # Line numbers are 1-indexed for display
        row_idx = line_num - 1
        
        if row_idx < 0 or row_idx >= len(self.current_subset):
            self.output_content = f"[error]Line {line_num} not found. Valid range: 1-{len(self.current_subset)}[/]"
            return
        
        row = self.current_subset.iloc[row_idx]
        entry_id = int(row['id'])  # Convert to native Python int for SQLite
        
        self.app.console.clear()
        self.app.console.print(f"[bold cyan]--- Edit Entry #{line_num} ---[/]")
        self.app.console.print(f"[dim]Editing: {row['description']} ({row['account']})[/]\n")
        
        # 1. Date
        current_date = pd.to_datetime(row['date']).strftime('%Y-%m-%d')
        date_in = self.app.console.input(f"Date [[dim]{current_date}[/dim]] >> ")
        date_val = date_in if date_in else current_date
        
        # 2. Description
        current_desc = str(row['description'])
        desc_in = self.app.console.input(f"Description [[dim]{current_desc}[/dim]] >> ")
        desc_val = desc_in if desc_in else current_desc
        
        # 3. Account
        current_account = str(row['account'])
        self.app.console.print(f"Accounts:\n[1] Personnel,\n[2] Gestion FZ\n(current: {current_account})")
        acc_choice = self.app.console.input(f"Account [[dim]{current_account}[/dim]] >> ")
        if acc_choice:
            acc_map = {'1': 'Personnel', '2': 'Gestion FZ', 'personnel': 'Personnel', 'gestion fz': 'Gestion FZ'}
            account_val = acc_map.get(acc_choice.lower(), acc_choice)
        else:
            account_val = current_account
        
        # 4. Category
        current_cat = str(row['category'])
        self.app.console.print(f"Categories:\n[1] Bitcoin,\n[2] Cash,\n[3] Immobilier,\n[4] FBN,\n[5] IBKR,\n[6] BZ\n(current: {current_cat})")
        cat_choice = self.app.console.input(f"Category [[dim]{current_cat}[/dim]] >> ")
        if cat_choice:
            cat_map = {'1': 'Bitcoin', '2': 'Cash', '3': 'Immobilier', '4': 'FBN', '5': 'IBKR', '6': 'BZ'}
            category_val = cat_map.get(cat_choice, cat_choice)
            # Clean up case if they typed text
            if category_val.lower() == 'bitcoin': category_val = 'Bitcoin'
            elif category_val.lower() == 'cash': category_val = 'Cash'
            elif category_val.lower() == 'immobilier': category_val = 'Immobilier'
            elif category_val.lower() == 'fbn': category_val = 'FBN'
            elif category_val.lower() == 'ibkr': category_val = 'IBKR'
        else:
            category_val = current_cat
        
        # 5. Currency
        current_currency = str(row['currency'])
        self.app.console.print(f"Currency:\n[1] CAD,\n[2] USD,\n[3] SAT\n(current: {current_currency})")
        cur_choice = self.app.console.input(f"Currency [[dim]{current_currency}[/dim]] >> ").lower()
        if cur_choice:
            if cur_choice == '1' or cur_choice == 'cad':
                currency_val = 'CAD'
            elif cur_choice == '2' or cur_choice == 'usd':
                currency_val = 'USD'
            elif cur_choice == '3' or cur_choice == 'sat':
                currency_val = 'SAT'
            else:
                currency_val = current_currency
        else:
            currency_val = current_currency
            
        # 6. Rate
        current_rate = row['rate']
        rate_in = self.app.console.input(f"Rate [[dim]{current_rate}[/dim]] >> ")
        try:
            rate_val = float(rate_in) if rate_in else current_rate
        except ValueError:
            rate_val = current_rate
            
        # 7. Balance
        current_balance = row['balance']
        bal_in = self.app.console.input(f"Balance [[dim]{current_balance:,.2f}[/dim]] >> ")
        try:
            balance_val = float(bal_in) if bal_in else current_balance
        except ValueError:
            balance_val = current_balance
            
        # 8. Tax
        current_tax = row['tax']
        tax_in = self.app.console.input(f"Tax (0.0 - 1.0) [[dim]{current_tax}[/dim]] >> ")
        try:
            tax_val = float(tax_in) if tax_in else current_tax
        except ValueError:
            tax_val = current_tax
        
        # Show summary and confirm
        self.app.console.print("\n[bold cyan]--- Summary of Changes ---[/]")
        self.app.console.print(f"Date:        {date_val}")
        self.app.console.print(f"Description: {desc_val}")
        self.app.console.print(f"Account:     {account_val}")
        self.app.console.print(f"Category:    {category_val}")
        self.app.console.print(f"Currency:    {currency_val}")
        self.app.console.print(f"Rate:        {rate_val}")
        self.app.console.print(f"Balance:     {balance_val:,.2f}")
        self.app.console.print(f"Tax:         {tax_val}")
        
        confirm = self.app.console.input("\nConfirm update? (y/n) >> ").lower()
        
        if confirm == 'y':
            entry = {
                'date': date_val,
                'description': desc_val,
                'account': account_val,
                'category': category_val,
                'currency': currency_val,
                'rate': float(rate_val),
                'balance': float(balance_val),
                'tax': float(tax_val)
            }
            
            if equity_db.update_equity_entry(entry_id, entry):
                self.app.console.print("[success]Entry updated![/]")
                self.load_equity_data()
                self.output_content = "Data updated."
            else:
                self.app.console.print("[error]Failed to update entry.[/]")
                self.output_content = "Update failed."
        else:
            self.output_content = "Edit cancelled."
        
        # Clear the stored subset after editing (date is kept for the status line)
        self.current_subset = None

    def copy_entries_for_date(self):
        """Copy all entries from a source date to a new target date with balance=0, rate=0"""
        if self.equity_df.empty:
            self.output_content = "[info]No equity data found.[/]"
            return

        # Get unique dates
        unique_dates = sorted(self.equity_df['date'].unique(), reverse=True)
        
        self.app.console.clear()
        self.app.console.print("[bold cyan]--- Copy Entries by Date ---[/]")
        self.app.console.print("[dim]Select source date to copy from:[/]\n")
        
        for i, dt in enumerate(unique_dates, 1):
            dt_str = pd.to_datetime(dt).strftime('%Y-%m-%d')
            self.app.console.print(f"{i}. {dt_str}")
            
        choice = self.app.console.input("\nSelect source date number >> ")
        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(unique_dates):
                self.output_content = "[error]Invalid selection.[/]"
                return
            source_date = unique_dates[idx]
        except ValueError:
            self.output_content = "[error]Invalid input.[/]"
            return
        
        # Prompt for target date
        source_date_str = pd.to_datetime(source_date).strftime('%Y-%m-%d')
        default_target = datetime.now().strftime("%Y-%m-%d")
        
        self.app.console.print(f"\n[dim]Source date: {source_date_str}[/]")
        target_in = self.app.console.input(f"Target date [[dim]{default_target}[/dim]] >> ")
        target_date = target_in if target_in else default_target
        
        # Get entries for source date
        mask = self.equity_df['date'] == source_date
        source_entries = self.equity_df[mask]
        
        if source_entries.empty:
            self.output_content = "[error]No entries found for source date.[/]"
            return
        
        # Create new entries
        new_entries = []
        for _, row in source_entries.iterrows():
            new_entry = {
                'date': target_date,
                'description': row['description'],
                'account': row['account'],
                'category': row['category'],
                'currency': row['currency'],
                'rate': 0.0,
                'balance': 0.0,
                'tax': row['tax']
            }
            new_entries.append(new_entry)
        
        # Show summary and confirm
        self.app.console.print(f"\n[bold cyan]Will copy {len(new_entries)} entries:[/]")
        self.app.console.print(f"  From: {source_date_str}")
        self.app.console.print(f"  To:   {target_date}")
        self.app.console.print(f"  With: balance=0, rate=0")
        
        confirm = self.app.console.input("\nConfirm copy? (y/n) >> ").lower()
        
        if confirm == 'y':
            if equity_db.save_equity_entries(new_entries):
                self.app.console.print(f"[success]{len(new_entries)} entries copied![/]")
                self.load_equity_data()
                self.output_content = f"Copied {len(new_entries)} entries to {target_date}."
            else:
                self.app.console.print("[error]Failed to copy entries.[/]")
                self.output_content = "Copy failed."
        else:
            self.output_content = "Copy cancelled."

    def show_pivot_tables(self):
        """Display four pivot tables: balance_cad and balance_net for both account and category"""
        if self.equity_df.empty:
            self.output_content = "[info]No equity data found.[/]"
            return

        # Format dates for display
        df = self.equity_df.copy()
        df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
        
        # Pivot Tables for balance_cad
        pivot_account_cad = df.pivot_table(
            index='date_str', 
            columns='account', 
            values='balance_cad', 
            aggfunc='sum', 
            fill_value=0
        ).sort_index(ascending=False)
        
        pivot_category_cad = df.pivot_table(
            index='date_str', 
            columns='category', 
            values='balance_cad', 
            aggfunc='sum', 
            fill_value=0
        ).sort_index(ascending=False)
        
        # Pivot Tables for balance_net
        pivot_account_net = df.pivot_table(
            index='date_str', 
            columns='account', 
            values='balance_net', 
            aggfunc='sum', 
            fill_value=0
        ).sort_index(ascending=False)
        
        pivot_category_net = df.pivot_table(
            index='date_str', 
            columns='category', 
            values='balance_net', 
            aggfunc='sum', 
            fill_value=0
        ).sort_index(ascending=False)
        
        # Build Table 1: Balance CAD by Account
        table_cad_account = Table(title="Balance CAD by Account")
        table_cad_account.add_column("Date", style="dim")
        for col in pivot_account_cad.columns:
            table_cad_account.add_column(str(col), justify="right", style="green")
        table_cad_account.add_column("Total", justify="right", style="bold cyan")
        
        for date_str in pivot_account_cad.index:
            row_values = [date_str]
            row_total = 0
            for col in pivot_account_cad.columns:
                val = pivot_account_cad.loc[date_str, col]
                row_values.append(f"{val:,.0f}")
                row_total += val
            row_values.append(f"{row_total:,.0f}")
            table_cad_account.add_row(*row_values)
        
        # Build Table 2: Balance CAD by Category
        table_cad_category = Table(title="Balance CAD by Category")
        table_cad_category.add_column("Date", style="dim")
        for col in pivot_category_cad.columns:
            table_cad_category.add_column(str(col), justify="right", style="orange1")
        table_cad_category.add_column("Total", justify="right", style="bold cyan")
        
        for date_str in pivot_category_cad.index:
            row_values = [date_str]
            row_total = 0
            for col in pivot_category_cad.columns:
                val = pivot_category_cad.loc[date_str, col]
                row_values.append(f"{val:,.0f}")
                row_total += val
            row_values.append(f"{row_total:,.0f}")
            table_cad_category.add_row(*row_values)
        
        # Build Table 3: Balance Net by Account
        table_net_account = Table(title="Balance Net by Account")
        table_net_account.add_column("Date", style="dim")
        for col in pivot_account_net.columns:
            table_net_account.add_column(str(col), justify="right", style="green")
        table_net_account.add_column("Total", justify="right", style="bold cyan")
        
        for date_str in pivot_account_net.index:
            row_values = [date_str]
            row_total = 0
            for col in pivot_account_net.columns:
                val = pivot_account_net.loc[date_str, col]
                row_values.append(f"{val:,.0f}")
                row_total += val
            row_values.append(f"{row_total:,.0f}")
            table_net_account.add_row(*row_values)
        
        # Build Table 4: Balance Net by Category
        table_net_category = Table(title="Balance Net by Category")
        table_net_category.add_column("Date", style="dim")
        for col in pivot_category_net.columns:
            table_net_category.add_column(str(col), justify="right", style="orange1")
        table_net_category.add_column("Total", justify="right", style="bold cyan")
        
        for date_str in pivot_category_net.index:
            row_values = [date_str]
            row_total = 0
            for col in pivot_category_net.columns:
                val = pivot_category_net.loc[date_str, col]
                row_values.append(f"{val:,.0f}")
                row_total += val
            row_values.append(f"{row_total:,.0f}")
            table_net_category.add_row(*row_values)
        
        # Display: CAD tables on top, Net tables on bottom
        self.app.console.clear()
        cad_columns = Columns([table_cad_account, table_cad_category], equal=True, expand=True)
        net_columns = Columns([table_net_account, table_net_category], equal=True, expand=True)
        self.app.console.print(cad_columns)
        self.app.console.print()
        self.app.console.print(net_columns)
        
        self.app.skip_render = True
        self.output_content = ""

    def delete_entry(self, line_num):
        """Delete an existing entry by its display line number"""
        if self.current_subset is None or self.current_subset.empty:
            self.output_content = "[error]No entries to delete. Use 'l' to list entries first.[/]"
            return
        
        # Line numbers are 1-indexed for display
        row_idx = line_num - 1
        
        if row_idx < 0 or row_idx >= len(self.current_subset):
            self.output_content = f"[error]Line {line_num} not found. Valid range: 1-{len(self.current_subset)}[/]"
            return
        
        row = self.current_subset.iloc[row_idx]
        entry_id = int(row['id'])
        
        self.app.console.clear()
        self.app.console.print(f"[bold red]--- Delete Entry #{line_num} ---[/]")
        self.app.console.print(f"\n[bold]Entry details:[/]")
        self.app.console.print(f"  Date:        {pd.to_datetime(row['date']).strftime('%Y-%m-%d')}")
        self.app.console.print(f"  Description: {row['description']}")
        self.app.console.print(f"  Account:     {row['account']}")
        self.app.console.print(f"  Category:    {row['category']}")
        self.app.console.print(f"  Currency:    {row['currency']}")
        self.app.console.print(f"  Rate:        {row['rate']}")
        self.app.console.print(f"  Balance:     {row['balance']:,.2f}")
        self.app.console.print(f"  Tax:         {row['tax']}")
        
        confirm = self.app.console.input("\n[bold red]Confirm DELETE?[/] (y/n) >> ").lower()
        
        if confirm == 'y':
            if equity_db.delete_equity_entry(entry_id):
                self.app.console.print("[success]Entry deleted![/]")
                self.load_equity_data()
                self.output_content = "Entry deleted."
            else:
                self.app.console.print("[error]Failed to delete entry.[/]")
                self.output_content = "Delete failed."
        else:
            self.output_content = "Delete cancelled."
        
        # Clear stored subset after deletion (date is kept for the status line)
        self.current_subset = None

    def get_output(self):
        return self.output_content
