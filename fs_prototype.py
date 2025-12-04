#!/usr/bin/env python3
"""
Fiction Editing Assistant
A terminal-based text editor that sends drafts to Cerberas AI for polishing.
Uses ncurses for the terminal UI.

Environment variables:
  CERBERAS_API_KEY - Your Cerberas API key (required)
  CERBERAS_MODEL   - Model to use (default: llama3.1-8b)
"""

import curses
import threading
import os
import logging
import json
from openai import OpenAI
from typing import Optional
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
import warnings
from queue import Queue, Empty

SYSTEM_PROMPT = """# Fiction Editing Agent

You transform rough drafts into polished prose. You receive up to 3 pages of content at a time.

## Functions

**Error Correction:** Fix all spelling, grammar, punctuation, and usage errors silently. Do not flag or ask permission.

**Prose Improvement:** Strengthen weak verbs, eliminate redundancy, improve flow. Make minimum necessary changes. Preserve intentional stylistic choices.

**Expansion:** When you encounter markers (`//comment`, `[[comment]]`, `[TODO: x]`), write new prose fulfilling all specified requirements. Match surrounding tone and pacing. Remove markers entirely.

## Context Handling

You may receive `[PRECEDING TEXT]` and `[SUBSEQUENT TEXT]` sections. Use these for continuity, characterization, and consistency. Edit ONLY the `[TEXT TO EDIT]` section.

## Output

Return only the edited text. No explanations, no commentary, no questions. If a critical issue cannot be resolved, append a brief note after `---`.

## Style Guide

**Voice:** Close third person default. Wry, sardonic narrator. Internal monologue is punchy—one or two sentences max.

**Tone:** Dark but not grimdark. Understate emotional beats. Gallows humor welcome. Villains are charismatic and competent.

**Dialogue:** Snappy and natural. People interrupt and trail off. Vary tags with action beats. British English for HP content (git, bloke, mate, bloody, Merlin's beard, rubbish, arse—never "guys," "gotten," or American slang).

**Description:** Moderate density. Few vivid details, then move on. No purple prose, no "orbs" for eyes.

**Sentences:** Vary length deliberately. Short for impact. Fragments acceptable. Parenthetical asides are common (and snarky).

**Pacing:** Action sequences: efficient, kinetic, short sentences. Dialogue: let it breathe. Introspection: tight, never retreading. Use scene breaks (---) liberally.

**Preserve:** Wry self-awareness, absurdist observations mid-crisis, irreverent similes, dark humor touches.

**Avoid:** Melodrama, overwritten description, "as you know Bob" dialogue, attention-seeking dialogue tags, over-explained emotions."""

CONTEXT_SIZE = 2000


class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


