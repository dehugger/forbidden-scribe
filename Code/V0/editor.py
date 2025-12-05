"""Editor state machine and main application logic."""

import curses
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from queue import Queue, Empty
from typing import Optional

from logging_config import get_logger, setup_logging
from models.config import AppConfig, Secrets
from models.document import Document
from models.passage import Passage
from agents.base import AgentResult
from agents.edit_agent import EditAgent
from agents.fix_agent import FixAgent
from agents.condense_agent import CondenseAgent
from agents.expand_agent import ExpandAgent
from wrappers.llm_client import OpenAICompatibleClient
from ui.base import ColorPair, setup_colors, safe_addstr
from ui.passage_panel import PassagePanel
from ui.input_panel import InputPanel
from ui.menu import Menu, create_left_menu, create_right_menu


class EditorMode(Enum):
    """Editor operating modes."""

    PASSAGES = auto()      # Navigating passage list
    INPUT = auto()         # Typing in input panel
    EDIT_PASSAGE = auto()  # Editing a passage inline
    MENU_LEFT = auto()     # Left menu open
    MENU_RIGHT = auto()    # Right menu open
    PROMPT_SAVE = auto()   # Save dialog
    PROMPT_INPUT = auto()  # Generic input prompt


@dataclass
class EditorState:
    """Centralized editor state."""

    mode: EditorMode = EditorMode.INPUT
    document: Document = field(default_factory=Document.new)
    running: bool = True
    processing: bool = False
    status_message: str = "Ready"
    spinner_chars: str = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    spinner_idx: int = 0


