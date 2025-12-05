"""Base UI utilities and color definitions."""

import curses
from enum import IntEnum
from typing import Optional


class ColorPair(IntEnum):
    """Color pair indices for the UI.

    Designed for dark terminal backgrounds.
    """

    HEADER = 1       # Cyan on default (bright header text)
    FOOTER = 2       # White on default (status text)
    BORDER_FOCUS = 3 # Green on default (focused panel)
    BORDER_INPUT = 4 # Yellow on default (input panel focused)
    BORDER_DIM = 5   # White/dim on default (unfocused)
    SELECTED = 6     # Green on default (selected passage highlight)
    MENU_BG = 7      # Cyan on default (menu items)
    MENU_SELECT = 8  # Black on cyan (menu selection highlight)
    ERROR = 9        # Red on default (error log lines)
    WARNING = 10     # Yellow on default (warning log lines)
    DEBUG = 11       # Magenta on default (debug log lines)
    # Gradient colors for passage indicators (12-19)
    INDICATOR_1 = 12  # Red
    INDICATOR_2 = 13  # Yellow
    INDICATOR_3 = 14  # Green
    INDICATOR_4 = 15  # Cyan
    INDICATOR_5 = 16  # Blue
    INDICATOR_6 = 17  # Magenta


def setup_colors() -> None:
    """Initialize curses color pairs for dark terminal backgrounds."""
    curses.start_color()
    curses.use_default_colors()

    # Use light text on default (dark) background for readability
    curses.init_pair(ColorPair.HEADER, curses.COLOR_CYAN, -1)
    curses.init_pair(ColorPair.FOOTER, curses.COLOR_WHITE, -1)
    curses.init_pair(ColorPair.BORDER_FOCUS, curses.COLOR_GREEN, -1)
    curses.init_pair(ColorPair.BORDER_INPUT, curses.COLOR_YELLOW, -1)
    curses.init_pair(ColorPair.BORDER_DIM, curses.COLOR_WHITE, -1)
    curses.init_pair(ColorPair.SELECTED, curses.COLOR_GREEN, -1)
    curses.init_pair(ColorPair.MENU_BG, curses.COLOR_CYAN, -1)
    curses.init_pair(ColorPair.MENU_SELECT, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(ColorPair.ERROR, curses.COLOR_RED, -1)
    curses.init_pair(ColorPair.WARNING, curses.COLOR_YELLOW, -1)
    curses.init_pair(ColorPair.DEBUG, curses.COLOR_MAGENTA, -1)

    # Gradient colors for passage indicators
    curses.init_pair(ColorPair.INDICATOR_1, curses.COLOR_RED, -1)
    curses.init_pair(ColorPair.INDICATOR_2, curses.COLOR_YELLOW, -1)
    curses.init_pair(ColorPair.INDICATOR_3, curses.COLOR_GREEN, -1)
    curses.init_pair(ColorPair.INDICATOR_4, curses.COLOR_CYAN, -1)
    curses.init_pair(ColorPair.INDICATOR_5, curses.COLOR_BLUE, -1)
    curses.init_pair(ColorPair.INDICATOR_6, curses.COLOR_MAGENTA, -1)


def wrap_text(text: str, width: int, word_wrap: bool = True) -> list[str]:
    """Wrap text to fit within width.

    Args:
        text: Text to wrap.
        width: Maximum line width.
        word_wrap: If True, try to wrap at word boundaries.

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
        elif word_wrap:
            # Word-based wrapping
            current = ""
            words = line.split(" ")
            for word in words:
                if not current:
                    # First word on line
                    if len(word) <= width:
                        current = word
                    else:
                        # Word too long, hard wrap it
                        while len(word) > width:
                            wrapped.append(word[:width])
                            word = word[width:]
                        current = word
                elif len(current) + 1 + len(word) <= width:
                    # Word fits on current line
                    current += " " + word
                else:
                    # Word doesn't fit, start new line
                    wrapped.append(current)
                    if len(word) <= width:
                        current = word
                    else:
                        # Word too long, hard wrap it
                        while len(word) > width:
                            wrapped.append(word[:width])
                            word = word[width:]
                        current = word
            if current:
                wrapped.append(current)
        else:
            # Hard wrap at width
            while len(line) > width:
                wrapped.append(line[:width])
                line = line[width:]
            if line:
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
