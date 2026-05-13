import pandas as pd
from rich.table import Table

from base_module import SubModule

GRUVBOX = {
    'bg':       '#282828',
    'bg_soft':  '#3c3836',
    'fg':       '#ebdbb2',
    'gray':     '#a89984',
    'red':      '#fb4934',
    'green':    '#b8bb26',
    'yellow':   '#fabd2f',
    'blue':     '#83a598',
    'purple':   '#d3869b',
    'aqua':     '#8ec07c',
    'orange':   '#fe8019',
}


def apply_gruvbox_style():
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        'figure.facecolor':   GRUVBOX['bg'],
        'axes.facecolor':     GRUVBOX['bg'],
        'axes.edgecolor':     GRUVBOX['gray'],
        'axes.labelcolor':    GRUVBOX['fg'],
        'axes.titlecolor':    GRUVBOX['orange'],
        'axes.titlesize':     14,
        'axes.titleweight':   'bold',
        'xtick.color':        GRUVBOX['fg'],
        'ytick.color':        GRUVBOX['fg'],
        'text.color':         GRUVBOX['fg'],
        'grid.color':         GRUVBOX['bg_soft'],
        'grid.linestyle':     '--',
        'grid.alpha':         0.5,
        'savefig.facecolor':  GRUVBOX['bg'],
        'savefig.edgecolor':  GRUVBOX['bg'],
        'legend.facecolor':   GRUVBOX['bg_soft'],
        'legend.edgecolor':   GRUVBOX['gray'],
        'legend.labelcolor':  GRUVBOX['fg'],
    })


