"""Lightweight token-based printer for all UI output with double buffering."""

from __future__ import annotations

import os
import re
import shutil
import sys
import termios
import tty
from contextlib import contextmanager
from typing import ClassVar, TextIO

# Token to ANSI code mapping
TOKEN_MAP = {
    # Text formatting
    "{b}": "\033[1;33m",  # Bold + Yellow (highlighted text, fuzzy match chars)
    "{/b}": "\033[22m\033[39m",  # Reset bold + foreground
    "{dim}": "\033[90m",  # Gray (bright black) - secondary/de-emphasized text
    "{text}": "\033[0m\033[39m",  # Full reset - normal text
    "{reset}": "\033[0m\033[39m\033[49m",  # Complete reset of all formatting
    "{/fg}": "\033[39m",  # Reset foreground color only
    # Headings
    "{h1}": "\033[1;38;5;208m",  # Bold + Orange (primary headings)
    "{h2}": "\033[1;34m",  # Bold + Blue (secondary headings)
    # Selection
    "{section}": "\033[1m\033[48;5;236m",  # Bold + dark gray background
    "{/section}": "\033[0m",  # Full reset - end of selected section
    # Strikethrough (for deleted items)
    "{strike}": "\033[48;5;52m",  # Dark red background
    "{/strike}": "\033[49m",  # Reset background
    # Screen control
    "{clear_screen}": "\033[2J",
    "{clear_line}": "\033[2K",
    "{home}": "\033[H",
    "{clear_below}": "\033[0J",
    "{hide_cursor}": "\033[?25l",
    "{show_cursor}": "\033[?25h",
    # Input cursor
    "{cursor}": "\033[7m \033[27m",  # Reverse video space as cursor block
}


class UI:
    """Double-buffered terminal UI with token-based formatting."""

    _buffer: ClassVar[list[str]] = []
    _last_buffer: ClassVar[list[str]] = []
    _current_line: ClassVar[str] = ""
    _height: ClassVar[int | None] = None
    _width: ClassVar[int | None] = None
    _expand_tokens: ClassVar[bool] = True
    _force_colors: ClassVar[bool] = False

    @classmethod
    def print(cls, text: str, io: TextIO = sys.stderr) -> None:
        """Add text to current line buffer."""
        if text is None:
            return
        cls._current_line += text

    @classmethod
    def puts(cls, text: str = "", io: TextIO = sys.stderr) -> None:
        """Add text and newline to buffer."""
        cls._current_line += text
        cls._buffer.append(cls._current_line)
        cls._current_line = ""

    @classmethod
    def flush(cls, io: TextIO = sys.stderr) -> None:
        """Output buffer with smart diff against last frame."""
        # Finalize current line
        if cls._current_line:
            cls._buffer.append(cls._current_line)
            cls._current_line = ""

        is_tty = hasattr(io, "isatty") and io.isatty()

        # Non-TTY: print plain text without control codes
        if not is_tty and not cls._force_colors:
            plain = "\n".join(cls._buffer)
            plain = re.sub(r"\{.*?\}", "", plain)
            io.write(plain)
            if not plain.endswith("\n"):
                io.write("\n")
            cls._last_buffer = []
            cls._buffer.clear()
            cls._current_line = ""
            io.flush()
            return

        # TTY or force_colors mode
        if is_tty:
            io.write("\033[H")  # Home

        max_lines = max(len(cls._buffer), len(cls._last_buffer))
        reset = TOKEN_MAP["{reset}"]

        for i in range(max_lines):
            current_line = cls._buffer[i] if i < len(cls._buffer) else ""
            last_line = cls._last_buffer[i] if i < len(cls._last_buffer) else ""

            if current_line != last_line or cls._force_colors:
                if is_tty:
                    io.write(f"\033[{i + 1};1H\033[2K")  # Move and clear line
                if current_line:
                    processed = cls.expand_tokens(current_line)
                    io.write(processed)
                    if cls._expand_tokens:
                        io.write(reset)
                    if cls._force_colors and not is_tty:
                        io.write("\n")

        cls._last_buffer = cls._buffer.copy()
        cls._buffer.clear()
        cls._current_line = ""
        io.flush()

    @classmethod
    def cls(cls, io: TextIO = sys.stderr) -> None:
        """Clear screen and buffers."""
        cls._current_line = ""
        cls._buffer.clear()
        cls._last_buffer.clear()
        io.write("\033[2J\033[H")
        io.flush()

    @classmethod
    def hide_cursor(cls) -> None:
        """Hide terminal cursor."""
        sys.stderr.write("\033[?25l")
        sys.stderr.flush()

    @classmethod
    def show_cursor(cls) -> None:
        """Show terminal cursor."""
        sys.stderr.write("\033[?25h")
        sys.stderr.flush()

    @classmethod
    def read_key(cls) -> str:
        """Read a single key from stdin, handling escape sequences."""
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\033":  # Escape sequence
                import select

                # Check for more chars
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    ch += sys.stdin.read(1)
                    if select.select([sys.stdin], [], [], 0.01)[0]:
                        ch += sys.stdin.read(1)
                    if select.select([sys.stdin], [], [], 0.01)[0]:
                        ch += sys.stdin.read(2)
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    @classmethod
    def height(cls) -> int:
        """Get terminal height."""
        if cls._height is None:
            env_h = os.environ.get("TRY_HEIGHT", "")
            if env_h.isdigit() and int(env_h) > 0:
                cls._height = int(env_h)
            else:
                size = shutil.get_terminal_size((80, 24))
                cls._height = size.lines
        return cls._height

    @classmethod
    def width(cls) -> int:
        """Get terminal width."""
        if cls._width is None:
            env_w = os.environ.get("TRY_WIDTH", "")
            if env_w.isdigit() and int(env_w) > 0:
                cls._width = int(env_w)
            else:
                size = shutil.get_terminal_size((80, 24))
                cls._width = size.columns
        return cls._width

    @classmethod
    def refresh_size(cls) -> None:
        """Clear cached terminal size."""
        cls._height = None
        cls._width = None

    @classmethod
    def disable_token_expansion(cls) -> None:
        """Disable token expansion."""
        cls._expand_tokens = False

    @classmethod
    def disable_colors(cls) -> None:
        """Disable color output."""
        cls._expand_tokens = False

    @classmethod
    def force_colors(cls) -> None:
        """Force color output even for non-TTY."""
        cls._force_colors = True

    @classmethod
    def expand_tokens(cls, text: str) -> str:
        """Expand tokens in text to ANSI sequences."""
        if not cls._expand_tokens:
            return text

        def replace_token(match: re.Match) -> str:
            token = match.group(0)
            return TOKEN_MAP.get(token, token)

        return re.sub(r"\{.*?\}", replace_token, text)


@contextmanager
def raw_mode():
    """Context manager for raw terminal mode."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


@contextmanager
def cooked_mode():
    """Context manager to temporarily restore cooked mode."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        yield
    finally:
        pass  # Settings already restored
