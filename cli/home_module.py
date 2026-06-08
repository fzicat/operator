from base_module import Module

class HomeModule(Module):
    name = "HOME"
    emoji = "🏠"

    def __init__(self, app):
        super().__init__(app)
        self.output_content = ""

    def handle_command(self, command):
        cmd = command.lower().strip()
        if cmd in ['q', 'qq','quit']:
            self.app.quit()
        elif cmd in ['h', 'help']:
            self.output_content = "Available commands:\n - ibkr (i): Switch to IBKR module\n - fbn (f) : Switch to FBN module\n - equity (e): Switch to Equity module\n - bitcoin (b): Switch to Bitcoin module\n - quit (q): Exit the application\n - help (h): Show this message"
        elif cmd in ['i', 'ibkr']:
            # Local import to avoid circular dependency
            from ibkr_module import IBKRModule
            self.app.switch_module(IBKRModule(self.app))
        elif cmd in ['f', 'fbn']:
            from fbn_module import FBNModule
            self.app.switch_module(FBNModule(self.app))
        elif cmd in ['e', 'equity']:
            from equity_module import EquityModule
            self.app.switch_module(EquityModule(self.app))
        elif cmd in ['b', 'bitcoin']:
            from bitcoin_module import BitcoinModule
            self.app.switch_module(BitcoinModule(self.app))
        elif cmd == "":
            pass
        else:
            self.output_content = f"Unknown command: {command}\nType 'help' for valid commands."

    def get_output(self):
        return self.output_content
