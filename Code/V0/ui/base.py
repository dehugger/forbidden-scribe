"""Base UI utilities and color definitions."""

import curses
from enum import IntEnum
from typing import Optional


class ColorPair(IntEnum):
    """Color pair indices for the UI."""

    HEADER = 1       # Black on cyan
    FOOTER = 2       # Black on white
    BORDER_FOCUS = 3 # Green on default
    BORDER_INPUT = 4 # Yellow on default
    BORDER_DIM = 5   # White on default
    SELECTED = 6     # Black on white (for selected passage)
    MENU_BG = 7      # Black on blue (menu background)
    MENU_SELECT = 8  # Black on cyan (menu selection)


def setup_colors() -> None:
    """Initialize curses color pairs."""
    curses.start_color()
    curses.use_default_colors()

    curses.init_pair(ColorPair.HEADER, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(ColorPair.FOOTER, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(ColorPair.BORDER_FOCUS, curses.COLOR_GREEN, -1)
    curses.init_pair(ColorPair.BORDER_INPUT, curses.COLOR_YELLOW, -1)
    curses.init_pair(ColorPair.BORDER_DIM, curses.COLOR_WHITE, -1)
    curses.init_pair(ColorPair.SELECTED, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(ColorPair.MENU_BG, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(ColorPair.MENU_SELECT, curses.COLOR_BLACK, curses.COLOR_CYAN)


def wrap_text(text: str, width: int) -> list[str]:
    """Wrap text to fit within width.

    Args:
        text: Text to wrap.
        width: Maximum line width.

    Returns:
        List of wrapped lines.
    """
    if width <= 0:
        return []

    lines = text.split("\n")
    wrapped: list[str] = []

    for line in lines:
        if len(line) <= width:
            wrapped.append(line)
        else:
            # Hard wrap at width
            while len(line) > width:
                wrapped.append(line[:width])
                line = line[width:]
            wrapped.append(line)

    return wrapped


def truncate(text: str, width: int, ellipsis: str = "...") -> str:
    """Truncate text to width with ellipsis.

    Args:
        text: Text to truncate.
        width: Maximum width including ellipsis.
        ellipsis: Ellipsis string to append.

    Returns:
        Truncated string.
    """
    if len(text) <= width:
        return text
    if width <= len(ellipsis):
        return ellipsis[:width]
    return text[:width - len(ellipsis)] + ellipsis


def safe_addstr(
    window: "curses.window",
    y: int,
    x: int,
    text: str,
    attr: int = 0,
) -> None:
    """Safely add string to window, handling boundary errors.

    Args:
        window: Curses window to write to.
        y: Row position.
        x: Column position.
        text: Text to write.
        attr: Optional attributes.
    """
    try:
        height, width = window.getmaxyx()
        if y < 0 or y >= height or x < 0:
            return
        # Truncate text to fit
        max_len = width - x - 1
        if max_len <= 0:
            return
        window.addstr(y, x, text[:max_len], attr)
    except curses.error:
        pass


def draw_box(
    window: "curses.window",
    color_pair: int = ColorPair.BORDER_DIM,
) -> None:
    """Draw a box border around a window.

    Args:
        window: Curses window to draw border on.
        color_pair: Color pair for the border.
    """
    try:
        window.attron(curses.color_pair(color_pair))
        window.border()
        window.attroff(curses.color_pair(color_pair))
    except curses.error:
        pass
