"""UI components for the terminal interface."""

from ui.base import ColorPair, setup_colors
from ui.passage_panel import PassagePanel
from ui.input_panel import InputPanel
from ui.menu import Menu, MenuItem

__all__ = [
    "ColorPair",
    "setup_colors",
    "PassagePanel",
    "InputPanel",
    "Menu",
    "MenuItem",
]
