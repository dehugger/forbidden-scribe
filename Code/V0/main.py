#!/usr/bin/env python3
"""Forbidden Scribe - Terminal-based fiction drafting tool.

A passage-based fiction editor that uses AI to refine rough drafts
into polished prose. Features a two-panel TUI with passage navigation,
menu-based operations, and structured document storage.

Usage:
    python main.py [document.json] [--debug]

Configuration:
    API key can be set via:
    - FS_API_KEY environment variable, or
    - secrets.json with "api_key" field
    Note: Empty string is valid for APIs without authentication.

    Optional environment variables (override config.json):
    - FS_API_URL: API endpoint URL (default: https://api.cerebras.ai/v1)
    - FS_MODEL: Model name (default: llama3.1-8b)
"""

import argparse
import curses
import sys
import warnings
from pathlib import Path

from logging_config import setup_logging, get_logger
from editor import ForbiddenScribeEditor
from models.document import Document


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Forbidden Scribe - AI-powered fiction drafting tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "document",
        nargs="?",
        type=Path,
        help="Document file to open (JSON format)",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path(__file__).parent,
        help="Directory containing config.json and secrets.json",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show debug panel with scrolling log output",
    )
    return parser.parse_args()


def main(stdscr: "curses.window", args: argparse.Namespace) -> None:
    """Main application entry point.

    Args:
        stdscr: Main curses screen.
        args: Command line arguments.
    """
    logger = get_logger("main")

    try:
        editor = ForbiddenScribeEditor(
            stdscr, args.config_dir, debug=args.debug
        )

        # Load document if specified
        if args.document:
            try:
                editor.state.document = Document.load(args.document)
                editor.passage_panel.update_passages(
                    editor.state.document.passages
                )
                logger.info(f"Loaded document: {args.document}")
            except FileNotFoundError:
                logger.warning(f"Document not found: {args.document}")
            except Exception as e:
                logger.error(f"Failed to load document: {e}")

        editor.run()

    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        raise


def run() -> None:
    """Entry point wrapper."""
    args = parse_args()

    # Set up logging
    config_dir = args.config_dir
    log_path = config_dir / "logs" / "forbidden_scribe.log"
    setup_logging(str(log_path))

    logger = get_logger("main")
    logger.info("Starting Forbidden Scribe")

    # Suppress deprecation warnings from curses
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    try:
        curses.wrapper(lambda stdscr: main(stdscr, args))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        raise
    finally:
        logger.info("Forbidden Scribe shutdown")


if __name__ == "__main__":
    run()
