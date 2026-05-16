"""Cross-platform terminal UI helpers."""
import sys


# Logical key names returned by _read_key
KEY_UP = 'UP'
KEY_DOWN = 'DOWN'
KEY_ENTER = 'ENTER'
KEY_SPACE = 'SPACE'
KEY_ESC = 'ESC'
KEY_CTRL_C = 'CTRL_C'


if sys.platform == 'win32':
    import msvcrt

    def _read_key():
        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):
            # Special key prefix; next byte identifies the key
            ch2 = msvcrt.getch()
            if ch2 == b'H':
                return KEY_UP
            if ch2 == b'P':
                return KEY_DOWN
            return None
        if ch == b'\x1b':
            return KEY_ESC
        if ch in (b'\r', b'\n'):
            return KEY_ENTER
        if ch == b' ':
            return KEY_SPACE
        if ch == b'\x03':
            return KEY_CTRL_C
        try:
            return ch.decode('utf-8')
        except UnicodeDecodeError:
            return None
else:
    import os
    import select
    import termios
    import tty

    def _read_key():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            b = os.read(fd, 1)
            if b == b'\x1b':
                r, _, _ = select.select([fd], [], [], 0.05)
                if r:
                    b += os.read(fd, 2)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        if b == b'\x1b[A':
            return KEY_UP
        if b == b'\x1b[B':
            return KEY_DOWN
        if b == b'\x1b':
            return KEY_ESC
        if b in (b'\r', b'\n'):
            return KEY_ENTER
        if b == b' ':
            return KEY_SPACE
        if b == b'\x03':
            return KEY_CTRL_C
        return b.decode('utf-8', errors='replace')


def multi_select(console, options, preselected=None, title="Select"):
    """Interactive multi-select picker.

    Returns the chosen options as a list (preserving `options` order),
    or None if cancelled.
    """
    if not sys.stdin.isatty():
        console.print("[error]Interactive picker requires a TTY.[/]")
        return None

    selected = set(preselected or [])
    cursor = 0

    def render():
        console.clear()
        console.print(f"[bold]{title}[/]")
        console.print("[dim]↑/↓ navigate · Space toggle · Enter confirm · Esc/q cancel[/]")
        console.print()
        for i, opt in enumerate(options):
            mark = "[X]" if opt in selected else "[ ]"
            prefix = "›" if i == cursor else " "
            style = "bright_yellow" if i == cursor else "base"
            console.print(f"[{style}]{prefix} {mark} {opt}[/]")

    while True:
        render()
        key = _read_key()
        if key == KEY_UP:
            cursor = (cursor - 1) % len(options)
        elif key == KEY_DOWN:
            cursor = (cursor + 1) % len(options)
        elif key == KEY_SPACE:
            opt = options[cursor]
            if opt in selected:
                selected.remove(opt)
            else:
                selected.add(opt)
        elif key == KEY_ENTER:
            return [o for o in options if o in selected]
        elif key in (KEY_ESC, KEY_CTRL_C, 'q'):
            return None