def setup_logging() -> logging.Logger:
    """Configure structured JSON logging with rotation."""
    logger = logging.getLogger("fiction_editor")
    logger.setLevel(logging.DEBUG)
    os.makedirs("logs", exist_ok=True)

    file_handler = RotatingFileHandler(
        "logs/fiction_editor.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    return logger


logger = setup_logging()


class FictionEditor:
    """Terminal-based fiction editor with Claude integration."""

    def __init__(self, stdscr):
        self.stdscr = stdscr
        logger.info("Initializing Fiction Editor application")

        # Initialize curses
        curses.curs_set(1)  # Show cursor
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)    # Header
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Footer
        curses.init_pair(3, curses.COLOR_GREEN, -1)   # Doc border focused
        curses.init_pair(4, curses.COLOR_YELLOW, -1)  # Input border focused
        curses.init_pair(5, curses.COLOR_WHITE, -1)   # Dim border

        self.stdscr.nodelay(True)  # Non-blocking input
        self.stdscr.keypad(True)   # Enable special keys

        # Initialize Cerberas client (OpenAI-compatible)
        try:
            api_key = os.environ.get("CERBERAS_API_KEY")
            if not api_key:
                raise ValueError("CERBERAS_API_KEY environment variable not set")
            self.model = os.environ.get("CERBERAS_MODEL", "llama3.1-8b")
            self.client = OpenAI(
                base_url="https://api.cerebras.ai/v1",
                api_key=api_key
            )
            logger.info(f"Cerberas client initialized, model: {self.model}")
        except Exception as e:
            logger.error(f"Failed to initialize Cerberas client: {e}")
            raise

        self.response_queue: Queue = Queue()
        self.running = True
        self.processing = False

        # Document state
        self.document_lines: list[str] = [""]
        self.doc_cursor_x: int = 0
        self.doc_cursor_y: int = 0
        self.input_lines: list[str] = [""]
        self.input_cursor_x: int = 0
        self.input_cursor_y: int = 0
        self.status_message: str = "Ready"

        # Spinner for API calls
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.spinner_idx: int = 0

        # File tracking
        self.current_file: Optional[str] = None
        self.modified: bool = False

        # Scrolling and focus
        self.focus: str = "input"  # "document" or "input"
        self.document_scroll: int = 0
        self.input_scroll: int = 0

        # Windows (created in resize handler)
        self.doc_win = None
        self.input_win = None
        self.create_windows()

        logger.info("Fiction Editor application started")

    def wrap_lines(self, lines: list[str], width: int) -> list[str]:
        """Wrap lines to fit within width."""
        wrapped = []
        for line in lines:
            if len(line) <= width:
                wrapped.append(line)
            else:
                # Wrap long lines
                while len(line) > width:
                    wrapped.append(line[:width])
                    line = line[width:]
                wrapped.append(line)
        return wrapped

    def create_windows(self):
        """Create or recreate windows based on terminal size."""
        height, width = self.stdscr.getmaxyx()

        # Layout: header(1) + doc(75%) + input(25%) + footer(1)
        content_height = height - 2
        self.doc_height = max(3, int(content_height * 0.75))
        self.input_height = max(3, content_height - self.doc_height)

        # Create windows (with borders, so content is height-2)
        try:
            self.doc_win = curses.newwin(self.doc_height, width, 1, 0)
            self.input_win = curses.newwin(self.input_height, width, 1 + self.doc_height, 0)
            self.doc_win.keypad(True)
            self.input_win.keypad(True)
        except curses.error:
            pass

    def draw_header(self):
        """Draw the header line."""
        height, width = self.stdscr.getmaxyx()
        filename = self.current_file or "Untitled"
        modified = "*" if self.modified else ""
        focus = "DOC" if self.focus == "document" else "INPUT"
        header = f" Fiction Editor: {filename}{modified} | Focus: {focus} "
        header = header.ljust(width)[:width]

        try:
            self.stdscr.attron(curses.color_pair(1))
            self.stdscr.addstr(0, 0, header[:width-1])
            self.stdscr.attroff(curses.color_pair(1))
        except curses.error:
            pass

    def draw_footer(self):
        """Draw the footer line."""
        height, width = self.stdscr.getmaxyx()

        # Show spinner when processing
        if self.processing:
            self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)
            spinner = self.spinner_chars[self.spinner_idx]
            status = f"{spinner} {self.status_message}"
        else:
            status = self.status_message

        footer = f" {status} | Ctrl+E:Focus | Ctrl+D:Send | Ctrl+S:Save | Ctrl+Q:Quit "
        footer = footer.ljust(width)[:width]

        try:
            self.stdscr.attron(curses.color_pair(2))
            self.stdscr.addstr(height - 1, 0, footer[:width-1])
            self.stdscr.attroff(curses.color_pair(2))
        except curses.error:
            pass

    def draw_document(self):
        """Draw the document panel."""
        if not self.doc_win:
            return

        self.doc_win.erase()
        height, width = self.doc_win.getmaxyx()

        # Draw border
        color = curses.color_pair(3) if self.focus == "document" else curses.color_pair(5)
        self.doc_win.attron(color)
        self.doc_win.border()
        self.doc_win.attroff(color)

        # Content dimensions
        content_height = height - 2
        content_width = width - 2

        # Wrap document lines for display
        wrapped_lines = self.wrap_lines(self.document_lines, content_width)

        # Title
        total = len(wrapped_lines)
        is_empty = (self.document_lines == [""] or self.document_lines == [])
        if is_empty:
            title = " Document (empty) "
        elif total > 0:
            end = min(self.document_scroll + content_height, total)
            title = f" Document (ln {self.document_scroll + 1}-{end}/{total}) "
        else:
            title = " Document "

        try:
            self.doc_win.addstr(0, 2, title[:width-4])
        except curses.error:
            pass

        # Ensure scroll is valid
        max_scroll = max(0, len(wrapped_lines) - content_height)
        self.document_scroll = max(0, min(self.document_scroll, max_scroll))

        for i in range(content_height):
            line_idx = self.document_scroll + i
            if line_idx < len(wrapped_lines):
                line = wrapped_lines[line_idx]
                try:
                    self.doc_win.addstr(i + 1, 1, line)
                except curses.error:
                    pass

        # Position cursor if focused (on unwrapped line)
        if self.focus == "document":
            # Ensure cursor is valid
            if self.doc_cursor_y >= len(self.document_lines):
                self.doc_cursor_y = max(0, len(self.document_lines) - 1)
            if self.document_lines and self.doc_cursor_x > len(self.document_lines[self.doc_cursor_y]):
                self.doc_cursor_x = len(self.document_lines[self.doc_cursor_y])

            # Calculate screen position (account for wrapping)
            screen_line = 0
            for i in range(self.doc_cursor_y):
                if i < len(self.document_lines):
                    line_len = len(self.document_lines[i])
                    screen_line += max(1, (line_len + content_width - 1) // content_width) if line_len > content_width else 1

            # Add offset within current line due to wrapping
            cursor_in_line = self.doc_cursor_x // content_width
            screen_line += cursor_in_line
            cursor_x_in_wrap = self.doc_cursor_x % content_width

            cursor_screen_y = screen_line - self.document_scroll + 1
            cursor_screen_x = cursor_x_in_wrap + 1

            if 0 < cursor_screen_y < height - 1:
                try:
                    self.doc_win.move(cursor_screen_y, cursor_screen_x)
                except curses.error:
                    pass

        self.doc_win.noutrefresh()

    def draw_input(self):
        """Draw the input panel."""
        if not self.input_win:
            return

        self.input_win.erase()
        height, width = self.input_win.getmaxyx()

        # Draw border
        color = curses.color_pair(4) if self.focus == "input" else curses.color_pair(5)
        self.input_win.attron(color)
        self.input_win.border()
        self.input_win.attroff(color)

        # Title
        title = " Input - Ctrl+D to send "
        try:
            self.input_win.addstr(0, 2, title[:width-4])
        except curses.error:
            pass

        # Content
        content_height = height - 2
        content_width = width - 2

        # Ensure scroll is valid
        max_scroll = max(0, len(self.input_lines) - content_height)
        self.input_scroll = max(0, min(self.input_scroll, max_scroll))

        for i in range(content_height):
            line_idx = self.input_scroll + i
            if line_idx < len(self.input_lines):
                line = self.input_lines[line_idx][:content_width]
                try:
                    self.input_win.addstr(i + 1, 1, line)
                except curses.error:
                    pass

        # Position cursor if focused
        if self.focus == "input":
            cursor_screen_y = self.input_cursor_y - self.input_scroll + 1
            cursor_screen_x = min(self.input_cursor_x + 1, content_width)
            if 0 < cursor_screen_y < height - 1:
                try:
                    self.input_win.move(cursor_screen_y, cursor_screen_x)
                except curses.error:
                    pass

        self.input_win.noutrefresh()

    def refresh_all(self):
        """Refresh all windows."""
        self.stdscr.noutrefresh()
        self.draw_header()
        self.draw_footer()
        self.stdscr.noutrefresh()
        self.draw_document()
        self.draw_input()
        curses.doupdate()

    def get_input_text(self) -> str:
        """Get all input text as a single string."""
        return "\n".join(self.input_lines)

    def clear_input(self):
        """Clear the input buffer."""
        self.input_lines = [""]
        self.input_cursor_x = 0
        self.input_cursor_y = 0
        self.input_scroll = 0

    def handle_input_key(self, key: int):
        """Handle keypress in input mode."""
        content_height = self.input_height - 2

        if key == curses.KEY_BACKSPACE or key == 127 or key == 8:
            if self.input_cursor_x > 0:
                line = self.input_lines[self.input_cursor_y]
                self.input_lines[self.input_cursor_y] = line[:self.input_cursor_x-1] + line[self.input_cursor_x:]
                self.input_cursor_x -= 1
                self.modified = True
            elif self.input_cursor_y > 0:
                # Join with previous line
                prev_len = len(self.input_lines[self.input_cursor_y - 1])
                self.input_lines[self.input_cursor_y - 1] += self.input_lines[self.input_cursor_y]
                del self.input_lines[self.input_cursor_y]
                self.input_cursor_y -= 1
                self.input_cursor_x = prev_len
                self.modified = True
                # Adjust scroll
                if self.input_cursor_y < self.input_scroll:
                    self.input_scroll = self.input_cursor_y

        elif key == curses.KEY_DC:  # Delete key
            line = self.input_lines[self.input_cursor_y]
            if self.input_cursor_x < len(line):
                self.input_lines[self.input_cursor_y] = line[:self.input_cursor_x] + line[self.input_cursor_x+1:]
                self.modified = True

        elif key == curses.KEY_LEFT:
            if self.input_cursor_x > 0:
                self.input_cursor_x -= 1

        elif key == curses.KEY_RIGHT:
            if self.input_cursor_x < len(self.input_lines[self.input_cursor_y]):
                self.input_cursor_x += 1

        elif key == curses.KEY_UP:
            if self.input_cursor_y > 0:
                self.input_cursor_y -= 1
                self.input_cursor_x = min(self.input_cursor_x, len(self.input_lines[self.input_cursor_y]))
                if self.input_cursor_y < self.input_scroll:
                    self.input_scroll = self.input_cursor_y

        elif key == curses.KEY_DOWN:
            if self.input_cursor_y < len(self.input_lines) - 1:
                self.input_cursor_y += 1
                self.input_cursor_x = min(self.input_cursor_x, len(self.input_lines[self.input_cursor_y]))
                if self.input_cursor_y >= self.input_scroll + content_height:
                    self.input_scroll = self.input_cursor_y - content_height + 1

        elif key == 10 or key == 13:  # Enter
            # Split line at cursor
            line = self.input_lines[self.input_cursor_y]
            self.input_lines[self.input_cursor_y] = line[:self.input_cursor_x]
            self.input_lines.insert(self.input_cursor_y + 1, line[self.input_cursor_x:])
            self.input_cursor_y += 1
            self.input_cursor_x = 0
            self.modified = True
            # Adjust scroll
            if self.input_cursor_y >= self.input_scroll + content_height:
                self.input_scroll = self.input_cursor_y - content_height + 1

        elif 32 <= key <= 126:  # Printable ASCII
            line = self.input_lines[self.input_cursor_y]
            self.input_lines[self.input_cursor_y] = line[:self.input_cursor_x] + chr(key) + line[self.input_cursor_x:]
            self.input_cursor_x += 1
            self.modified = True

    def handle_document_key(self, key: int):
        """Handle keypress in document mode."""
        content_height = self.doc_height - 2

        # Ensure document has at least one line
        if not self.document_lines:
            self.document_lines = [""]

        if key == curses.KEY_BACKSPACE or key == 127 or key == 8:
            if self.doc_cursor_x > 0:
                line = self.document_lines[self.doc_cursor_y]
                self.document_lines[self.doc_cursor_y] = line[:self.doc_cursor_x-1] + line[self.doc_cursor_x:]
                self.doc_cursor_x -= 1
                self.modified = True
            elif self.doc_cursor_y > 0:
                # Join with previous line
                prev_len = len(self.document_lines[self.doc_cursor_y - 1])
                self.document_lines[self.doc_cursor_y - 1] += self.document_lines[self.doc_cursor_y]
                del self.document_lines[self.doc_cursor_y]
                self.doc_cursor_y -= 1
                self.doc_cursor_x = prev_len
                self.modified = True

        elif key == curses.KEY_DC:  # Delete key
            line = self.document_lines[self.doc_cursor_y]
            if self.doc_cursor_x < len(line):
                self.document_lines[self.doc_cursor_y] = line[:self.doc_cursor_x] + line[self.doc_cursor_x+1:]
                self.modified = True
            elif self.doc_cursor_y < len(self.document_lines) - 1:
                # Join with next line
                self.document_lines[self.doc_cursor_y] += self.document_lines[self.doc_cursor_y + 1]
                del self.document_lines[self.doc_cursor_y + 1]
                self.modified = True

        elif key == curses.KEY_LEFT:
            if self.doc_cursor_x > 0:
                self.doc_cursor_x -= 1
            elif self.doc_cursor_y > 0:
                self.doc_cursor_y -= 1
                self.doc_cursor_x = len(self.document_lines[self.doc_cursor_y])

        elif key == curses.KEY_RIGHT:
            if self.doc_cursor_x < len(self.document_lines[self.doc_cursor_y]):
                self.doc_cursor_x += 1
            elif self.doc_cursor_y < len(self.document_lines) - 1:
                self.doc_cursor_y += 1
                self.doc_cursor_x = 0

        elif key == curses.KEY_UP:
            if self.doc_cursor_y > 0:
                self.doc_cursor_y -= 1
                self.doc_cursor_x = min(self.doc_cursor_x, len(self.document_lines[self.doc_cursor_y]))

        elif key == curses.KEY_DOWN:
            if self.doc_cursor_y < len(self.document_lines) - 1:
                self.doc_cursor_y += 1
                self.doc_cursor_x = min(self.doc_cursor_x, len(self.document_lines[self.doc_cursor_y]))

        elif key == curses.KEY_PPAGE:  # Page Up
            self.document_scroll = max(0, self.document_scroll - content_height)
            self.doc_cursor_y = max(0, self.doc_cursor_y - content_height)

        elif key == curses.KEY_NPAGE:  # Page Down
            self.document_scroll += content_height
            self.doc_cursor_y = min(len(self.document_lines) - 1, self.doc_cursor_y + content_height)

        elif key == curses.KEY_HOME:
            self.doc_cursor_x = 0

        elif key == curses.KEY_END:
            self.doc_cursor_x = len(self.document_lines[self.doc_cursor_y])

        elif key == 10 or key == 13:  # Enter
            line = self.document_lines[self.doc_cursor_y]
            self.document_lines[self.doc_cursor_y] = line[:self.doc_cursor_x]
            self.document_lines.insert(self.doc_cursor_y + 1, line[self.doc_cursor_x:])
            self.doc_cursor_y += 1
            self.doc_cursor_x = 0
            self.modified = True

        elif 32 <= key <= 126:  # Printable ASCII
            line = self.document_lines[self.doc_cursor_y]
            self.document_lines[self.doc_cursor_y] = line[:self.doc_cursor_x] + chr(key) + line[self.doc_cursor_x:]
            self.doc_cursor_x += 1
            self.modified = True

    def prompt_for_filename(self) -> Optional[str]:
        """Prompt user for a filename."""
        height, width = self.stdscr.getmaxyx()
        prompt = "Filename: "
        default = self.current_file or "document.md"

        # Draw prompt on footer line
        self.stdscr.attron(curses.color_pair(1))
        self.stdscr.addstr(height - 1, 0, " " * (width - 1))
        self.stdscr.addstr(height - 1, 0, prompt)
        self.stdscr.attroff(curses.color_pair(1))
        self.stdscr.refresh()

        # Enable echo and blocking input temporarily
        curses.echo()
        curses.curs_set(1)
        self.stdscr.nodelay(False)

        try:
            filename_bytes = self.stdscr.getstr(height - 1, len(prompt), 255)
            filename = filename_bytes.decode('utf-8').strip()
            if not filename:
                filename = default
            return filename
        except (curses.error, UnicodeDecodeError):
            return default
        finally:
            curses.noecho()
            self.stdscr.nodelay(True)

    def prompt_save_before_quit(self) -> str:
        """Prompt user to save before quitting. Returns 'y', 'n', or 'c'."""
        height, width = self.stdscr.getmaxyx()
        prompt = "Save before quitting? (y/n/c): "

        self.stdscr.attron(curses.color_pair(1))
        self.stdscr.addstr(height - 1, 0, " " * (width - 1))
        self.stdscr.addstr(height - 1, 0, prompt)
        self.stdscr.attroff(curses.color_pair(1))
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

    def save_file(self, filename: Optional[str] = None) -> bool:
        """Save the document to a file."""
        if filename is None:
            filename = self.current_file
        if filename is None:
            filename = self.prompt_for_filename()
        if filename is None:
            return False

        logger.info(f"Saving file: {filename}")
        try:
            # Don't save if document is just empty placeholder
            if self.document_lines == [""]:
                content = ""
            else:
                content = "\n".join(self.document_lines)
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
            self.current_file = filename
            self.modified = False
            self.status_message = f"Saved: {os.path.basename(filename)}"
            logger.info(f"File saved: {filename}")
            return True
        except Exception as e:
            logger.error(f"Failed to save: {e}")
            self.status_message = f"Save error: {e}"
            return False

    def get_context(self) -> tuple[str, str]:
        """Get preceding and subsequent text for context."""
        doc_content = "\n".join(self.document_lines)
        if not doc_content:
            return "", ""
        preceding = doc_content[-CONTEXT_SIZE:] if len(doc_content) > CONTEXT_SIZE else doc_content
        return preceding, ""

    def build_prompt(self, text_to_edit: str) -> str:
        """Build the full prompt with context."""
        preceding, subsequent = self.get_context()
        parts = []
        if preceding:
            parts.append(f"[PRECEDING TEXT]\n{preceding}")
        parts.append(f"[TEXT TO EDIT]\n{text_to_edit}")
        if subsequent:
            parts.append(f"[SUBSEQUENT TEXT]\n{subsequent}")
        return "\n\n".join(parts)

    def send_to_api(self):
        """Send input text to Cerberas for editing."""
        input_content = self.get_input_text().strip()
        if not input_content:
            self.status_message = "Empty input"
            return

        logger.info(f"Sending to Cerberas: {len(input_content)} chars")
        self.processing = True
        self.status_message = "Sending to Cerberas..."

        thread = threading.Thread(target=self._api_call, args=(input_content,), daemon=True)
        thread.start()

    def _api_call(self, input_content: str):
        """Make the API call (runs in separate thread)."""
        try:
            prompt = self.build_prompt(input_content)
            logger.info(f"Starting API call to Cerberas ({self.model})")

            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )

            response_text = response.choices[0].message.content
            logger.info(f"API success: {len(response_text)} chars")
            self.response_queue.put({"type": "response", "data": response_text})

        except Exception as e:
            logger.error(f"API error: {e}")
            self.response_queue.put({"type": "error", "data": str(e)})

    def process_queue(self):
        """Process items from the response queue."""
        try:
            while True:
                item = self.response_queue.get_nowait()
                if item["type"] == "response":
                    # Add response to document
                    if self.document_lines and self.document_lines != [""]:
                        self.document_lines.append("")
                    response_lines = item["data"].split("\n")
                    if self.document_lines == [""]:
                        self.document_lines = response_lines
                    else:
                        self.document_lines.extend(response_lines)
                    # Move cursor to end
                    self.doc_cursor_y = len(self.document_lines) - 1
                    self.doc_cursor_x = len(self.document_lines[self.doc_cursor_y])
                    # Scroll to bottom
                    content_height = self.doc_height - 2
                    self.document_scroll = max(0, len(self.document_lines) - content_height)
                    self.clear_input()
                    self.modified = True
                    self.status_message = "Ready"
                elif item["type"] == "error":
                    self.status_message = f"Error: {item['data'][:50]}"
                self.processing = False
        except Empty:
            pass

    def run(self):
        """Main application loop."""
        logger.info("Starting main loop")

        while self.running:
            # Handle resize
            if curses.is_term_resized(curses.LINES, curses.COLS):
                curses.update_lines_cols()
                self.create_windows()
                self.stdscr.clear()

            # Process API responses
            self.process_queue()

            # Draw UI
            self.refresh_all()

            # Handle input
            try:
                key = self.stdscr.getch()
            except curses.error:
                key = -1

            if key == -1:
                curses.napms(50)  # Sleep 50ms if no input
                continue

            # Global keys
            if key == 5:  # Ctrl+E
                self.focus = "document" if self.focus == "input" else "input"

            elif key == 17:  # Ctrl+Q
                if self.modified:
                    choice = self.prompt_save_before_quit()
                    if choice == 'y':
                        self.save_file()
                        self.running = False
                    elif choice == 'n':
                        self.running = False
                    # else cancel, continue
                else:
                    self.running = False

            elif key == 19:  # Ctrl+S
                self.save_file()

            elif key == 4:  # Ctrl+D - send to API
                if not self.processing:
                    self.send_to_api()

            # Focus-specific keys
            elif self.focus == "input":
                self.handle_input_key(key)
            elif self.focus == "document":
                self.handle_document_key(key)

        logger.info("Application shutdown")


def main(stdscr):
    """Main entry point."""
    app = FictionEditor(stdscr)
    app.run()


if __name__ == "__main__":
    # Suppress deprecation warnings before curses starts
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    logger.info("Starting Fiction Editor")
    try:
        curses.wrapper(main)
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        raise
    finally:
        logger.info("Fiction Editor shutdown")
