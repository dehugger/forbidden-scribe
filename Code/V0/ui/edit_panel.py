"""Edit panel for editing passage text."""

import curses
from typing import Optional

from ui.base import ColorPair, draw_box, safe_addstr


class EditPanel:
    """Panel for editing passage text.

    Similar to InputPanel but for editing existing passage content.
    """

    def __init__(self, window: "curses.window", initial_text: str = "") -> None:
        """Initialize the edit panel.

        Args:
            window: Curses window to render into.
            initial_text: Initial text to edit.
        """
        self.window = window
        self.lines: list[str] = initial_text.split("\n") if initial_text else [""]
        self.cursor_x: int = 0
        self.cursor_y: int = 0
        self.scroll_offset: int = 0
        self.focused: bool = True

    def get_text(self) -> str:
        """Get all text as a single string.

        Returns:
            Combined text from all lines.
        """
        return "\n".join(self.lines)

    def set_text(self, text: str) -> None:
        """Set the text content.

        Args:
            text: New text content.
        """
        self.lines = text.split("\n") if text else [""]
        self.cursor_x = 0
        self.cursor_y = 0
        self.scroll_offset = 0

    def handle_key(self, key: int) -> bool:
        """Handle a keypress in the edit panel.

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
        elif key == 10 or key == 13:  # Enter - new line
            return self._handle_enter()
        elif 32 <= key <= 126:  # Printable ASCII
            return self._handle_char(chr(key))

        return False

    def _handle_enter(self) -> bool:
        """Handle Enter key - insert newline."""
        line = self.lines[self.cursor_y]
        # Split line at cursor
        self.lines[self.cursor_y] = line[:self.cursor_x]
        self.lines.insert(self.cursor_y + 1, line[self.cursor_x:])
        self.cursor_y += 1
        self.cursor_x = 0
        self._ensure_visible()
        return True

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

    def _get_wrapped_lines(
        self, content_width: int
    ) -> tuple[list[tuple[int, str]], int, int]:
        """Get display lines with soft-wrapping.

        Args:
            content_width: Width available for text.

        Returns:
            Tuple of (wrapped_lines, cursor_display_row, cursor_display_col)
            where wrapped_lines is list of (original_line_idx, text).
        """
        wrapped: list[tuple[int, str]] = []
        cursor_row = 0
        cursor_col = 0

        for line_idx, line in enumerate(self.lines):
            if not line:
                # Empty line
                if line_idx == self.cursor_y:
                    cursor_row = len(wrapped)
                    cursor_col = 0
                wrapped.append((line_idx, ""))
            else:
                # Wrap long lines
                pos = 0
                while pos < len(line):
                    chunk = line[pos:pos + content_width]
                    # Track cursor position
                    if line_idx == self.cursor_y:
                        if pos <= self.cursor_x < pos + len(chunk):
                            cursor_row = len(wrapped)
                            cursor_col = self.cursor_x - pos
                        elif self.cursor_x >= len(line) and pos + len(chunk) >= len(line):
                            # Cursor at end of line
                            cursor_row = len(wrapped)
                            cursor_col = len(chunk)
                    wrapped.append((line_idx, chunk))
                    pos += content_width

        return wrapped, cursor_row, cursor_col

    def draw(self) -> None:
        """Render the edit panel with soft line wrapping."""
        self.window.erase()
        height, width = self.window.getmaxyx()

        # Draw border
        border_color = (
            ColorPair.BORDER_FOCUS if self.focused else ColorPair.BORDER_DIM
        )
        draw_box(self.window, border_color)

        # Draw title
        title = " Edit Passage - ESC to cancel, Ctrl+S to save "
        safe_addstr(self.window, 0, 2, title)

        # Content area
        content_height = height - 2
        content_width = width - 4

        if content_width <= 0:
            self.window.noutrefresh()
            return

        # Get wrapped lines and cursor position
        wrapped, cursor_row, cursor_col = self._get_wrapped_lines(content_width)

        # Adjust scroll to keep cursor visible
        if cursor_row < self.scroll_offset:
            self.scroll_offset = cursor_row
        elif cursor_row >= self.scroll_offset + content_height:
            self.scroll_offset = cursor_row - content_height + 1

        # Clamp scroll offset
        max_scroll = max(0, len(wrapped) - content_height)
        self.scroll_offset = min(self.scroll_offset, max_scroll)

        # Draw wrapped lines
        for i in range(content_height):
            display_idx = self.scroll_offset + i
            if display_idx < len(wrapped):
                _, line_text = wrapped[display_idx]
                safe_addstr(self.window, i + 1, 2, line_text)

        # Position cursor if focused
        if self.focused:
            cursor_screen_y = cursor_row - self.scroll_offset + 1
            cursor_screen_x = cursor_col + 2
            if 0 < cursor_screen_y < height - 1 and cursor_screen_x < width - 1:
                try:
                    self.window.move(cursor_screen_y, cursor_screen_x)
                except curses.error:
                    pass

        self.window.noutrefresh()
