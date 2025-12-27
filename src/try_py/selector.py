"""Interactive directory selector with fuzzy matching TUI."""

from __future__ import annotations

import fcntl
import os
import re
import select
import signal
import sys
import termios
import tty
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from .fuzzy import calculate_score, highlight_matches_for_selection
from .ui import UI


@dataclass
class TryDir:
    """Directory entry."""

    name: str
    basename: str
    path: Path
    ctime: datetime
    mtime: datetime
    score: float = 0.0

    @property
    def basename_down(self) -> str:
        return self.basename.lower()

    def to_dict(self) -> dict:
        """Convert to dict for scoring compatibility."""
        return {
            "name": self.name,
            "basename": self.basename,
            "basename_down": self.basename_down,
            "path": str(self.path),
            "ctime": self.ctime,
            "mtime": self.mtime,
            "score": self.score,
        }


class SelectionResult(TypedDict, total=False):
    """Result from selection."""

    type: str  # 'cd', 'mkdir', 'delete', 'cancel'
    path: str
    paths: list[dict]
    base_path: str


@dataclass
class TrySelector:
    """Interactive directory selector with fuzzy matching."""

    TRY_PATH = str(Path("~/src/tries").expanduser())

    search_term: str = ""
    base_path: str = field(default_factory=lambda: TrySelector.TRY_PATH)
    initial_input: str | None = None
    test_render_once: bool = False
    test_no_cls: bool = False
    test_keys: list[str] | None = None
    test_confirm: str | None = None

    # Internal state
    cursor_pos: int = field(default=0, init=False)
    input_cursor_pos: int = field(default=0, init=False)
    scroll_offset: int = field(default=0, init=False)
    input_buffer: str = field(default="", init=False)
    selected: SelectionResult | None = field(default=None, init=False)
    _all_tries: list[TryDir] | None = field(default=None, init=False)
    delete_status: str | None = field(default=None, init=False)
    delete_mode: bool = field(default=False, init=False)
    marked_for_deletion: list[str] = field(default_factory=list, init=False)
    test_had_keys: bool = field(default=False, init=False)
    _old_winch_handler: Any = field(default=None, init=False)
    needs_redraw: bool = field(default=False, init=False)
    _original_term_settings: Any = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.search_term = re.sub(r"\s+", "-", self.search_term)
        self.input_buffer = (
            re.sub(r"\s+", "-", self.initial_input) if self.initial_input else self.search_term
        )
        self.input_cursor_pos = len(self.input_buffer)
        self.test_had_keys = self.test_keys is not None and len(self.test_keys) > 0

        Path(self.base_path).mkdir(parents=True, exist_ok=True)

    def run(self) -> SelectionResult | None:
        """Main entry point - run the selector."""
        self._setup_terminal()

        try:
            # Test mode: render once and exit
            if self.test_render_once and (self.test_keys is None or len(self.test_keys) == 0):
                tries = self._get_tries()
                self._render(tries)
                return None

            # Check for TTY
            if not sys.stdin.isatty() or not sys.stderr.isatty():
                if self.test_keys is None or len(self.test_keys) == 0:
                    UI.puts("Error: try requires an interactive terminal")
                    return None
                self._main_loop()
            else:
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                self._original_term_settings = old_settings
                try:
                    tty.setraw(fd)
                    self._main_loop()
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        finally:
            self._restore_terminal()

        return self.selected

    def _setup_terminal(self) -> None:
        """Set up terminal for TUI."""
        if not self.test_no_cls:
            UI.cls()
            UI.hide_cursor()

        # Handle SIGWINCH
        def handle_winch(signum: int, frame: object) -> None:
            self.needs_redraw = True

        self._old_winch_handler = signal.signal(signal.SIGWINCH, handle_winch)

    def _restore_terminal(self) -> None:
        """Restore terminal state."""
        if not self.test_no_cls:
            UI.cls()
            UI.show_cursor()

        if self._old_winch_handler is not None:
            signal.signal(signal.SIGWINCH, self._old_winch_handler)

    def _load_all_tries(self) -> list[TryDir]:
        """Load all directories from base path."""
        if self._all_tries is not None:
            return self._all_tries

        tries: list[TryDir] = []
        base = Path(self.base_path)

        try:
            for entry in base.iterdir():
                if entry.name.startswith("."):
                    continue

                try:
                    if not entry.is_dir():
                        continue

                    stat = entry.stat()
                    tries.append(
                        TryDir(
                            name=f"📁 {entry.name}",
                            basename=entry.name,
                            path=entry,
                            ctime=datetime.fromtimestamp(stat.st_ctime),
                            mtime=datetime.fromtimestamp(stat.st_mtime),
                            score=0.0,
                        )
                    )
                except OSError:
                    continue
        except OSError:
            pass

        self._all_tries = tries
        return tries

    def _get_tries(self) -> list[dict]:
        """Get filtered and scored directories."""
        all_tries = self._load_all_tries()

        query_down = self.input_buffer.lower()
        query_chars = list(query_down)

        # Score all tries
        scored = []
        for try_dir in all_tries:
            d = try_dir.to_dict()
            score = calculate_score(d, query_down, query_chars, try_dir.ctime, try_dir.mtime)
            d["score"] = score
            scored.append(d)

        # Filter and sort
        if not self.input_buffer:
            return sorted(scored, key=lambda t: -t["score"])
        else:
            filtered = [t for t in scored if t["score"] > 0]
            return sorted(filtered, key=lambda t: -t["score"])

    def _main_loop(self) -> None:
        """Main event loop."""
        while True:
            tries = self._get_tries()
            show_create_new = bool(self.input_buffer)
            total_items = len(tries) + (1 if show_create_new else 0)

            # Ensure cursor in bounds
            self.cursor_pos = max(0, min(self.cursor_pos, max(0, total_items - 1)))

            self._render(tries)

            key = self._read_key()
            if key is None:
                continue

            match key:
                case "\r":  # Enter
                    if self.delete_mode and self.marked_for_deletion:
                        self._confirm_batch_delete(tries)
                        if self.selected:
                            break
                    elif self.cursor_pos < len(tries):
                        self._handle_selection(tries[self.cursor_pos])
                        if self.selected:
                            break
                    elif show_create_new:
                        self._handle_create_new()
                        if self.selected:
                            break

                case "\033[A" | "\x10":  # Up / Ctrl-P
                    self.cursor_pos = max(0, self.cursor_pos - 1)

                case "\033[B" | "\x0e":  # Down / Ctrl-N
                    self.cursor_pos = min(total_items - 1, self.cursor_pos + 1)

                case "\033[C" | "\033[D":  # Right/Left arrows - ignore
                    pass

                case "\x7f" | "\b":  # Backspace
                    if self.input_cursor_pos > 0:
                        self.input_buffer = (
                            self.input_buffer[: self.input_cursor_pos - 1]
                            + self.input_buffer[self.input_cursor_pos :]
                        )
                        self.input_cursor_pos -= 1
                    self.cursor_pos = 0

                case "\x01":  # Ctrl-A
                    self.input_cursor_pos = 0

                case "\x05":  # Ctrl-E
                    self.input_cursor_pos = len(self.input_buffer)

                case "\x02":  # Ctrl-B
                    self.input_cursor_pos = max(0, self.input_cursor_pos - 1)

                case "\x06":  # Ctrl-F
                    self.input_cursor_pos = min(len(self.input_buffer), self.input_cursor_pos + 1)

                case "\x08":  # Ctrl-H
                    if self.input_cursor_pos > 0:
                        self.input_buffer = (
                            self.input_buffer[: self.input_cursor_pos - 1]
                            + self.input_buffer[self.input_cursor_pos :]
                        )
                        self.input_cursor_pos -= 1
                    self.cursor_pos = 0

                case "\x0b":  # Ctrl-K
                    self.input_buffer = self.input_buffer[: self.input_cursor_pos]

                case "\x17":  # Ctrl-W
                    if self.input_cursor_pos > 0:
                        pos = self.input_cursor_pos - 1
                        # Skip non-alnum
                        while pos >= 0 and not self.input_buffer[pos].isalnum():
                            pos -= 1
                        # Skip alnum
                        while pos >= 0 and self.input_buffer[pos].isalnum():
                            pos -= 1
                        new_pos = pos + 1
                        self.input_buffer = (
                            self.input_buffer[:new_pos] + self.input_buffer[self.input_cursor_pos :]
                        )
                        self.input_cursor_pos = new_pos

                case "\x04":  # Ctrl-D - toggle delete mark
                    if self.cursor_pos < len(tries):
                        path = tries[self.cursor_pos]["path"]
                        if path in self.marked_for_deletion:
                            self.marked_for_deletion.remove(path)
                        else:
                            self.marked_for_deletion.append(path)
                            self.delete_mode = True
                        if not self.marked_for_deletion:
                            self.delete_mode = False

                case "\x03" | "\033":  # Ctrl-C / ESC
                    if self.delete_mode:
                        self.marked_for_deletion.clear()
                        self.delete_mode = False
                    else:
                        self.selected = None
                        break

                case char if len(char) == 1 and re.match(r"[a-zA-Z0-9\-_. ]", char):
                    self.input_buffer = (
                        self.input_buffer[: self.input_cursor_pos]
                        + char
                        + self.input_buffer[self.input_cursor_pos :]
                    )
                    self.input_cursor_pos += 1
                    self.cursor_pos = 0

    def _read_key(self) -> str | None:
        """Read a key from input."""
        if self.test_keys and len(self.test_keys) > 0:
            return self.test_keys.pop(0)

        if self.test_had_keys and (not self.test_keys or len(self.test_keys) == 0):
            return "\033"

        while True:
            if self.needs_redraw:
                self.needs_redraw = False
                UI.refresh_size()
                UI.cls()
                return None

            fd = sys.stdin.fileno()
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                # Read first byte directly (we're already in raw mode)
                data = os.read(fd, 1)
                if not data:
                    continue
                ch = data.decode("utf-8", errors="replace")

                # If escape, read more bytes for arrow keys etc
                if ch == "\033":
                    # Check for more bytes with short timeout
                    while True:
                        more_ready, _, _ = select.select([fd], [], [], 0.05)
                        if more_ready:
                            more = os.read(fd, 1)
                            if more:
                                ch += more.decode("utf-8", errors="replace")
                            else:
                                break
                        else:
                            break

                return ch

    def _render(self, tries: list[dict]) -> None:
        """Render the TUI."""
        term_width = UI.width()
        term_height = UI.height()

        separator = "─" * (term_width - 1)

        # Header
        UI.puts("{h1}📁 Try Selector{reset}")
        UI.puts(f"{{dim}}{separator}{{/fg}}")

        # Search input
        before = self.input_buffer[: self.input_cursor_pos]
        at_cursor = (
            self.input_buffer[self.input_cursor_pos]
            if self.input_cursor_pos < len(self.input_buffer)
            else " "
        )
        after = self.input_buffer[self.input_cursor_pos + 1 :]
        UI.puts(f"{{dim}}Search:{{/fg}} {{b}}{before}\033[7m{at_cursor}\033[27m{after}{{/b}}")
        UI.puts(f"{{dim}}{separator}{{/fg}}")

        # Calculate visible window
        max_visible = max(3, term_height - 8)
        show_create_new = bool(self.input_buffer)
        total_items = len(tries) + (1 if show_create_new else 0)

        # Adjust scroll
        if self.cursor_pos < self.scroll_offset:
            self.scroll_offset = self.cursor_pos
        elif self.cursor_pos >= self.scroll_offset + max_visible:
            self.scroll_offset = self.cursor_pos - max_visible + 1

        visible_end = min(self.scroll_offset + max_visible, total_items)

        for idx in range(self.scroll_offset, visible_end):
            # Blank line before create new
            if idx == len(tries) and tries and idx >= self.scroll_offset:
                UI.puts()

            is_selected = idx == self.cursor_pos
            UI.print("{b}→ {/b}" if is_selected else "  ")

            if idx < len(tries):
                try_dir = tries[idx]
                is_marked = try_dir["path"] in self.marked_for_deletion
                basename = try_dir["basename"]

                # Metadata
                time_text = self._format_relative_time(try_dir["mtime"])
                score_text = f"{try_dir['score']:.1f}"
                meta_text = f"{time_text}, {score_text}"
                meta_width = len(meta_text) + 1

                prefix_width = 5
                meta_start = term_width - meta_width
                max_name_for_meta = meta_start - prefix_width - 1
                max_name_width = term_width - prefix_width - 1

                if is_marked:
                    UI.print("{strike}")

                UI.print("🗑️  " if is_marked else "📁 ")

                if is_selected:
                    UI.print("{section}")

                # Format with date styling
                if date_match := re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)$", basename):
                    date_part, name_part = date_match.groups()
                    full_name = f"{date_part}-{name_part}"

                    if len(full_name) > max_name_width > 14:
                        available = max_name_width - 11 - 2
                        if len(name_part) > available + 1:
                            name_part = name_part[:available] + "…"
                        full_name = f"{date_part}-{name_part}"

                    UI.print(f"{{dim}}{date_part}{{/fg}}")

                    sep_matches = self.input_buffer and "-" in self.input_buffer
                    UI.print("{b}-{/b}" if sep_matches else "{dim}-{/fg}")

                    if self.input_buffer:
                        UI.print(
                            highlight_matches_for_selection(
                                name_part, self.input_buffer, is_selected
                            )
                        )
                    else:
                        UI.print(name_part)

                    display_text = full_name
                else:
                    name = basename
                    if len(name) > max_name_width > 2:
                        name = name[: max_name_width - 1] + "…"

                    if self.input_buffer:
                        UI.print(
                            highlight_matches_for_selection(name, self.input_buffer, is_selected)
                        )
                    else:
                        UI.print(name)

                    display_text = name

                if is_selected:
                    UI.print("{/section}")

                # Metadata
                if len(display_text) <= max_name_for_meta:
                    padding = meta_start - prefix_width - len(display_text)
                    UI.print(" " * padding)
                    UI.print(f"{{dim}}{meta_text}{{/fg}}")

                if is_marked:
                    UI.print("{/strike}")

            else:
                # Create new option
                if is_selected:
                    UI.print("{section}")

                date_prefix = datetime.now().strftime("%Y-%m-%d")
                if self.input_buffer:
                    display = f"📂 Create new: {date_prefix}-{self.input_buffer}"
                else:
                    display = f"📂 Create new: {date_prefix}-"

                UI.print(display)

                padding = max(1, term_width - 3 - len(display))
                UI.print(" " * padding)

            UI.puts()

        # Scroll indicator
        if total_items > max_visible:
            UI.puts(f"{{dim}}{separator}{{/fg}}")
            UI.puts(f"{{dim}}[{self.scroll_offset + 1}-{visible_end}/{total_items}]{{/fg}}")

        # Footer
        UI.puts(f"{{dim}}{separator}{{/fg}}")

        if self.delete_status:
            UI.puts(f"{{b}}{self.delete_status}{{/b}}")
            self.delete_status = None
        elif self.delete_mode:
            count = len(self.marked_for_deletion)
            UI.puts(
                f"{{strike}} DELETE MODE {{/strike}} {count} marked  |  Ctrl-D: Toggle  Enter: Confirm  Esc: Cancel"
            )
        else:
            UI.puts("{dim}↑↓: Navigate  Enter: Select  Ctrl-D: Delete  Esc: Cancel{/fg}")

        UI.flush()

    def _format_relative_time(self, time: datetime | None) -> str:
        """Format time as relative string."""
        if not time:
            return "?"

        seconds = (datetime.now() - time).total_seconds()
        minutes = seconds / 60
        hours = minutes / 60
        days = hours / 24

        if seconds < 60:
            return "just now"
        elif minutes < 60:
            return f"{int(minutes)}m ago"
        elif hours < 24:
            return f"{int(hours)}h ago"
        elif days < 7:
            return f"{int(days)}d ago"
        else:
            return f"{int(days / 7)}w ago"

    def _handle_selection(self, try_dir: dict) -> None:
        """Handle selecting an existing directory."""
        self.selected = SelectionResult(type="cd", path=try_dir["path"])

    def _handle_create_new(self) -> None:
        """Handle creating a new directory."""
        date_prefix = datetime.now().strftime("%Y-%m-%d")

        if self.input_buffer:
            final_name = re.sub(r"\s+", "-", f"{date_prefix}-{self.input_buffer}")
            full_path = str(Path(self.base_path) / final_name)
            self.selected = SelectionResult(type="mkdir", path=full_path)
        else:
            # Prompt for name - simplified for now
            self.selected = SelectionResult(type="cancel", path="")

    def _confirm_batch_delete(self, tries: list[dict]) -> None:
        """Confirm and execute batch deletion."""
        marked_items = [t for t in tries if t["path"] in self.marked_for_deletion]
        if not marked_items:
            return

        UI.cls()
        count = len(marked_items)
        suffix = "y" if count == 1 else "ies"
        UI.puts(f"{{h2}}Delete {count} Director{suffix}{{reset}}")
        UI.puts()

        for item in marked_items:
            UI.puts(f"  {{strike}}📁 {item['basename']}{{/strike}}")

        UI.puts()
        UI.puts("{b}Type {/b}YES{b} to confirm deletion: {/b}")
        UI.flush()
        sys.stderr.write("\033[?25h")
        sys.stderr.flush()

        # Get confirmation
        confirmation = ""
        if self.test_keys and len(self.test_keys) > 0:
            while self.test_keys:
                ch = self.test_keys.pop(0)
                if ch in ("\r", "\n"):
                    break
                confirmation += ch
        elif self.test_confirm is not None or not sys.stderr.isatty():
            confirmation = self.test_confirm or ""
        else:
            fd = sys.stdin.fileno()
            try:
                # Restore cooked mode for input()
                if self._original_term_settings:
                    termios.tcsetattr(fd, termios.TCSADRAIN, self._original_term_settings)
                sys.stdin.flush()
                confirmation = input().strip()
            finally:
                # Restore raw mode
                if self._original_term_settings:
                    tty.setraw(fd)

        if confirmation == "YES":
            try:
                base_real = Path(self.base_path).resolve()
                validated = []

                for item in marked_items:
                    target_real = Path(item["path"]).resolve()
                    if not str(target_real).startswith(str(base_real) + "/"):
                        raise ValueError(
                            f"Safety check failed: {target_real} is not inside {base_real}"
                        )
                    validated.append({"path": str(target_real), "basename": item["basename"]})

                self.selected = SelectionResult(
                    type="delete", paths=validated, base_path=str(base_real)
                )
                names = ", ".join(p["basename"] for p in validated)
                self.delete_status = f"Deleted: {{strike}}{names}{{/strike}}"
                self._all_tries = None
                self.marked_for_deletion.clear()
                self.delete_mode = False
            except Exception as e:
                self.delete_status = f"Error: {e}"
        else:
            self.delete_status = "Delete cancelled"
            self.marked_for_deletion.clear()
            self.delete_mode = False

        sys.stderr.write("\033[?25l")
        sys.stderr.flush()
