"""Passage panel for displaying the list of passages."""

import curses
from typing import Optional

from models.passage import Passage
from ui.base import ColorPair, draw_box, safe_addstr, wrap_text


class PassagePanel:
    """Panel for displaying and navigating passages.

    The passage panel shows a scrollable list of passages, with
    the currently selected passage highlighted. Each passage shows
    a preview of its text content.
    """

    def __init__(
        self,
        window: "curses.window",
        passages: list[Passage],
    ) -> None:
        """Initialize the passage panel.

        Args:
            window: Curses window to render into.
            passages: List of passages to display.
        """
        self.window = window
        self.passages = passages
        self.selected_index: int = 0
        self.scroll_offset: int = 0
        self.focused: bool = False

    def update_passages(self, passages: list[Passage]) -> None:
        """Update the passage list.

        Args:
            passages: New list of passages.
        """
        self.passages = passages
        # Clamp selection to valid range
        if self.passages:
            self.selected_index = min(
                self.selected_index, len(self.passages) - 1
            )
        else:
            self.selected_index = 0

    def select_next(self) -> None:
        """Select the next passage."""
        if self.passages and self.selected_index < len(self.passages) - 1:
            self.selected_index += 1
            self._ensure_visible()

    def select_prev(self) -> None:
        """Select the previous passage."""
        if self.selected_index > 0:
            self.selected_index -= 1
            self._ensure_visible()

    def select_last(self) -> None:
        """Select the last passage."""
        if self.passages:
            self.selected_index = len(self.passages) - 1
            self._ensure_visible()

    def _ensure_visible(self) -> None:
        """Ensure the selected passage is visible."""
        height, _ = self.window.getmaxyx()
        content_height = height - 2  # Account for border
        lines_per_passage = 4  # separator + index + 2 lines preview

        # Calculate which "slot" the selection is in
        visible_passages = max(1, content_height // lines_per_passage)

        if self.selected_index < self.scroll_offset:
            self.scroll_offset = self.selected_index
        elif self.selected_index >= self.scroll_offset + visible_passages:
            self.scroll_offset = self.selected_index - visible_passages + 1

    def get_selected(self) -> Optional[Passage]:
        """Get the currently selected passage.

        Returns:
            Selected passage, or None if no passages.
        """
        if self.passages and 0 <= self.selected_index < len(self.passages):
            return self.passages[self.selected_index]
        return None

    def draw(self) -> None:
        """Render the passage panel."""
        self.window.erase()
        height, width = self.window.getmaxyx()

        # Draw border
        border_color = (
            ColorPair.BORDER_FOCUS if self.focused else ColorPair.BORDER_DIM
        )
        draw_box(self.window, border_color)

        # Draw title
        if self.passages:
            title = f" Passages ({self.selected_index + 1}/{len(self.passages)}) "
        else:
            title = " Passages (empty) "
        safe_addstr(self.window, 0, 2, title)

        if not self.passages:
            safe_addstr(
                self.window, 2, 2,
                "No passages yet. Type in the input panel and press Ctrl+D.",
            )
            self.window.noutrefresh()
            return

        # Content area
        content_height = height - 2
        content_width = width - 4  # margins
        lines_per_passage = 4
        visible_passages = max(1, content_height // lines_per_passage)

        # Clamp scroll offset
        max_scroll = max(0, len(self.passages) - visible_passages)
        self.scroll_offset = min(self.scroll_offset, max_scroll)

        y = 1
        for i in range(self.scroll_offset, len(self.passages)):
            if y >= height - 1:
                break

            passage = self.passages[i]
            is_selected = (i == self.selected_index)

            # Separator line
            if i > self.scroll_offset:
                separator = "─" * (content_width)
                safe_addstr(self.window, y, 2, separator)
                y += 1
                if y >= height - 1:
                    break

            # Passage header
            header = f"[{i + 1}]"
            if passage.manual_edited:
                header += " (edited)"
            if is_selected:
                attr = curses.color_pair(ColorPair.SELECTED) | curses.A_BOLD
            else:
                attr = curses.A_BOLD

            safe_addstr(self.window, y, 2, header, attr)
            y += 1
            if y >= height - 1:
                break

            # Passage preview (2 lines)
            preview_lines = wrap_text(passage.text, content_width)
            for line in preview_lines[:2]:
                if y >= height - 1:
                    break
                if is_selected:
                    attr = curses.color_pair(ColorPair.SELECTED)
                else:
                    attr = 0
                safe_addstr(self.window, y, 2, line, attr)
                y += 1

            # Add ellipsis if text is longer
            if len(preview_lines) > 2 and y < height - 1:
                if is_selected:
                    attr = curses.color_pair(ColorPair.SELECTED)
                else:
                    attr = curses.A_DIM
                safe_addstr(self.window, y - 1, content_width - 1, "…", attr)

        self.window.noutrefresh()
