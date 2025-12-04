# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Forbidden Scribe** is a terminal-based fiction drafting tool that uses AI to refine raw user input into polished prose. The application uses a vertical split TUI: rough user input at the bottom, generated "passages" (user input + AI response pairs) displayed as a scrolling list above.

## Current State

The codebase contains a working prototype (`fs_prototype.py`) that implements a basic two-panel editor with Cerebras AI integration. This is NOT the full vision described in the design documents - it's an early working prototype focused on basic editing flow.

**What exists:**
- Two-panel ncurses editor (document panel + input panel)
- Basic text editing with cursor movement
- Cerebras API integration for AI editing
- Context-aware prompting (sends preceding text for continuity)
- JSON structured logging with rotation

**What's planned but not implemented:**
- JSON document format with passage storage (see `templates/fs_doc_format.json`)
- Passage-level operations (reroll, expand, condense, fix)
- Menu navigation system (LEFT/RIGHT for options, ENTER for edit)
- Visual passage separators and colored indicators
- Audit logging and passage history
- Configurable system prompts and keybindings
- Structured JSON schema output from AI

## Architecture

### Core Components

**fs_prototype.py**: Complete ncurses-based editor application
- `FictionEditor` class manages all UI state and API interaction
- Two-panel layout: 75% document (top) + 25% input (bottom)
- Focus switches between panels with Ctrl+E
- API calls run in background threads with queue-based response handling
- Spinner animation during API processing

### Document Format (Planned)

JSON structure in `templates/fs_doc_format.json`:
- `config`: API settings, model parameters, token limits
- `meta`: Document metadata, system prompt selection, context settings
- `content.passages[]`: Array of passage objects with:
  - `id`: Unique identifier
  - `rank`: Display order
  - `user_entry`: Original user input (immutable)
  - `ai_response`: AI-generated text (immutable)
  - `text`: Current editable text
  - `model`: Model that generated the passage

### AI Integration

**Current (Prototype):**
- Uses Cerebras API via OpenAI-compatible client
- Environment variables: `CERBERAS_API_KEY`, `CERBERAS_MODEL`
- Context window: Last 2000 chars of document as preceding text
- System prompt embedded in `fs_prototype.py` (SYSTEM_PROMPT constant)

**Planned:**
- Configurable API endpoints/specs (OpenAI, local models)
- Structured JSON response schemas
- Multiple agent modes (reroll, fix, condense, expand, custom instructions)
- Unbounded token generation option

### UI/UX Flow (Planned Vision)

The planned interface allows users to:
1. Type raw draft text in input panel
2. Submit to AI for refinement (becomes a "passage" in document)
3. Navigate through passages with arrow keys
4. Press LEFT/RIGHT on a passage to access menu options
5. Press ENTER on a passage to edit it directly
6. See visual separators and colored indicators between passages

## Configuration

**Current:** Environment variables only
**Planned:** `config.json` with API settings, model parameters, keybindings

**System Prompt Philosophy:**
- Transforms rough drafts into polished prose
- Silent error correction (no flagging)
- Expands TODO markers and inline comments into prose
- Style: wry sardonic narrator, dark but not grimdark, British English for HP content
- Output only edited text, no meta-commentary

## Development Commands

**Run the prototype:**
```bash
export CERBERAS_API_KEY="your-key"
export CERBERAS_MODEL="llama3.1-8b"  # optional, defaults to this
python3 fs_prototype.py
```

**Key bindings (current prototype):**
- Ctrl+E: Switch focus between document and input panels
- Ctrl+D: Send input to AI for editing
- Ctrl+S: Save document to file
- Ctrl+Q: Quit (prompts to save if modified)
- Arrow keys, Home/End, Page Up/Down: Navigation
- Standard text editing in focused panel

**Logs:**
- Location: `logs/fiction_editor.log`
- Format: JSON structured logging with rotation (10MB max, 5 backups)

## Next Steps for Development

The prototype provides basic editing functionality but lacks the core passage-based architecture. To align with the vision in `concept.md`:

1. Implement JSON document format with passage storage
2. Build passage navigation UI with visual separators
3. Add menu system for passage operations (LEFT/RIGHT navigation)
4. Implement multiple AI agent modes (reroll, fix, condense, expand)
5. Add configuration file support for settings and keybindings
6. Implement passage audit history
