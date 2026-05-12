import sys
import os
import argparse

# Add parent directory to path for shared module access
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.text import Text
from rich.theme import Theme

from shared.supabase_client import login, is_authenticated
from home_module import HomeModule


class TradeToolsApp:
    def __init__(self, auto_login=None, auto_password=None, auto_module=None):
        # Store auto-login credentials
        self.auto_login = auto_login
        self.auto_password = auto_password
        self.auto_module = auto_module
        
        # Gruvbox theme definition
        gruvbox_theme = Theme({
            "base": "#ebdbb2 on #282828",
            "header.text": "bold #d79921",
            "header.bg": "#3c3836",
            "panel.border": "#a89984",
            "prompt": "bold #fabd2f",
            "error": "bold #cc241d",
            "info": "#83a598",
            "success": "bold #b8bb26",
            # Gruvbox colors
            "dark0_hard": "#1d2021",
            "dark0": "#282828",
            "dark0_soft": "#32302f",
            "dark1": "#3c3836",
            "dark2": "#504945",
            "dark3": "#665c54",
            "dark4": "#7c6f64",
            # Light colors
            "light0_hard": "#f9f5d7",
            "light0": "#fbf1c7",
            "light0_soft": "#f2e5bc",
            "light1": "#ebdbb2",
            "light2": "#d5c4a1",
            "light3": "#bdae93",
            "light4": "#a89984",
            # Neutral colors
            "neutral_red": "#cc241d",
            "neutral_green": "#98971a",
            "neutral_yellow": "#d79921",
            "neutral_blue": "#458588",
            "neutral_purple": "#b16286",
            "neutral_aqua": "#689d6a",
            "neutral_orange": "#d65d0e",
            # Bright colors
            "bright_red": "#fb4934",
            "bright_green": "#b8bb26",
            "bright_yellow": "#fabd2f",
            "bright_blue": "#83a598",
            "bright_purple": "#d3869b",
            "bright_aqua": "#8ec07c",
            "bright_orange": "#fe8019",
            # Faded colors
            "faded_red": "#9d0006",
            "faded_green": "#79740e",
            "faded_yellow": "#b57614",
            "faded_blue": "#076678",
            "faded_purple": "#8f3f71",
            "faded_aqua": "#427b58",
            "faded_orange": "#af3a03"
        })
        self.console = Console(theme=gruvbox_theme, style="base")
        self.running = True
        self.active_module = None
        self.skip_render = False

    def authenticate(self) -> bool:
        """Prompt user for login credentials and authenticate with Supabase."""
        self.console.print()
        self.console.print("[header.text]TradeTools v3 - Login[/]")
        self.console.print()

        # If auto-login credentials provided, use them
        if self.auto_login and self.auto_password:
            try:
                self.console.print("[info]Auto-authenticating...[/]")
                result = login(self.auto_login, self.auto_password)
                if result and result.get("user"):
                    self.console.print(f"[success]Welcome, {result['user'].email}![/]")
                    return True
                else:
                    self.console.print("[error]Auto-login failed. Falling back to manual login.[/]")
            except Exception as e:
                self.console.print(f"[error]Auto-login error: {e}. Falling back to manual login.[/]")

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                email = self.console.input("[prompt]Email: [/]")
                password = self.console.input("[prompt]Password: [/]", password=True)

                self.console.print("[info]Authenticating...[/]")
                result = login(email, password)

                if result and result.get("user"):
                    self.console.print(f"[success]Welcome, {result['user'].email}![/]")
                    return True
                else:
                    self.console.print("[error]Login failed. Please try again.[/]")

            except Exception as e:
                remaining = max_attempts - attempt - 1
                if remaining > 0:
                    self.console.print(f"[error]Authentication error: {e}[/]")
                    self.console.print(f"[info]Attempts remaining: {remaining}[/]")
                else:
                    self.console.print(f"[error]Authentication failed: {e}[/]")

        return False

    def switch_module(self, module):
        self.active_module = module

    def _switch_to_module(self, module_name):
        """Switch to a module by name."""
        module_name = module_name.lower()
        if module_name == 'ibkr':
            from ibkr_module import IBKRModule
            self.switch_module(IBKRModule(self))
        elif module_name == 'fbn':
            from fbn_module import FBNModule
            self.switch_module(FBNModule(self))
        elif module_name == 'equity':
            from equity_module import EquityModule
            self.switch_module(EquityModule(self))

    def _render_prompt_block(self):
        """Render status bar, top line, bottom line, then put cursor on prompt row."""
        width = max(1, self.console.size.width - 1)
        line = "─" * width
        self.console.print()  # blank line above status bar
        status_text = " › ".join(self.active_module.get_status_chain())
        self.console.print(f"[bright_blue]{status_text}[/]")
        self.console.print(f"[bright_orange]{line}[/]")

        # Reserve next row for the bottom line, then bring cursor back up to prompt row
        sys.stdout.write("\n")
        self.console.print(f"[bright_orange]{line}[/]", end="")
        sys.stdout.write("\x1b[1A\r")
        sys.stdout.flush()

        command = self.console.input("[bright_orange]❯[/] ")

        # After Enter, cursor sits at start of the bottom-line row.
        # Drop 3 lines below (with newlines so the terminal scrolls if needed)
        # to clear the horizontal line and leave breathing room above output.
        sys.stdout.write("\n\n\n")
        sys.stdout.flush()
        return command

    def _render_output(self):
        """Print module output below the prompt block, without clearing screen."""
        if self.skip_render:
            # Module already printed directly during handle_command
            self.skip_render = False
            self.active_module.clear_output()
            return

        output = self.active_module.get_output()
        if output is None or output == "":
            return

        if isinstance(output, str):
            self.console.print(Text.from_markup(output))
        else:
            self.console.print(output)
        self.active_module.clear_output()

    def _print_welcome(self):
        self.console.print()
        self.console.print("[bright_yellow]Welcome to TradeTools v3[/]")
        self.console.print("Type [bright_orange]help[/] or [bright_orange]h[/] for a list of commands.")

    def run(self):
        # Authenticate before proceeding
        if not self.authenticate():
            self.console.print("[error]Authentication failed. Exiting.[/]")
            return

        # Initialize the home module after authentication
        self.active_module = HomeModule(self)

        # If auto-module specified, switch to it
        if self.auto_module:
            self._switch_to_module(self.auto_module)

        self._print_welcome()

        while self.running:
            try:
                command = self._render_prompt_block()
                self.process_command(command)
                if not self.running:
                    break
                self._render_output()
            except KeyboardInterrupt:
                self.quit()
                break
            except EOFError:
                self.quit()
                break

    def process_command(self, command):
        self.active_module.handle_command(command)

    def quit(self):
        self.running = False
        self.console.print("[error]Goodbye![/]")


def parse_args():
    parser = argparse.ArgumentParser(description='TradeTools v3 - CLI Trading Application')
    parser.add_argument('-l', '--login', type=str, help='Email for auto-login')
    parser.add_argument('-p', '--password', type=str, help='Password for auto-login')
    parser.add_argument('-m', '--module', type=str, choices=['ibkr', 'fbn', 'equity'],
                        help='Module to open directly (ibkr, fbn, or equity)')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    app = TradeToolsApp(
        auto_login=args.login,
        auto_password=args.password,
        auto_module=args.module
    )
    app.run()
