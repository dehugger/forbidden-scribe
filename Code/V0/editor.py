"""Editor state machine and main application logic."""

import curses
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from queue import Queue, Empty
from typing import Optional

from logging_config import get_logger, setup_logging
from models.config import AppConfig, Secrets
from models.document import Document
from models.passage import Passage, PassageAuditEntry
from agents.base import AgentResult
from agents.edit_agent import EditAgent
from agents.fix_agent import FixAgent
from agents.condense_agent import CondenseAgent
from agents.expand_agent import ExpandAgent
from wrappers.llm_client import OpenAICompatibleClient
from ui.base import ColorPair, setup_colors, safe_addstr
from ui.passage_panel import PassagePanel
from ui.input_panel import InputPanel
from ui.edit_panel import EditPanel
from ui.menu import Menu, create_left_menu, create_right_menu
from ui.debug_panel import DebugPanel, DebugPanelHandler


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

    def __init__(
        self,
        stdscr: "curses.window",
        config_dir: Path,
        debug: bool = False,
    ) -> None:
        """Initialize the editor.

        Args:
            stdscr: Main curses screen.
            config_dir: Directory containing config.json and secrets.json.
            debug: Enable debug panel with scrolling log output.
        """
        self.stdscr = stdscr
        self.config_dir = config_dir
        self.debug_mode = debug
        self.logger = get_logger("editor")

        # Load configuration
        self.config = AppConfig.load(config_dir / "config.json")
        self.secrets = Secrets.load(config_dir / "secrets.json")

        # Initialize curses
        curses.curs_set(1)
        setup_colors()
        self.stdscr.nodelay(True)
        self.stdscr.keypad(True)

        # Initialize state
        self.state = EditorState()

        # Response queue for API calls
        self.response_queue: Queue = Queue()

        # Initialize LLM client and agents
        # Note: Empty string API key is valid for APIs without authentication
        self.llm_client = OpenAICompatibleClient(
            api_key=self.secrets.api_key,
            base_url=self.config.api.api_url,
            model=self.config.api.model_name,
            logger=get_logger("llm"),
            debug=self.debug_mode,
        )
        prompt_path = config_dir / self.config.default_prompt_path
        self.edit_agent = EditAgent(self.llm_client, prompt_path)
        self.fix_agent = FixAgent(self.llm_client)
        self.condense_agent = CondenseAgent(self.llm_client)
        self.expand_agent = ExpandAgent(self.llm_client)

        # Create menus
        self.left_menu: Optional[Menu] = None
        self.right_menu: Optional[Menu] = None

        # Debug panel (created in _create_windows if debug_mode)
        self.debug_panel: Optional[DebugPanel] = None
        self.debug_handler: Optional[DebugPanelHandler] = None

        # Create windows and panels
        self._create_windows()

        # Attach debug handler to root logger if debug mode
        if self.debug_mode:
            self._setup_debug_logging()
            self._log_config()

        self.logger.info("Editor initialized")

    def _create_windows(self) -> None:
        """Create or recreate windows based on terminal size."""
        height, width = self.stdscr.getmaxyx()

        # Calculate main content width (leave space for debug if enabled)
        if self.debug_mode:
            # Split: 60% main content, 40% debug panel
            main_width = max(40, int(width * 0.6))
            debug_width = width - main_width
        else:
            main_width = width
            debug_width = 0

        # Layout: header(1) + passages(75%) + input(25%) + footer(1)
        content_height = height - 2
        self.passage_height = max(3, int(content_height * 0.75))
        self.input_height = max(3, content_height - self.passage_height)

        # Create windows
        try:
            self.passage_win = curses.newwin(
                self.passage_height, main_width, 1, 0
            )
            self.input_win = curses.newwin(
                self.input_height, main_width, 1 + self.passage_height, 0
            )
            self.passage_win.keypad(True)
            self.input_win.keypad(True)

            # Create debug window if enabled
            if self.debug_mode and debug_width > 10:
                self.debug_win = curses.newwin(
                    content_height, debug_width, 1, main_width
                )
                self.debug_win.keypad(True)
        except curses.error:
            pass

        # Create panels
        self.passage_panel = PassagePanel(
            self.passage_win, self.state.document.passages
        )
        self.input_panel = InputPanel(self.input_win)
        self.edit_panel: Optional[EditPanel] = None  # Created when entering edit mode

        # Create debug panel if enabled
        if self.debug_mode and hasattr(self, 'debug_win'):
            self.debug_panel = DebugPanel(self.debug_win)
            # Re-attach handler to new panel if it exists
            if self.debug_handler:
                self.debug_handler.panel = self.debug_panel

        # Set initial focus
        self._update_focus()

    def _update_focus(self) -> None:
        """Update panel focus based on mode."""
        if self.state.mode == EditorMode.INPUT:
            self.passage_panel.focused = False
            self.input_panel.focused = True
            if self.edit_panel:
                self.edit_panel.focused = False
        elif self.state.mode == EditorMode.PASSAGES:
            self.passage_panel.focused = True
            self.input_panel.focused = False
            if self.edit_panel:
                self.edit_panel.focused = False
        elif self.state.mode == EditorMode.EDIT_PASSAGE:
            self.passage_panel.focused = False
            self.input_panel.focused = False
            if self.edit_panel:
                self.edit_panel.focused = True
        else:
            # Menus or prompts - dim all
            self.passage_panel.focused = False
            self.input_panel.focused = False
            if self.edit_panel:
                self.edit_panel.focused = False

    def _setup_debug_logging(self) -> None:
        """Set up logging handler for debug panel."""
        # Create a temporary panel for the handler
        # (will be replaced when windows are created)
        if not self.debug_panel:
            # Create a minimal panel that will be replaced
            height, width = self.stdscr.getmaxyx()
            temp_win = curses.newwin(height - 2, width // 3, 1, width * 2 // 3)
            self.debug_panel = DebugPanel(temp_win)

        # Create and attach handler
        self.debug_handler = DebugPanelHandler(self.debug_panel)
        self.debug_handler.setLevel(logging.DEBUG)

        # Add to root logger to capture all log messages
        root_logger = logging.getLogger()
        root_logger.addHandler(self.debug_handler)

    def _log_config(self) -> None:
        """Log all configuration settings when debug mode is enabled."""
        self.logger.info("=== Configuration Settings ===")
        self.logger.info(f"Config directory: {self.config_dir}")

        # API configuration
        self.logger.info("--- API Config ---")
        self.logger.info(f"  api_url: {self.config.api.api_url}")
        self.logger.info(f"  api_spec: {self.config.api.api_spec}")
        self.logger.info(f"  model_name: {self.config.api.model_name}")
        self.logger.info(f"  temperature: {self.config.api.temperature}")
        self.logger.info(f"  max_input_tokens: {self.config.api.max_input_tokens}")
        self.logger.info(f"  max_output_tokens: {self.config.api.max_output_tokens}")
        self.logger.info(f"  structured_output_schema: {self.config.api.structured_output_schema}")

        # App configuration
        self.logger.info("--- App Config ---")
        self.logger.info(f"  default_prompt_path: {self.config.default_prompt_path}")
        self.logger.info(f"  log_path: {self.config.log_path}")
        self.logger.info(f"  context_chars: {self.config.context_chars}")
        self.logger.info(f"  works_directory: {self.config.works_directory}")

        # Secrets (redacted)
        self.logger.info("--- Secrets ---")
        api_key_display = (
            f"{self.secrets.api_key[:8]}..."
            if len(self.secrets.api_key) > 8
            else "[empty]" if not self.secrets.api_key
            else "[too short to redact]"
        )
        self.logger.info(f"  api_key: {api_key_display}")
        self.logger.info("=== End Configuration ===")

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

        header = f"── Forbidden Scribe: {filename}{modified} | {mode_str} "
        # Pad with box-drawing line character
        header = header + "─" * (width - len(header) - 1)
        header = header[:width - 1]

        try:
            attr = curses.color_pair(ColorPair.HEADER) | curses.A_BOLD
            self.stdscr.addstr(0, 0, header, attr)
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
            help_text = "TAB:Passages | Enter/Ctrl+D:Send | Ctrl+S:Save | Ctrl+Q:Quit"
        elif self.state.mode == EditorMode.PASSAGES:
            help_text = "TAB:Input | ←→:Menu | Enter:Edit | ESC:Back"
        elif self.state.mode == EditorMode.EDIT_PASSAGE:
            help_text = "Ctrl+S:Save Changes | ESC:Cancel"
        elif self.state.mode in (EditorMode.MENU_LEFT, EditorMode.MENU_RIGHT):
            help_text = "↑↓:Select | Enter:Confirm | ESC:Cancel"
        else:
            help_text = "ESC:Back | Ctrl+S:Save | Ctrl+Q:Quit"

        footer = f"─ {status} │ {help_text} "
        footer = "─" * (width - len(footer) - 1) + footer
        footer = footer[:width - 1]

        try:
            attr = curses.color_pair(ColorPair.FOOTER)
            self.stdscr.addstr(height - 1, 0, footer, attr)
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

        # Draw appropriate input panel based on mode
        if self.state.mode == EditorMode.EDIT_PASSAGE and self.edit_panel:
            self.edit_panel.draw()
        else:
            self.input_panel.draw()

        # Draw debug panel if enabled
        if self.debug_panel:
            self.debug_panel.draw()

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

        # Create pending passage immediately
        pending_passage = self.state.document.add_pending_passage(text)
        self.passage_panel.update_passages(self.state.document.passages)
        self.passage_panel.select_last()
        self.input_panel.clear()

        self.state.processing = True
        self.state.status_message = "Sending to API..."

        # Get context from existing passages (excluding the pending one)
        # Only if send_prepend_passage is enabled in document meta
        context = ""
        if (self.state.document.meta.send_prepend_passage
                and len(self.state.document.passages) > 1):
            context = self.state.document.get_context_text(
                len(self.state.document.passages) - 1,
                self.config.context_chars,
            )

        # Run API call in background thread
        thread = threading.Thread(
            target=self._api_call_thread,
            args=(pending_passage.id, text, context, "edit"),
            daemon=True,
        )
        thread.start()

    def _execute_passage_operation(
        self,
        operation: str,
        custom_instructions: str = "",
    ) -> None:
        """Execute an operation on the selected passage.

        Args:
            operation: Operation to perform (fix, condense, expand, etc.)
            custom_instructions: Optional custom instructions for the operation.
        """
        passage = self.passage_panel.get_selected()
        if not passage:
            self.state.status_message = "No passage selected"
            return

        self.logger.info(f"Executing {operation} on passage {passage.id}")
        self.state.processing = True
        self.state.status_message = f"Running {operation}..."

        # Get context only if enabled in document meta
        idx = self.passage_panel.selected_index
        preceding = ""
        subsequent = ""
        if self.state.document.meta.send_prepend_passage:
            preceding = self.state.document.get_context_text(
                idx, self.config.context_chars
            )
        if self.state.document.meta.send_append_text:
            subsequent = self.state.document.get_subsequent_text(
                idx, self.config.context_chars
            )

        # Run in background
        thread = threading.Thread(
            target=self._operation_thread,
            args=(passage, operation, preceding, subsequent, custom_instructions),
            daemon=True,
        )
        thread.start()

    def _api_call_thread(
        self,
        passage_id: str,
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
                "passage_id": passage_id,
                "user_entry": text,
                "result": result,
            })
        except Exception as e:
            self.logger.error(f"API error: {e}")
            self.response_queue.put({
                "type": "error",
                "passage_id": passage_id,
                "error": str(e),
            })

    def _operation_thread(
        self,
        passage: Passage,
        operation: str,
        preceding: str,
        subsequent: str,
        custom_instructions: str = "",
    ) -> None:
        """Operation thread for passage modifications."""
        try:
            agent = {
                "fix": self.fix_agent,
                "condense": self.condense_agent,
                "expand": self.expand_agent,
                "reroll": self.edit_agent,
                "reroll_unbounded": self.edit_agent,
                "reroll_instruct": self.edit_agent,
                "custom": self.edit_agent,
            }.get(operation, self.edit_agent)

            max_tokens = None
            if operation == "reroll_unbounded":
                max_tokens = None  # Unbounded
            elif operation not in ("reroll", "reroll_instruct"):
                max_tokens = self.config.api.max_output_tokens

            # Left menu (reroll operations): use original user_entry
            # Right menu (refactor operations): use current passage.text
            if "reroll" in operation:
                text = passage.user_entry
            else:
                # fix, condense, expand, custom - work on current text
                text = passage.text

            result = agent.execute(
                text=text,
                preceding_context=preceding,
                subsequent_context=subsequent,
                additional_instructions=custom_instructions,
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
                    passage = self.state.document.get_passage_by_id(
                        item["passage_id"]
                    )
                    if result.success and passage:
                        # Update the pending passage with AI response
                        passage.ai_response = result.text
                        passage.text = result.text
                        passage.model = result.model
                        passage.pending = False
                        # Log creation
                        passage.audit_log.append(
                            PassageAuditEntry(
                                timestamp=passage.created_at,
                                operation="create",
                                model=result.model,
                                previous_text=None,
                                new_text=result.text,
                            )
                        )
                        self.state.status_message = "Passage added"
                    else:
                        if passage:
                            # Mark as error but keep the passage
                            passage.pending = False
                            passage.text = f"[ERROR: {result.error}]\n\n{passage.user_entry}"
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
                    passage_id = item.get("passage_id")
                    if passage_id:
                        passage = self.state.document.get_passage_by_id(passage_id)
                        if passage:
                            passage.pending = False
                            passage.text = f"[ERROR: {item['error']}]\n\n{passage.user_entry}"
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

    def _prompt_custom_instructions(self) -> Optional[str]:
        """Prompt user for custom instructions.

        Returns:
            Custom instructions string, or None if cancelled.
        """
        height, width = self.stdscr.getmaxyx()
        prompt = "Custom instructions: "

        self.stdscr.attron(curses.color_pair(ColorPair.HEADER))
        self.stdscr.addstr(height - 1, 0, " " * (width - 1))
        self.stdscr.addstr(height - 1, 0, prompt)
        self.stdscr.attroff(curses.color_pair(ColorPair.HEADER))
        self.stdscr.refresh()

        curses.echo()
        self.stdscr.nodelay(False)
        try:
            instructions_bytes = self.stdscr.getstr(
                height - 1, len(prompt), width - len(prompt) - 2
            )
            instructions = instructions_bytes.decode('utf-8').strip()
            return instructions if instructions else None
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
                self.state.status_message = "Save cancelled"
                return False

        success, message = self.state.document.save(path)
        self.state.status_message = message

        if success:
            self.logger.info(f"Document saved: {path}")
        else:
            self.logger.error(f"Save failed: {message}")

        return success

    def _handle_global_keys(self, key: int) -> bool:
        """Handle global keybindings.

        Args:
            key: Key code.

        Returns:
            True if key was handled.
        """
        if key == 27:  # ESC - Exit current mode / go back
            return self._handle_escape()

        elif key == 17:  # Ctrl+Q - Quit
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
            # In edit mode, Ctrl+S saves the edit, not the document
            if self.state.mode == EditorMode.EDIT_PASSAGE:
                return False  # Let edit mode handler deal with it
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

    def _handle_escape(self) -> bool:
        """Handle ESC key - exit current mode, go up one level.

        Returns:
            True (ESC is always handled).
        """
        if self.state.mode == EditorMode.MENU_LEFT:
            if self.left_menu:
                self.left_menu.hide()
            self.state.mode = EditorMode.PASSAGES
            self._update_focus()
        elif self.state.mode == EditorMode.MENU_RIGHT:
            if self.right_menu:
                self.right_menu.hide()
            self.state.mode = EditorMode.PASSAGES
            self._update_focus()
        elif self.state.mode == EditorMode.EDIT_PASSAGE:
            self.state.mode = EditorMode.PASSAGES
            self._update_focus()
        elif self.state.mode == EditorMode.PASSAGES:
            # From passages, go back to input
            self.state.mode = EditorMode.INPUT
            self._update_focus()
        # In INPUT mode, ESC does nothing (already at top level)
        return True

    def _handle_input_mode_keys(self, key: int) -> None:
        """Handle keys in input mode."""
        if key == 10 or key == 13 or key == 4:  # Enter or Ctrl+D - Send
            # Allow sending even while processing (queue multiple requests)
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
            self._enter_edit_mode()

    def _enter_edit_mode(self) -> None:
        """Enter passage edit mode."""
        passage = self.passage_panel.get_selected()
        if not passage:
            self.state.status_message = "No passage selected"
            return

        self.logger.info(f"Entering edit mode for passage {passage.id}")

        # Create edit panel with passage text
        self.edit_panel = EditPanel(self.input_win, passage.text)
        self.state.mode = EditorMode.EDIT_PASSAGE
        self._update_focus()
        self.state.status_message = "Editing passage - ESC to cancel, Ctrl+S to save"

    def _exit_edit_mode(self, save: bool = False) -> None:
        """Exit passage edit mode.

        Args:
            save: If True, save changes to the passage.
        """
        if not self.edit_panel:
            return

        if save:
            passage = self.passage_panel.get_selected()
            if passage:
                new_text = self.edit_panel.get_text()
                if new_text != passage.text:
                    # Update passage with manual edit
                    passage.update_text(new_text, "manual_edit", None)
                    self.state.document.modified = True
                    self.state.status_message = "Passage updated"
                    self.logger.info(f"Passage {passage.id} manually edited")
                else:
                    self.state.status_message = "No changes"
            else:
                self.state.status_message = "No passage selected"
        else:
            self.state.status_message = "Edit cancelled"

        self.edit_panel = None
        self.state.mode = EditorMode.PASSAGES
        self._update_focus()

    def _handle_edit_mode_keys(self, key: int) -> None:
        """Handle keys in edit mode."""
        if not self.edit_panel:
            return

        # Ctrl+S saves the edit
        if key == 19:  # Ctrl+S
            self._exit_edit_mode(save=True)
            return
        # ESC cancels
        elif key == 27:  # ESC
            self._exit_edit_mode(save=False)
            return

        # All other keys pass to edit panel
        self.edit_panel.handle_key(key)

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
                    # Prompt for custom reroll instructions
                    instructions = self._prompt_custom_instructions()
                    if instructions:
                        self._execute_passage_operation(action, instructions)
                    else:
                        self.state.status_message = "Reroll cancelled"
                else:
                    self._execute_passage_operation(action)
            elif action in ("fix", "condense", "expand"):
                self._execute_passage_operation(action)
            elif action == "custom":
                # Prompt for custom refactor instructions
                instructions = self._prompt_custom_instructions()
                if instructions:
                    self._execute_passage_operation(action, instructions)
                else:
                    self.state.status_message = "Custom operation cancelled"

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
            elif self.state.mode == EditorMode.EDIT_PASSAGE:
                self._handle_edit_mode_keys(key)
            elif self.state.mode in (EditorMode.MENU_LEFT, EditorMode.MENU_RIGHT):
                self._handle_menu_keys(key)

        self.logger.info("Application shutdown")
