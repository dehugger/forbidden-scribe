"""Debug panel for displaying scrolling log output."""

import curses
import logging
import time
from collections import deque
from typing import Optional

from ui.base import ColorPair, draw_box, safe_addstr, wrap_text


class DebugPanel:
    """Panel for displaying scrolling debug/log output.

    Shows recent log messages in a scrollable panel, useful for
    debugging API calls, state changes, and errors.
    """

    def __init__(
        self,
        window: "curses.window",
        max_lines: int = 1000,
    ) -> None:
        """Initialize the debug panel.

        Args:
            window: Curses window to render into.
            max_lines: Maximum number of display lines to retain.
        """
        self.window = window
        self.lines: deque[tuple[str, str]] = deque(maxlen=max_lines)
        self.scroll_offset: int = 0
        self.auto_scroll: bool = True
        self.focused: bool = False

    def add_line(self, text: str, level: str = "") -> None:
        """Add a line to the debug output.

        Args:
            text: Text to add (will be split on newlines and wrapped).
            level: Log level for coloring.
        """
        _, width = self.window.getmaxyx()
        content_width = max(10, width - 4)

        for line in text.split("\n"):
            # Wrap long lines
            wrapped = wrap_text(line, content_width)
            for i, wrapped_line in enumerate(wrapped if wrapped else [""]):
                # Only first line of wrapped text gets the level coloring
                self.lines.append((wrapped_line, level if i == 0 else ""))

        # Auto-scroll to bottom if enabled
        if self.auto_scroll:
            self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        """Scroll to show the most recent lines."""
        height, _ = self.window.getmaxyx()
        content_height = height - 2
        max_scroll = max(0, len(self.lines) - content_height)
        self.scroll_offset = max_scroll

    def handle_key(self, key: int) -> bool:
        """Handle a keypress in the debug panel.

        Args:
            key: The key code pressed.

        Returns:
            True if the key was handled.
        """
        height, _ = self.window.getmaxyx()
        content_height = height - 2

        if key == curses.KEY_UP:
            if self.scroll_offset > 0:
                self.scroll_offset -= 1
                self.auto_scroll = False
            return True
        elif key == curses.KEY_DOWN:
            max_scroll = max(0, len(self.lines) - content_height)
            if self.scroll_offset < max_scroll:
                self.scroll_offset += 1
            if self.scroll_offset >= max_scroll:
                self.auto_scroll = True
            return True
        elif key == curses.KEY_PPAGE:  # Page Up
            self.scroll_offset = max(0, self.scroll_offset - content_height)
            self.auto_scroll = False
            return True
        elif key == curses.KEY_NPAGE:  # Page Down
            max_scroll = max(0, len(self.lines) - content_height)
            self.scroll_offset = min(max_scroll, self.scroll_offset + content_height)
            if self.scroll_offset >= max_scroll:
                self.auto_scroll = True
            return True
        elif key == curses.KEY_HOME:
            self.scroll_offset = 0
            self.auto_scroll = False
            return True
        elif key == curses.KEY_END:
            self._scroll_to_bottom()
            self.auto_scroll = True
            return True

        return False

    def draw(self) -> None:
        """Render the debug panel."""
        self.window.erase()
        height, width = self.window.getmaxyx()

        # Draw border
        border_color = (
            ColorPair.BORDER_FOCUS if self.focused else ColorPair.BORDER_DIM
        )
        draw_box(self.window, border_color)

        # Draw title
        scroll_indicator = "" if self.auto_scroll else " [PAUSED]"
        title = f" Debug Log{scroll_indicator} "
        safe_addstr(self.window, 0, 2, title)

        # Content area
        content_height = height - 2
        content_width = width - 4

        # Clamp scroll offset
        max_scroll = max(0, len(self.lines) - content_height)
        self.scroll_offset = min(self.scroll_offset, max_scroll)

        # Draw lines
        for i in range(content_height):
            line_idx = self.scroll_offset + i
            if line_idx < len(self.lines):
                line_text, level = self.lines[line_idx]
                display_text = line_text[:content_width]
                attr = self._get_line_attr(level)
                safe_addstr(self.window, i + 1, 2, display_text, attr)

        self.window.noutrefresh()

    def _get_line_attr(self, level: str) -> int:
        """Get display attributes based on log level.

        Args:
            level: Log level string.

        Returns:
            Curses attribute for the line.
        """
        level_upper = level.upper()
        if level_upper in ("ERROR", "CRITICAL"):
            return curses.color_pair(ColorPair.ERROR)
        elif level_upper == "WARNING":
            return curses.color_pair(ColorPair.WARNING)
        elif level_upper == "DEBUG":
            return curses.color_pair(ColorPair.DEBUG)
        return curses.A_NORMAL


class DebugPanelHandler(logging.Handler):
    """Logging handler that writes to a DebugPanel.

    Captures log records and formats them for display in the debug panel.
    Uses a compact format optimized for narrow panel display.
    """

    # Short level indicators
    LEVEL_SHORT = {
        "DEBUG": "D",
        "INFO": "I",
        "WARNING": "W",
        "ERROR": "E",
        "CRITICAL": "C",
    }

    def __init__(self, panel: DebugPanel) -> None:
        """Initialize the handler.

        Args:
            panel: DebugPanel to write to.
        """
        super().__init__()
        self.panel = panel

    def _short_name(self, name: str) -> str:
        """Shorten logger name for display.

        Args:
            name: Full logger name like 'forbidden_scribe.editor'.

        Returns:
            Shortened name like 'editor'.
        """
        # Take last component of dotted name
        parts = name.split(".")
        return parts[-1] if parts else name

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the debug panel.

        Args:
            record: Log record to emit.
        """
        # Prevent recursion - don't log errors from this handler
        try:
            if not self.panel or not self.panel.window:
                return

            # Format: HH:MM:SS L [name] message
            time_str = time.strftime("%H:%M:%S", time.localtime(record.created))
            level_char = self.LEVEL_SHORT.get(record.levelname, "?")
            short_name = self._short_name(record.name)
            msg = f"{time_str} {level_char} [{short_name}] {record.getMessage()}"
            self.panel.add_line(msg, record.levelname)
        except Exception:
            # Silently ignore errors to prevent logging loops
            pass
