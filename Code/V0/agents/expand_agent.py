"""Expand agent for adding detail and length to text."""

from pathlib import Path
from typing import Optional

from agents.base import AgentBase
from wrappers.llm_client import LLMClientBase


DEFAULT_EXPAND_PROMPT = """# Text Expansion Agent

You expand and enrich prose while maintaining its style and flow.

## Guidelines

1. **Add meaningful detail** - Sensory details, character reactions, setting elements
2. **Maintain voice** - Match the original tone and style exactly
3. **Preserve pacing** - Don't slow down action scenes, let dialogue breathe
4. **Stay focused** - Expand what's there, don't add new plot elements
5. **Natural integration** - Additions should feel seamless, not tacked on

## What to Add

- Sensory details (sight, sound, smell, touch, taste) where sparse
- Character reactions and internal responses
- Setting details that ground the scene
- Action beats in dialogue
- Transitional moments between major beats
- Atmosphere and mood

## What NOT to Add

- New plot points or information
- Characters not already present
- Dramatic changes in tone
- Over-explanation of existing content
- Purple prose or excessive description

## Style Notes

- Match sentence structure and rhythm of original
- Use similar vocabulary and diction
- Maintain the original's level of formality
- Keep dialogue natural and snappy
- Preserve any dark humor or sardonic tone

## Output

Return only the expanded text. Aim to increase length by 30-50% while maintaining quality. No explanations or meta-commentary."""


class ExpandAgent(AgentBase):
    """Agent for expanding and enriching prose."""

    operation_name = "expand"

    def __init__(
        self,
        client: LLMClientBase,
        system_prompt_path: Optional[Path] = None,
    ) -> None:
        """Initialize the expand agent.

        Args:
            client: LLM client for API calls.
            system_prompt_path: Path to custom system prompt file.
        """
        super().__init__(client, system_prompt_path)

    @property
    def default_prompt(self) -> str:
        """Default system prompt for expanding."""
        return DEFAULT_EXPAND_PROMPT

    def build_user_prompt(
        self,
        text: str,
        preceding_context: str = "",
        subsequent_context: str = "",
        additional_instructions: str = "",
    ) -> str:
        """Build the user message for expanding.

        Args:
            text: The text to expand.
            preceding_context: For continuity and style matching.
            subsequent_context: For continuity.
            additional_instructions: Specific expansion goals.

        Returns:
            Formatted prompt for expansion.
        """
        parts: list[str] = []

        if preceding_context:
            parts.append(f"[PRECEDING TEXT]\n{preceding_context}")

        parts.append(f"[TEXT TO EXPAND]\n{text}")

        if subsequent_context:
            parts.append(f"[SUBSEQUENT TEXT]\n{subsequent_context}")

        if additional_instructions:
            parts.append(f"[EXPANSION GOALS]\n{additional_instructions}")
        else:
            parts.append(
                "[EXPANSION GOALS]\nAdd sensory details, character reactions, "
                "and atmosphere while preserving the original style and pacing."
            )

        return "\n\n".join(parts)
