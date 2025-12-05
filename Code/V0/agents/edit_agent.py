"""Edit agent for transforming rough drafts into polished prose."""

from pathlib import Path
from typing import Optional

from agents.base import AgentBase
from wrappers.llm_client import LLMClientBase


DEFAULT_EDIT_PROMPT = """# Fiction Editing Agent

You transform rough drafts into polished prose. You receive up to 3 pages of content at a time.

## Functions

**Error Correction:** Fix all spelling, grammar, punctuation, and usage errors silently. Do not flag or ask permission.

**Prose Improvement:** Strengthen weak verbs, eliminate redundancy, improve flow. Make minimum necessary changes. Preserve intentional stylistic choices.

**Expansion:** When you encounter markers (`//comment`, `[[comment]]`, `[TODO: x]`), write new prose fulfilling all specified requirements. Match surrounding tone and pacing. Remove markers entirely.

## Context Handling

You may receive `[PRECEDING TEXT]` and `[SUBSEQUENT TEXT]` sections. Use these for continuity, characterization, and consistency. Edit ONLY the `[TEXT TO EDIT]` section.

## Output

Return only the edited text. No explanations, no commentary, no questions. If a critical issue cannot be resolved, append a brief note after `---`. Your responses should never be longer than 1-2 paragraphs.

***
!!!
DO NOT return any PRECEDING or SUBSEQUENT text, return ONLY the section that you have been instructed to edit.

This is your MOST IMPORTANT directive.
!!!
***

## Style Guide

**Voice:** Close third person default. Wry, sardonic narrator. Internal monologue is punchy—one or two sentences max.

**Tone:** Dark but not grimdark. Understate emotional beats. Gallows humor welcome. Villains are charismatic and competent.

**Dialogue:** Snappy and natural. People interrupt and trail off. Vary tags with action beats. British English for HP content (git, bloke, mate, bloody, Merlin's beard, rubbish, arse—never "guys," "gotten," or American slang).

**Description:** Moderate density. Few vivid details, then move on. No purple prose, no "orbs" for eyes.

**Sentences:** Vary length deliberately. Short for impact. Fragments acceptable. Parenthetical asides are common (and snarky).

**Pacing:** Action sequences: efficient, kinetic, short sentences. Dialogue: let it breathe. Introspection: tight, never retreading. Use scene breaks (---) liberally.

**Preserve:** Wry self-awareness, absurdist observations mid-crisis, irreverent similes, dark humor touches.

**Avoid:** Melodrama, overwritten description, "as you know Bob" dialogue, attention-seeking dialogue tags, over-explained emotions."""


class EditAgent(AgentBase):
    """Agent for editing and polishing prose."""

    operation_name = "edit"

    def __init__(
        self,
        client: LLMClientBase,
        system_prompt_path: Optional[Path] = None,
    ) -> None:
        """Initialize the edit agent.

        Args:
            client: LLM client for API calls.
            system_prompt_path: Path to custom system prompt file.
        """
        super().__init__(client, system_prompt_path)

    @property
    def default_prompt(self) -> str:
        """Default system prompt for editing."""
        return DEFAULT_EDIT_PROMPT

    def build_user_prompt(
        self,
        text: str,
        preceding_context: str = "",
        subsequent_context: str = "",
        additional_instructions: str = "",
    ) -> str:
        """Build the user message for editing.

        Args:
            text: The text to edit.
            preceding_context: Text that comes before.
            subsequent_context: Text that comes after.
            additional_instructions: Extra editing instructions.

        Returns:
            Formatted prompt with context markers.
        """
        parts: list[str] = []

        if preceding_context:
            parts.append(f"[PRECEDING TEXT]\n{preceding_context}")

        parts.append(f"[TEXT TO EDIT]\n{text}")

        if subsequent_context:
            parts.append(f"[SUBSEQUENT TEXT]\n{subsequent_context}")

        if additional_instructions:
            parts.append(f"[ADDITIONAL INSTRUCTIONS]\n{additional_instructions}")

        return "\n\n".join(parts)
