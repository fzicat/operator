class Module:
    name = "MODULE"
    emoji = "•"

    def __init__(self, app):
        self.app = app

    def handle_command(self, command):
        raise NotImplementedError

    def get_output(self):
        raise NotImplementedError

    def get_status(self):
        return f"{self.emoji} {self.name}"
