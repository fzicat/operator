class Module:
    name = "MODULE"
    emoji = "•"

    def __init__(self, app):
        self.app = app
        self.output_content = ""
        self.active_submodule = None

    def handle_command(self, command):
        if self.active_submodule is not None:
            cmd = command.lower().strip()
            if cmd == 'q':
                self.exit_submodule()
                return
            self.active_submodule.handle_command(command)
            return
        raise NotImplementedError

    def enter_submodule(self, submodule):
        self.active_submodule = submodule
        self.output_content = ""

    def exit_submodule(self):
        self.active_submodule = None
        self.output_content = ""

    def get_output(self):
        if self.active_submodule is not None:
            return self.active_submodule.get_output()
        return self.output_content

    def clear_output(self):
        if self.active_submodule is not None:
            self.active_submodule.clear_output()
        else:
            self.output_content = ""

    def get_status(self):
        return f"{self.emoji} {self.name}"

    def get_status_chain(self):
        chain = [self.get_status()]
        if self.active_submodule is not None:
            chain.extend(self.active_submodule.get_status_chain())
        return chain


class SubModule(Module):
    """Lives under a parent Module. 'q' returns to the parent (handled by parent)."""

    def __init__(self, parent):
        super().__init__(parent.app)
        self.parent = parent