class ForbiddenScribeEditor:
    """Main editor application.

    Manages the TUI, document state, API interactions, and user input.
    """

    def __init__(self, stdscr: "curses.window", config_dir: Path) -> None:
        """Initialize the editor.

        Args:
            stdscr: Main curses screen.
            config_dir: Directory containing config.json and secrets.json.
        """
        self.stdscr = stdscr
        self.config_dir = config_dir
        self.logger = get_logger("editor")

        # Load configuration
        self.config = AppConfig.load(config_dir / "config.json")
        self.secrets = Secrets.load(config_dir / "secrets.json")

        # Validate API key
        if not self.secrets.is_valid():
            raise ValueError(
                "API key not configured. Set FS_API_KEY environment variable "
                "or edit secrets.json to add your API key."
            )

        # Initialize curses
        curses.curs_set(1)
        setup_colors()
        self.stdscr.nodelay(True)
        self.stdscr.keypad(True)

        # Initialize state
        self.state = EditorState()

        # Response queue for API calls
        self.response_queue: Queue = Queue()

        # Initialize LLM client
        self.llm_client = OpenAICompatibleClient(
            api_key=self.secrets.api_key,
            base_url=self.config.api.api_url,
            model=self.config.api.model_name,
            logger=get_logger("llm"),
        )

        # Initialize agents
        prompt_path = config_dir / self.config.default_prompt_path
        self.edit_agent = EditAgent(self.llm_client, prompt_path)
        self.fix_agent = FixAgent(self.llm_client)
        self.condense_agent = CondenseAgent(self.llm_client)
        self.expand_agent = ExpandAgent(self.llm_client)

        # Create windows and panels
        self._create_windows()

        # Create menus
        self.left_menu: Optional[Menu] = None
        self.right_menu: Optional[Menu] = None

        self.logger.info("Editor initialized")

    def _create_windows(self) -> None:
        """Create or recreate windows based on terminal size."""
        height, width = self.stdscr.getmaxyx()

        # Layout: header(1) + passages(75%) + input(25%) + footer(1)
        content_height = height - 2
        self.passage_height = max(3, int(content_height * 0.75))
        self.input_height = max(3, content_height - self.passage_height)

        # Create windows
        try:
            self.passage_win = curses.newwin(
                self.passage_height, width, 1, 0
            )
            self.input_win = curses.newwin(
                self.input_height, width, 1 + self.passage_height, 0
            )
            self.passage_win.keypad(True)
            self.input_win.keypad(True)
        except curses.error:
            pass

        # Create panels
        self.passage_panel = PassagePanel(
            self.passage_win, self.state.document.passages
        )
        self.input_panel = InputPanel(self.input_win)

        # Set initial focus
        self._update_focus()

    def _update_focus(self) -> None:
        """Update panel focus based on mode."""
        if self.state.mode == EditorMode.INPUT:
            self.passage_panel.focused = False
            self.input_panel.focused = True
        elif self.state.mode == EditorMode.PASSAGES:
            self.passage_panel.focused = True
            self.input_panel.focused = False
        else:
            # Menus or prompts - dim both
            self.passage_panel.focused = False
            self.input_panel.focused = False

    def _draw_header(self) -> None:
        """Draw the header line."""
        height, width = self.stdscr.getmaxyx()

        filename = self.state.document.meta.document_name
        if self.state.document.file_path:
            filename = self.state.document.file_path.name
        modified = "*" if self.state.document.modified else ""

        mode_str = {
            EditorMode.PASSAGES: "PASSAGES",
            EditorMode.INPUT: "INPUT",
            EditorMode.EDIT_PASSAGE: "EDIT",
            EditorMode.MENU_LEFT: "MENU",
            EditorMode.MENU_RIGHT: "MENU",
        }.get(self.state.mode, "")

        header = f" Forbidden Scribe: {filename}{modified} | {mode_str} "
        header = header.ljust(width)[:width - 1]

        try:
            self.stdscr.attron(curses.color_pair(ColorPair.HEADER))
            self.stdscr.addstr(0, 0, header)
            self.stdscr.attroff(curses.color_pair(ColorPair.HEADER))
        except curses.error:
            pass

    def _draw_footer(self) -> None:
        """Draw the footer line."""
        height, width = self.stdscr.getmaxyx()

        # Show spinner when processing
        if self.state.processing:
            self.state.spinner_idx = (
                (self.state.spinner_idx + 1) % len(self.state.spinner_chars)
            )
            spinner = self.state.spinner_chars[self.state.spinner_idx]
            status = f"{spinner} {self.state.status_message}"
        else:
            status = self.state.status_message

        if self.state.mode == EditorMode.INPUT:
            help_text = "TAB:Passages | Ctrl+D:Send | Ctrl+S:Save | Ctrl+Q:Quit"
        elif self.state.mode == EditorMode.PASSAGES:
            help_text = "TAB:Input | ←/→:Menu | Enter:Edit | Ctrl+S:Save | Ctrl+Q:Quit"
        elif self.state.mode in (EditorMode.MENU_LEFT, EditorMode.MENU_RIGHT):
            help_text = "↑/↓:Select | Enter:Confirm | Esc:Cancel"
        else:
            help_text = "Esc:Cancel | Ctrl+S:Save | Ctrl+Q:Quit"

        footer = f" {status} | {help_text} "
        footer = footer.ljust(width)[:width - 1]

        try:
            self.stdscr.attron(curses.color_pair(ColorPair.FOOTER))
            self.stdscr.addstr(height - 1, 0, footer)
            self.stdscr.attroff(curses.color_pair(ColorPair.FOOTER))
        except curses.error:
            pass

    def _refresh_all(self) -> None:
        """Refresh all windows."""
        self.stdscr.noutrefresh()
        self._draw_header()
        self._draw_footer()
        self.stdscr.noutrefresh()

        self.passage_panel.update_passages(self.state.document.passages)
        self.passage_panel.draw()
        self.input_panel.draw()

        # Draw menus if visible
        if self.left_menu and self.left_menu.visible:
            self.left_menu.draw()
        if self.right_menu and self.right_menu.visible:
            self.right_menu.draw()

        curses.doupdate()

    def _send_to_api(self) -> None:
        """Send input text to API for editing."""
        text = self.input_panel.get_text().strip()
        if not text:
            self.state.status_message = "Empty input"
            return

        self.logger.info(f"Sending to API: {len(text)} chars")
        self.state.processing = True
        self.state.status_message = "Sending to API..."

        # Get context from existing passages
        context = ""
        if self.state.document.passages:
            context = self.state.document.get_context_text(
                len(self.state.document.passages),
                self.config.context_chars,
            )

        # Run API call in background thread
        thread = threading.Thread(
            target=self._api_call_thread,
            args=(text, context, "edit"),
            daemon=True,
        )
        thread.start()

    def _execute_passage_operation(self, operation: str) -> None:
        """Execute an operation on the selected passage.

        Args:
            operation: Operation to perform (fix, condense, expand, etc.)
        """
        passage = self.passage_panel.get_selected()
        if not passage:
            self.state.status_message = "No passage selected"
            return

        self.logger.info(f"Executing {operation} on passage {passage.id}")
        self.state.processing = True
        self.state.status_message = f"Running {operation}..."

        # Get context
        idx = self.passage_panel.selected_index
        preceding = self.state.document.get_context_text(
            idx, self.config.context_chars
        )
        subsequent = self.state.document.get_subsequent_text(
            idx, self.config.context_chars
        )

        # Run in background
        thread = threading.Thread(
            target=self._operation_thread,
            args=(passage, operation, preceding, subsequent),
            daemon=True,
        )
        thread.start()

    def _api_call_thread(
        self,
        text: str,
        context: str,
        operation: str,
    ) -> None:
        """API call thread for new passages."""
        try:
            result = self.edit_agent.execute(
                text=text,
                preceding_context=context,
                max_tokens=self.config.api.max_output_tokens,
                temperature=self.config.api.temperature,
            )
            self.response_queue.put({
                "type": "new_passage",
                "user_entry": text,
                "result": result,
            })
        except Exception as e:
            self.logger.error(f"API error: {e}")
            self.response_queue.put({
                "type": "error",
                "error": str(e),
            })

    def _operation_thread(
        self,
        passage: Passage,
        operation: str,
        preceding: str,
        subsequent: str,
    ) -> None:
        """Operation thread for passage modifications."""
        try:
            agent = {
                "fix": self.fix_agent,
                "condense": self.condense_agent,
                "expand": self.expand_agent,
                "reroll": self.edit_agent,
                "reroll_unbounded": self.edit_agent,
            }.get(operation, self.edit_agent)

            max_tokens = None
            if operation == "reroll_unbounded":
                max_tokens = None  # Unbounded
            elif operation != "reroll":
                max_tokens = self.config.api.max_output_tokens

            # For reroll operations, use original user_entry
            text = passage.user_entry if "reroll" in operation else passage.text

            result = agent.execute(
                text=text,
                preceding_context=preceding,
                subsequent_context=subsequent,
                max_tokens=max_tokens,
                temperature=self.config.api.temperature,
            )

            self.response_queue.put({
                "type": "passage_update",
                "passage_id": passage.id,
                "operation": operation,
                "result": result,
            })
        except Exception as e:
            self.logger.error(f"Operation error: {e}")
            self.response_queue.put({
                "type": "error",
                "error": str(e),
            })

    def _process_queue(self) -> None:
        """Process items from the response queue."""
        try:
            while True:
                item = self.response_queue.get_nowait()

                if item["type"] == "new_passage":
                    result: AgentResult = item["result"]
                    if result.success:
                        self.state.document.add_passage(
                            user_entry=item["user_entry"],
                            ai_response=result.text,
                            model=result.model,
                        )
                        self.input_panel.clear()
                        self.passage_panel.select_last()
                        self.state.status_message = "Passage added"
                    else:
                        self.state.status_message = f"Error: {result.error}"

                elif item["type"] == "passage_update":
                    result = item["result"]
                    if result.success:
                        passage = self.state.document.get_passage_by_id(
                            item["passage_id"]
                        )
                        if passage:
                            passage.update_text(
                                result.text,
                                item["operation"],
                                result.model,
                            )
                            self.state.document.modified = True
                        self.state.status_message = f"{item['operation'].title()} complete"
                    else:
                        self.state.status_message = f"Error: {result.error}"

                elif item["type"] == "error":
                    self.state.status_message = f"Error: {item['error'][:50]}"

                self.state.processing = False

        except Empty:
            pass

    def _prompt_save(self) -> Optional[str]:
        """Prompt user for save confirmation.

        Returns:
            'y' to save, 'n' to discard, 'c' to cancel.
        """
        height, width = self.stdscr.getmaxyx()
        prompt = "Save before quitting? (y/n/c): "

        self.stdscr.attron(curses.color_pair(ColorPair.HEADER))
        self.stdscr.addstr(height - 1, 0, " " * (width - 1))
        self.stdscr.addstr(height - 1, 0, prompt)
        self.stdscr.attroff(curses.color_pair(ColorPair.HEADER))
        self.stdscr.refresh()

        self.stdscr.nodelay(False)
        try:
            key = self.stdscr.getch()
            if key in (ord('y'), ord('Y')):
                return 'y'
            elif key in (ord('n'), ord('N')):
                return 'n'
            else:
                return 'c'
        finally:
            self.stdscr.nodelay(True)

    def _prompt_filename(self) -> Optional[Path]:
        """Prompt user for a filename.

        Returns:
            Path to save to, or None if cancelled.
        """
        height, width = self.stdscr.getmaxyx()
        prompt = "Filename: "
        default = "document.json"

        self.stdscr.attron(curses.color_pair(ColorPair.HEADER))
        self.stdscr.addstr(height - 1, 0, " " * (width - 1))
        self.stdscr.addstr(height - 1, 0, prompt)
        self.stdscr.attroff(curses.color_pair(ColorPair.HEADER))
        self.stdscr.refresh()

        curses.echo()
        self.stdscr.nodelay(False)
        try:
            filename_bytes = self.stdscr.getstr(height - 1, len(prompt), 255)
            filename = filename_bytes.decode('utf-8').strip()
            if not filename:
                filename = default
            # Add .json extension if not present
            if not filename.endswith('.json'):
                filename += '.json'
            return self.config_dir / "works" / filename
        except (curses.error, UnicodeDecodeError):
            return None
        finally:
            curses.noecho()
            self.stdscr.nodelay(True)

    def _save_document(self) -> bool:
        """Save the current document.

        Returns:
            True if save succeeded.
        """
        path = self.state.document.file_path
        if not path:
            path = self._prompt_filename()
            if not path:
                return False

        # Ensure works directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        if self.state.document.save(path):
            self.state.status_message = f"Saved: {path.name}"
            self.logger.info(f"Document saved: {path}")
            return True
        else:
            self.state.status_message = "Save failed"
            return False

    def _handle_global_keys(self, key: int) -> bool:
        """Handle global keybindings.

        Args:
            key: Key code.

        Returns:
            True if key was handled.
        """
        if key == 17:  # Ctrl+Q - Quit
            if self.state.document.modified:
                choice = self._prompt_save()
                if choice == 'y':
                    self._save_document()
                    self.state.running = False
                elif choice == 'n':
                    self.state.running = False
                # else cancel
            else:
                self.state.running = False
            return True

        elif key == 19:  # Ctrl+S - Save
            self._save_document()
            return True

        elif key == 9:  # Tab - Switch focus
            if self.state.mode == EditorMode.INPUT:
                self.state.mode = EditorMode.PASSAGES
            elif self.state.mode == EditorMode.PASSAGES:
                self.state.mode = EditorMode.INPUT
            self._update_focus()
            return True

        return False

    def _handle_input_mode_keys(self, key: int) -> None:
        """Handle keys in input mode."""
        if key == 4:  # Ctrl+D - Send
            if not self.state.processing:
                self._send_to_api()
        else:
            self.input_panel.handle_key(key)

    def _handle_passages_mode_keys(self, key: int) -> None:
        """Handle keys in passages mode."""
        if key == curses.KEY_UP:
            self.passage_panel.select_prev()
        elif key == curses.KEY_DOWN:
            self.passage_panel.select_next()
        elif key == curses.KEY_LEFT:
            # Open left menu
            self._open_left_menu()
        elif key == curses.KEY_RIGHT:
            # Open right menu
            self._open_right_menu()
        elif key == 10 or key == 13:  # Enter - Edit passage
            # TODO: Implement passage edit mode
            self.state.status_message = "Passage edit mode not yet implemented"

    def _open_left_menu(self) -> None:
        """Open the left (regeneration) menu."""
        if not self.passage_panel.get_selected():
            self.state.status_message = "No passage selected"
            return

        height, _ = self.stdscr.getmaxyx()
        self.left_menu = create_left_menu(self.stdscr, 2, 3)
        self.left_menu.show()
        self.state.mode = EditorMode.MENU_LEFT
        self._update_focus()

    def _open_right_menu(self) -> None:
        """Open the right (edit operations) menu."""
        if not self.passage_panel.get_selected():
            self.state.status_message = "No passage selected"
            return

        _, width = self.stdscr.getmaxyx()
        self.right_menu = create_right_menu(self.stdscr, width - 30, 3)
        self.right_menu.show()
        self.state.mode = EditorMode.MENU_RIGHT
        self._update_focus()

    def _handle_menu_keys(self, key: int) -> None:
        """Handle keys when a menu is open."""
        menu = self.left_menu if self.state.mode == EditorMode.MENU_LEFT else self.right_menu
        if not menu:
            return

        action = menu.handle_key(key)

        if action:
            # Execute the selected action
            menu.hide()
            self.state.mode = EditorMode.PASSAGES
            self._update_focus()

            if action in ("reroll", "reroll_unbounded", "reroll_instruct"):
                if action == "reroll_instruct":
                    # TODO: Prompt for instructions
                    self.state.status_message = "Custom instructions not yet implemented"
                else:
                    self._execute_passage_operation(action)
            elif action in ("fix", "condense", "expand"):
                self._execute_passage_operation(action)
            elif action == "custom":
                # TODO: Prompt for custom instructions
                self.state.status_message = "Custom instructions not yet implemented"

        elif key == 27:  # Escape
            menu.hide()
            self.state.mode = EditorMode.PASSAGES
            self._update_focus()

    def run(self) -> None:
        """Main application loop."""
        self.logger.info("Starting main loop")

        while self.state.running:
            # Handle terminal resize
            if curses.is_term_resized(curses.LINES, curses.COLS):
                curses.update_lines_cols()
                self._create_windows()
                self.stdscr.clear()

            # Process API responses
            self._process_queue()

            # Draw UI
            self._refresh_all()

            # Handle input
            try:
                key = self.stdscr.getch()
            except curses.error:
                key = -1

            if key == -1:
                curses.napms(50)
                continue

            # Handle global keys first
            if self._handle_global_keys(key):
                continue

            # Handle mode-specific keys
            if self.state.mode == EditorMode.INPUT:
                self._handle_input_mode_keys(key)
            elif self.state.mode == EditorMode.PASSAGES:
                self._handle_passages_mode_keys(key)
            elif self.state.mode in (EditorMode.MENU_LEFT, EditorMode.MENU_RIGHT):
                self._handle_menu_keys(key)

        self.logger.info("Application shutdown")
