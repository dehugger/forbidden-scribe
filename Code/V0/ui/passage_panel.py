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

    def _get_indicator_color(self, passage_id: str) -> int:
        """Get a consistent color for a passage based on its ID.

        Args:
            passage_id: Unique passage identifier.

        Returns:
            Color pair index from the gradient set.
        """
        # Use hash of ID to deterministically pick a color
        indicator_colors = [
            ColorPair.INDICATOR_1,
            ColorPair.INDICATOR_2,
            ColorPair.INDICATOR_3,
            ColorPair.INDICATOR_4,
            ColorPair.INDICATOR_5,
            ColorPair.INDICATOR_6,
        ]
        hash_val = sum(ord(c) for c in passage_id)
        return indicator_colors[hash_val % len(indicator_colors)]

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
        """Ensure the selected passage is visible by scrolling if needed."""
        # Don't scroll until passages exceed screen capacity
        # This keeps all passages visible for as long as possible
        # When scrolling is needed, we'll handle it dynamically in draw()
        self.scroll_offset = 0

    def get_selected(self) -> Optional[Passage]:
        """Get the currently selected passage.

        Returns:
            Selected passage, or None if no passages.
        """
        if self.passages and 0 <= self.selected_index < len(self.passages):
            return self.passages[self.selected_index]
        return None

    def draw(self) -> None:
        """Render the passage panel with subtle colored indicators."""
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
                "No passages yet. Type below and press Enter.",
            )
            self.window.noutrefresh()
            return

        # Content area: just border + small left margin + text
        content_height = height - 2
        content_width = width - 4  # Standard margins

        y = 1
        # Always start from first passage (scroll_offset is always 0)
        # Render all passages completely, even if they extend beyond screen
        for i in range(len(self.passages)):
            passage = self.passages[i]
            is_selected = (i == self.selected_index)
            start_y = y

            # Get color for this passage's indicator
            indicator_color = self._get_indicator_color(passage.id)

            # Add spacing between passages (one blank line)
            if i > 0:
                y += 1

            # Status indicator (pending/edited) as first line if needed
            if passage.pending or passage.manual_edited:
                status = ""
                if passage.pending:
                    status = "⏳ generating..."
                elif passage.manual_edited:
                    status = "✎ edited"
                safe_addstr(self.window, y, 3, status, curses.A_DIM)
                y += 1

            # Complete passage text - render ALL lines regardless of screen size
            text_lines = wrap_text(passage.text, content_width - 1)
            for line in text_lines:
                # Only draw if within visible area
                if 1 <= y < height - 1:
                    if passage.pending:
                        # Pending passages show in dim color
                        attr = curses.A_DIM
                    else:
                        attr = 0
                    safe_addstr(self.window, y, 3, line, attr)
                y += 1

            # Draw subtle colored indicator on far left edge (column 1)
            # Only draw within visible area
            end_y = y
            for row in range(start_y, end_y):
                if 1 <= row < height - 1:
                    try:
                        self.window.addstr(
                            row, 1, "▌",
                            curses.color_pair(indicator_color)
                        )
                    except curses.error:
                        pass

            # Draw subtle highlight on selected passage (only when panel is focused)
            if is_selected and self.focused:
                # Calculate outline dimensions - full width
                outline_left = 1
                outline_right = width - 2
                outline_width = outline_right - outline_left

                # Only draw outline within visible area
                visible_start = max(start_y, 1)
                visible_end = min(end_y, height - 1)

                try:
                    # Right edge line only
                    for row in range(visible_start, visible_end):
                        if 1 <= row < height - 1:
                            self.window.addstr(
                                row, outline_right, "│",
                                curses.color_pair(ColorPair.SELECTED)
                            )

                    # Bottom line (if visible and it's the actual end)
                    if visible_end == end_y and visible_end < height - 1:
                        bottom_line = "─" * outline_width
                        self.window.addstr(
                            visible_end, outline_left, bottom_line,
                            curses.color_pair(ColorPair.SELECTED)
                        )
                except curses.error:
                    pass

        self.window.noutrefresh()
