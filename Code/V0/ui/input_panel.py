"""Input panel for user text entry."""

import curses
from typing import Optional

from ui.base import ColorPair, draw_box, safe_addstr


class InputPanel:
    """Panel for entering user text.

    The input panel provides a multi-line text editing area
    where users can compose their rough drafts before sending
    to the AI for refinement.
    """

    def __init__(self, window: "curses.window") -> None:
        """Initialize the input panel.

        Args:
            window: Curses window to render into.
        """
        self.window = window
        self.lines: list[str] = [""]
        self.cursor_x: int = 0
        self.cursor_y: int = 0
        self.scroll_offset: int = 0
        self.focused: bool = True

    def get_text(self) -> str:
        """Get all input text as a single string.

        Returns:
            Combined text from all lines.
        """
        return "\n".join(self.lines)

    def clear(self) -> None:
        """Clear all input text."""
        self.lines = [""]
        self.cursor_x = 0
        self.cursor_y = 0
        self.scroll_offset = 0

    def is_empty(self) -> bool:
        """Check if input is empty.

        Returns:
            True if no text has been entered.
        """
        return self.lines == [""] or not any(self.lines)

    def handle_key(self, key: int) -> bool:
        """Handle a keypress in the input panel.

        Args:
            key: The key code pressed.

        Returns:
            True if the key was handled.
        """
        height, width = self.window.getmaxyx()
        content_height = height - 2
        content_width = width - 4

        if key == curses.KEY_BACKSPACE or key == 127 or key == 8:
            return self._handle_backspace()
        elif key == curses.KEY_DC:
            return self._handle_delete()
        elif key == curses.KEY_LEFT:
            return self._handle_left()
        elif key == curses.KEY_RIGHT:
            return self._handle_right()
        elif key == curses.KEY_UP:
            return self._handle_up()
        elif key == curses.KEY_DOWN:
            return self._handle_down()
        elif key == curses.KEY_HOME:
            self.cursor_x = 0
            return True
        elif key == curses.KEY_END:
            self.cursor_x = len(self.lines[self.cursor_y])
            return True
        elif key == 10 or key == 13:  # Enter
            return self._handle_enter()
        elif 32 <= key <= 126:  # Printable ASCII
            return self._handle_char(chr(key))

        return False

    def _handle_backspace(self) -> bool:
        """Handle backspace key."""
        if self.cursor_x > 0:
            line = self.lines[self.cursor_y]
            self.lines[self.cursor_y] = (
                line[:self.cursor_x - 1] + line[self.cursor_x:]
            )
            self.cursor_x -= 1
        elif self.cursor_y > 0:
            # Join with previous line
            prev_len = len(self.lines[self.cursor_y - 1])
            self.lines[self.cursor_y - 1] += self.lines[self.cursor_y]
            del self.lines[self.cursor_y]
            self.cursor_y -= 1
            self.cursor_x = prev_len
            self._ensure_visible()
        return True

    def _handle_delete(self) -> bool:
        """Handle delete key."""
        line = self.lines[self.cursor_y]
        if self.cursor_x < len(line):
            self.lines[self.cursor_y] = (
                line[:self.cursor_x] + line[self.cursor_x + 1:]
            )
        elif self.cursor_y < len(self.lines) - 1:
            # Join with next line
            self.lines[self.cursor_y] += self.lines[self.cursor_y + 1]
            del self.lines[self.cursor_y + 1]
        return True

    def _handle_left(self) -> bool:
        """Handle left arrow."""
        if self.cursor_x > 0:
            self.cursor_x -= 1
        elif self.cursor_y > 0:
            self.cursor_y -= 1
            self.cursor_x = len(self.lines[self.cursor_y])
            self._ensure_visible()
        return True

    def _handle_right(self) -> bool:
        """Handle right arrow."""
        if self.cursor_x < len(self.lines[self.cursor_y]):
            self.cursor_x += 1
        elif self.cursor_y < len(self.lines) - 1:
            self.cursor_y += 1
            self.cursor_x = 0
            self._ensure_visible()
        return True

    def _handle_up(self) -> bool:
        """Handle up arrow."""
        if self.cursor_y > 0:
            self.cursor_y -= 1
            self.cursor_x = min(self.cursor_x, len(self.lines[self.cursor_y]))
            self._ensure_visible()
        return True

    def _handle_down(self) -> bool:
        """Handle down arrow."""
        if self.cursor_y < len(self.lines) - 1:
            self.cursor_y += 1
            self.cursor_x = min(self.cursor_x, len(self.lines[self.cursor_y]))
            self._ensure_visible()
        return True

    def _handle_enter(self) -> bool:
        """Handle enter key."""
        line = self.lines[self.cursor_y]
        self.lines[self.cursor_y] = line[:self.cursor_x]
        self.lines.insert(self.cursor_y + 1, line[self.cursor_x:])
        self.cursor_y += 1
        self.cursor_x = 0
        self._ensure_visible()
        return True

    def _handle_char(self, char: str) -> bool:
        """Handle printable character."""
        line = self.lines[self.cursor_y]
        self.lines[self.cursor_y] = (
            line[:self.cursor_x] + char + line[self.cursor_x:]
        )
        self.cursor_x += 1
        return True

    def _ensure_visible(self) -> None:
        """Ensure cursor is visible by adjusting scroll."""
        height, _ = self.window.getmaxyx()
        content_height = height - 2

        if self.cursor_y < self.scroll_offset:
            self.scroll_offset = self.cursor_y
        elif self.cursor_y >= self.scroll_offset + content_height:
            self.scroll_offset = self.cursor_y - content_height + 1

    def draw(self) -> None:
        """Render the input panel."""
        self.window.erase()
        height, width = self.window.getmaxyx()

        # Draw border
        border_color = (
            ColorPair.BORDER_INPUT if self.focused else ColorPair.BORDER_DIM
        )
        draw_box(self.window, border_color)

        # Draw title
        title = " Input - Ctrl+D to send "
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
                line = self.lines[line_idx][:content_width]
                safe_addstr(self.window, i + 1, 2, line)

        # Position cursor if focused
        if self.focused:
            cursor_screen_y = self.cursor_y - self.scroll_offset + 1
            cursor_screen_x = min(self.cursor_x + 2, width - 2)
            if 0 < cursor_screen_y < height - 1:
                try:
                    self.window.move(cursor_screen_y, cursor_screen_x)
                except curses.error:
                    pass

        self.window.noutrefresh()