class StatsSubModule(SubModule):
    name = "STATS"
    emoji = "📈"

    def __init__(self, parent):
        super().__init__(parent)
        self.output_content = "STATS sub-module active. Type 'h' for commands."

    def handle_command(self, command):
        cmd = command.lower().strip()
        if cmd in ('h', 'help'):
            self.output_content = '''STATS commands:
        - D   | day        > Daily PnL stats (table)
        - W   | week       > Weekly PnL stats (table)
        - PD  | plot day   > Plot daily PnL (bar)
        - PW  | plot week  > Plot weekly PnL (bar)
        - PC  | plot cum   > Plot cumulative PnL (line)
        - OP  | outstanding premium > Plot outstanding short option premium (bar)
        - H   | help       > Show this message
        - Q   | quit       > Return to IBKR module
        - QQ  | quit quit  > Exit the application'''
        elif cmd in ('d', 'day', 'daily'):
            self._stats_daily_table()
        elif cmd in ('w', 'week', 'weekly'):
            self._stats_weekly_table()
        elif cmd in ('pd', 'plot day', 'plot daily'):
            self._plot_daily()
        elif cmd in ('pw', 'plot week', 'plot weekly'):
            self._plot_weekly()
        elif cmd in ('pc', 'plot cum', 'plot cumulative'):
            self._plot_cumulative()
        elif cmd in ('op', 'outstanding premium'):
            self._plot_outstanding_premium()
        elif cmd in ('qq', 'quit quit'):
            self.app.quit()
        elif cmd == "":
            pass
        else:
            self.output_content = f"Unknown STATS command: {command}\nType 'help' for valid commands."

    # ----- data series -----

    def _daily_series(self):
        df = self.parent.trades_df
        if df.empty:
            return pd.Series(dtype=float)
        df = df.copy()
        df['dateTime'] = pd.to_datetime(df['dateTime']).dt.tz_localize(None)
        df['date_only'] = df['dateTime'].dt.normalize()
        daily = df.groupby('date_only')['realized_pnl'].sum()
        if daily.empty:
            return daily
        start = pd.Timestamp('2026-01-05')
        min_date = max(start, daily.index.min()) if daily.index.min() > start else start
        max_date = daily.index.max()
        full = pd.date_range(start=min_date, end=max_date, freq='D')
        daily = daily.reindex(full, fill_value=0.0)
        mask = (daily.index.dayofweek < 5) | (daily != 0)
        return daily[mask]

    def _weekly_series(self):
        df = self.parent.trades_df
        if df.empty:
            return pd.Series(dtype=float)
        df = df.copy()
        df['dateTime'] = pd.to_datetime(df['dateTime']).dt.tz_localize(None)
        df = df.set_index('dateTime')
        weekly = df['realized_pnl'].resample('W-FRI').sum()
        weekly = weekly[weekly.index >= pd.Timestamp('2026-01-09')]
        if not weekly.empty:
            full = pd.date_range(start=weekly.index.min(), end=weekly.index.max(), freq='W-FRI')
            weekly = weekly.reindex(full, fill_value=0.0)
        return weekly

    # ----- text tables (reuse parent's renderer) -----

    def _stats_daily_table(self):
        self.parent.stats_daily()
        self.output_content = self.parent.output_content
        self.parent.output_content = ""

    def _stats_weekly_table(self):
        self.parent.stats_weekly()
        self.output_content = self.parent.output_content
        self.parent.output_content = ""

    # ----- plotting -----

    def _show(self, label):
        try:
            import matplotlib.pyplot as plt
            plt.tight_layout()
            plt.show()
            plt.close('all')
            self.output_content = f"[info]{label} plot closed.[/]"
        except Exception as e:
            self.output_content = f"[error]Plot display error: {e}[/]"

    def _plot_daily(self):
        try:
            daily = self._daily_series()
            if daily.empty:
                self.output_content = "[info]No data to plot.[/]"
                return
            import matplotlib.pyplot as plt
            apply_gruvbox_style()
            fig, ax = plt.subplots(figsize=(11, 5))
            colors = [GRUVBOX['green'] if v > 0 else GRUVBOX['red'] if v < 0 else GRUVBOX['gray'] for v in daily.values]
            ax.bar(daily.index, daily.values, color=colors, width=0.8, edgecolor=GRUVBOX['bg_soft'], linewidth=0.5)
            ax.axhline(0, color=GRUVBOX['fg'], linewidth=0.8)
            ax.set_title("Daily Realized PnL")
            ax.set_ylabel("PnL ($)")
            ax.grid(True, axis='y')
            fig.autofmt_xdate()
            self._show("Daily PnL")
        except Exception as e:
            self.output_content = f"[error]Plot error: {e}[/]"

    def _plot_weekly(self):
        try:
            weekly = self._weekly_series()
            if weekly.empty:
                self.output_content = "[info]No data to plot.[/]"
                return
            import matplotlib.pyplot as plt
            apply_gruvbox_style()
            fig, ax = plt.subplots(figsize=(11, 5))
            colors = [GRUVBOX['green'] if v > 0 else GRUVBOX['red'] if v < 0 else GRUVBOX['gray'] for v in weekly.values]
            ax.bar(weekly.index, weekly.values, color=colors, width=5, edgecolor=GRUVBOX['bg_soft'], linewidth=0.5)
            ax.axhline(0, color=GRUVBOX['fg'], linewidth=0.8)
            ax.set_title("Weekly Realized PnL (W-FRI)")
            ax.set_ylabel("PnL ($)")
            ax.grid(True, axis='y')
            fig.autofmt_xdate()
            self._show("Weekly PnL")
        except Exception as e:
            self.output_content = f"[error]Plot error: {e}[/]"

    def _outstanding_premium_series(self):
        df = self.parent.trades_df
        if df.empty:
            return pd.DataFrame()
        df = df.copy()
        df['dateTime'] = pd.to_datetime(df['dateTime']).dt.tz_localize(None)
        df = df[df['putCall'].isin(['C', 'P'])].sort_values('dateTime')
        if df.empty:
            return pd.DataFrame()

        inventory = {}
        start = pd.Timestamp('2026-01-01').normalize()
        end = pd.Timestamp.now().normalize()
        all_dates = pd.date_range(start=start, end=end, freq='D')
        all_dates = all_dates[all_dates.dayofweek < 5]

        events = df.to_dict('records')
        ev_idx = 0
        rows = []

        for d in all_dates:
            cutoff = d + pd.Timedelta(days=1)
            while ev_idx < len(events) and events[ev_idx]['dateTime'] < cutoff:
                t = events[ev_idx]
                ev_idx += 1
                symbol = t['symbol']
                try:
                    qty = float(t['quantity'])
                    price = float(t['tradePrice'])
                except (TypeError, ValueError):
                    continue
                mult = t.get('multiplier')
                mult = float(mult) if mult not in (None, '', 0) else 100.0
                put_call = t['putCall']
                oc = t.get('openCloseIndicator')

                if oc == 'O' and qty < 0:
                    inventory.setdefault(symbol, {'put_call': put_call, 'lots': []})
                    inventory[symbol]['lots'].append({'qty': abs(qty), 'premium_per_unit': price * mult})
                elif oc == 'C' and qty > 0 and symbol in inventory:
                    remaining = qty
                    lots = inventory[symbol]['lots']
                    while remaining > 0 and lots:
                        lot = lots[0]
                        if lot['qty'] <= remaining + 1e-9:
                            remaining -= lot['qty']
                            lots.pop(0)
                        else:
                            lot['qty'] -= remaining
                            remaining = 0

            call_prem = 0.0
            put_prem = 0.0
            for info in inventory.values():
                total = sum(l['qty'] * l['premium_per_unit'] for l in info['lots'])
                if info['put_call'] == 'C':
                    call_prem += total
                else:
                    put_prem += total
            rows.append({'date': d, 'call': call_prem, 'put': put_prem})

        return pd.DataFrame(rows).set_index('date')

    def _plot_outstanding_premium(self):
        try:
            data = self._outstanding_premium_series()
            if data.empty:
                self.output_content = "[info]No data to plot.[/]"
                return

            table = Table(title="Outstanding Short Option Premium", expand=False)
            table.add_column("Date", style="cyan")
            table.add_column("Call", justify="right", style="red")
            table.add_column("Put", justify="right", style="green")
            table.add_column("Total", justify="right", style="bold yellow")
            for d, row in data.iterrows():
                total = row['call'] + row['put']
                table.add_row(
                    d.strftime("%Y-%m-%d"),
                    f"{row['call']:,.2f}" if row['call'] else "-",
                    f"{row['put']:,.2f}" if row['put'] else "-",
                    f"{total:,.2f}" if total else "-",
                )
            self.app.console.print(table)
            self.app.skip_render = True

            import matplotlib.pyplot as plt
            import numpy as np
            apply_gruvbox_style()
            fig, ax = plt.subplots(figsize=(13, 5))
            x = np.arange(len(data.index))
            width = 0.4
            ax.bar(x - width / 2, data['put'].values, width=width,
                   color=GRUVBOX['green'], edgecolor=GRUVBOX['bg_soft'], linewidth=0.5, label='Put')
            ax.bar(x + width / 2, data['call'].values, width=width,
                   color=GRUVBOX['red'], edgecolor=GRUVBOX['bg_soft'], linewidth=0.5, label='Call')
            ax.set_title("Outstanding Short Option Premium")
            ax.set_ylabel("Premium ($)")
            step = max(1, len(x) // 20)
            ax.set_xticks(x[::step])
            ax.set_xticklabels([d.strftime('%Y-%m-%d') for d in data.index[::step]], rotation=45, ha='right')
            ax.grid(True, axis='y')

            ax2 = ax.twinx()
            totals = data['call'].values + data['put'].values
            ax2.plot(x, totals, color=GRUVBOX['blue'], linewidth=2,
                     marker='o', markersize=3, markerfacecolor=GRUVBOX['blue'],
                     markeredgecolor=GRUVBOX['blue'], label='Total')
            ax2.set_ylabel("Total Premium ($)", color=GRUVBOX['blue'])
            ax2.tick_params(axis='y', colors=GRUVBOX['blue'])
            ax2.spines['right'].set_color(GRUVBOX['blue'])

            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2)

            self._show("Outstanding Premium")
        except Exception as e:
            self.output_content = f"[error]Plot error: {e}[/]"

    def _plot_cumulative(self):
        try:
            daily = self._daily_series()
            if daily.empty:
                self.output_content = "[info]No data to plot.[/]"
                return
            cum = daily.cumsum()
            import matplotlib.pyplot as plt
            apply_gruvbox_style()
            fig, ax = plt.subplots(figsize=(11, 5))
            ax.plot(cum.index, cum.values, color=GRUVBOX['orange'], linewidth=2,
                    marker='o', markersize=3, markerfacecolor=GRUVBOX['yellow'],
                    markeredgecolor=GRUVBOX['orange'])
            ax.fill_between(cum.index, cum.values, 0, where=(cum.values >= 0),
                            color=GRUVBOX['green'], alpha=0.18, interpolate=True)
            ax.fill_between(cum.index, cum.values, 0, where=(cum.values < 0),
                            color=GRUVBOX['red'], alpha=0.18, interpolate=True)
            ax.axhline(0, color=GRUVBOX['fg'], linewidth=0.8)
            ax.set_title("Cumulative Realized PnL")
            ax.set_ylabel("Cumulative PnL ($)")
            ax.grid(True, axis='y')
            fig.autofmt_xdate()
            self._show("Cumulative PnL")
        except Exception as e:
            self.output_content = f"[error]Plot error: {e}[/]"
