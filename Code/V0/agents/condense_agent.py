"""Condense agent for shortening text while preserving meaning."""

from pathlib import Path
from typing import Optional

from agents.base import AgentBase
from wrappers.llm_client import LLMClientBase


DEFAULT_CONDENSE_PROMPT = """# Text Condensation Agent

You condense and tighten prose while preserving its essential meaning and style.

## Guidelines

1. **Cut ruthlessly** - Remove redundant phrases, unnecessary modifiers, filler words
2. **Preserve voice** - Maintain the original tone, style, and character voice
3. **Keep key details** - Don't lose important plot points or character beats
4. **Improve pacing** - Tighter prose reads faster
5. **Maintain flow** - Condensed text should still read naturally

## What to Cut

- Redundant descriptions ("She nodded her head" → "She nodded")
- Filler phrases ("It was as if", "seemed to", "began to")
- Over-explanation of emotions or motivations
- Unnecessary dialogue tags when speaker is clear
- Repetitive beats that hammer the same point

## What to Preserve

- Essential plot information
- Character voice and personality
- Key emotional moments (but tighter)
- Dialogue content (though it can be trimmed)
- Atmosphere and setting (in fewer words)

## Output

Return only the condensed text. Aim to reduce length by 20-40% while keeping all essential content. No explanations or meta-commentary."""


class CondenseAgent(AgentBase):
    """Agent for condensing and tightening prose."""

    operation_name = "condense"

    def __init__(
        self,
        client: LLMClientBase,
        system_prompt_path: Optional[Path] = None,
    ) -> None:
        """Initialize the condense agent.

        Args:
            client: LLM client for API calls.
            system_prompt_path: Path to custom system prompt file.
        """
        super().__init__(client, system_prompt_path)

    @property
    def default_prompt(self) -> str:
        """Default system prompt for condensing."""
        return DEFAULT_CONDENSE_PROMPT

    def build_user_prompt(
        self,
        text: str,
        preceding_context: str = "",
        subsequent_context: str = "",
        additional_instructions: str = "",
    ) -> str:
        """Build the user message for condensing.

        Args:
            text: The text to condense.
            preceding_context: For style reference only.
            subsequent_context: Not typically used.
            additional_instructions: Specific condensation goals.

        Returns:
            Formatted prompt for condensation.
        """
        parts: list[str] = []

        if preceding_context:
            parts.append(
                f"[PRECEDING TEXT FOR STYLE REFERENCE]\n{preceding_context}"
            )

        parts.append(f"[TEXT TO CONDENSE]\n{text}")

        if additional_instructions:
            parts.append(f"[CONDENSATION GOALS]\n{additional_instructions}")

        return "\n\n".join(parts)
