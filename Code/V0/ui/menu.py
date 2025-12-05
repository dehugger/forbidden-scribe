"""Menu overlay for passage operations."""

import curses
from dataclasses import dataclass
from typing import Callable, Optional

from ui.base import ColorPair, safe_addstr


@dataclass
class MenuItem:
    """A single menu item."""

    label: str
    action: str  # Action identifier
    description: Optional[str] = None
    hotkey: Optional[str] = None


class Menu:
    """Overlay menu for selecting operations.

    Menus appear as overlays on top of the main UI and allow
    users to select from a list of operations.
    """

    def __init__(
        self,
        stdscr: "curses.window",
        title: str,
        items: list[MenuItem],
        x: int,
        y: int,
    ) -> None:
        """Initialize the menu.

        Args:
            stdscr: Main screen for drawing.
            title: Menu title.
            items: List of menu items.
            x: X position for menu.
            y: Y position for menu.
        """
        self.stdscr = stdscr
        self.title = title
        self.items = items
        self.x = x
        self.y = y
        self.selected_index: int = 0
        self.visible: bool = False

    def show(self) -> None:
        """Show the menu."""
        self.visible = True
        self.selected_index = 0

    def hide(self) -> None:
        """Hide the menu."""
        self.visible = False

    def select_next(self) -> None:
        """Select the next item."""
        if self.items and self.selected_index < len(self.items) - 1:
            self.selected_index += 1

    def select_prev(self) -> None:
        """Select the previous item."""
        if self.selected_index > 0:
            self.selected_index -= 1

    def get_selected(self) -> Optional[MenuItem]:
        """Get the currently selected item.

        Returns:
            Selected MenuItem, or None if no items.
        """
        if self.items and 0 <= self.selected_index < len(self.items):
            return self.items[self.selected_index]
        return None

    def get_selected_action(self) -> Optional[str]:
        """Get the action string of the selected item.

        Returns:
            Action string, or None if no selection.
        """
        item = self.get_selected()
        return item.action if item else None

    def handle_key(self, key: int) -> Optional[str]:
        """Handle a keypress in the menu.

        Args:
            key: The key code pressed.

        Returns:
            Action string if item selected, None otherwise.
        """
        if key == curses.KEY_UP:
            self.select_prev()
            return None
        elif key == curses.KEY_DOWN:
            self.select_next()
            return None
        elif key == 10 or key == 13:  # Enter
            return self.get_selected_action()
        elif key == 27:  # Escape
            self.hide()
            return None

        # Check for hotkeys
        for item in self.items:
            if item.hotkey and chr(key).lower() == item.hotkey.lower():
                return item.action

        return None

    def draw(self) -> None:
        """Render the menu overlay."""
        if not self.visible or not self.items:
            return

        # Calculate menu dimensions
        max_label_len = max(len(item.label) for item in self.items)
        menu_width = max(len(self.title), max_label_len) + 6
        menu_height = len(self.items) + 4  # title + border + items + border

        screen_height, screen_width = self.stdscr.getmaxyx()

        # Clamp position to screen
        x = min(self.x, screen_width - menu_width - 1)
        y = min(self.y, screen_height - menu_height - 1)
        x = max(0, x)
        y = max(0, y)

        # Draw menu background
        for row in range(menu_height):
            try:
                self.stdscr.addstr(
                    y + row, x,
                    " " * menu_width,
                    curses.color_pair(ColorPair.MENU_BG),
                )
            except curses.error:
                pass

        # Draw border
        try:
            # Top border
            self.stdscr.addstr(
                y, x,
                "┌" + "─" * (menu_width - 2) + "┐",
                curses.color_pair(ColorPair.MENU_BG),
            )
            # Title
            title_padded = f" {self.title} ".center(menu_width - 2)
            self.stdscr.addstr(
                y + 1, x,
                "│" + title_padded + "│",
                curses.color_pair(ColorPair.MENU_BG) | curses.A_BOLD,
            )
            # Separator
            self.stdscr.addstr(
                y + 2, x,
                "├" + "─" * (menu_width - 2) + "┤",
                curses.color_pair(ColorPair.MENU_BG),
            )
            # Items
            for i, item in enumerate(self.items):
                row = y + 3 + i
                if i == self.selected_index:
                    attr = curses.color_pair(ColorPair.MENU_SELECT)
                    prefix = "▸ "
                else:
                    attr = curses.color_pair(ColorPair.MENU_BG)
                    prefix = "  "

                label = prefix + item.label
                label_padded = label.ljust(menu_width - 2)
                self.stdscr.addstr(row, x, "│", curses.color_pair(ColorPair.MENU_BG))
                self.stdscr.addstr(row, x + 1, label_padded, attr)
                self.stdscr.addstr(
                    row, x + menu_width - 1,
                    "│",
                    curses.color_pair(ColorPair.MENU_BG),
                )

            # Bottom border
            self.stdscr.addstr(
                y + menu_height - 1, x,
                "└" + "─" * (menu_width - 2) + "┘",
                curses.color_pair(ColorPair.MENU_BG),
            )
        except curses.error:
            pass


# Predefined menu configurations
LEFT_MENU_ITEMS = [
    MenuItem("Reroll", "reroll", "Regenerate with same settings"),
    MenuItem("Reroll Unbounded", "reroll_unbounded", "Regenerate without token limit"),
    MenuItem("Reroll w/ Instructions", "reroll_instruct", "Regenerate with guidance"),
]

RIGHT_MENU_ITEMS = [
    MenuItem("Fix", "fix", "Clean up output issues"),
    MenuItem("Condense", "condense", "Shorten while preserving meaning"),
    MenuItem("Expand", "expand", "Add detail and length"),
    MenuItem("Custom", "custom", "Apply custom instructions"),
]


def create_left_menu(stdscr: "curses.window", x: int, y: int) -> Menu:
    """Create the left (regeneration) menu.

    Args:
        stdscr: Main screen.
        x: X position.
        y: Y position.

    Returns:
        Configured Menu instance.
    """
    return Menu(stdscr, "Regenerate", LEFT_MENU_ITEMS, x, y)


def create_right_menu(stdscr: "curses.window", x: int, y: int) -> Menu:
    """Create the right (edit operations) menu.

    Args:
        stdscr: Main screen.
        x: X position.
        y: Y position.

    Returns:
        Configured Menu instance.
    """
    return Menu(stdscr, "Edit", RIGHT_MENU_ITEMS, x, y)
