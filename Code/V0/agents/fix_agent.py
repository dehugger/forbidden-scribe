"""Fix agent for cleaning up AI output issues."""

from pathlib import Path
from typing import Optional

from agents.base import AgentBase
from wrappers.llm_client import LLMClientBase


DEFAULT_FIX_PROMPT = """# Text Cleanup Agent

You clean up and fix problematic AI-generated text. Your job is to remove artifacts and errors while preserving the core content.

## What to Remove

1. **Thinking/reasoning text** - Remove any "let me think...", "I'll...", meta-commentary
2. **Repeated context** - Remove any preceding or subsequent text that was accidentally included
3. **Formatting artifacts** - Remove stray markers, incomplete tags, malformed markdown
4. **Meta-commentary** - Remove explanations about what was changed or why
5. **Preambles** - Remove "Here's the edited text:" or similar introductions

## What to Preserve

1. The core narrative content
2. Intentional stylistic choices
3. Dialogue and action
4. Scene breaks (---)

## Output

Return only the cleaned text. No explanations, no commentary. If the text is already clean, return it unchanged."""


class FixAgent(AgentBase):
    """Agent for fixing and cleaning up problematic text."""

    operation_name = "fix"

    def __init__(
        self,
        client: LLMClientBase,
        system_prompt_path: Optional[Path] = None,
    ) -> None:
        """Initialize the fix agent.

        Args:
            client: LLM client for API calls.
            system_prompt_path: Path to custom system prompt file.
        """
        super().__init__(client, system_prompt_path)

    @property
    def default_prompt(self) -> str:
        """Default system prompt for fixing."""
        return DEFAULT_FIX_PROMPT

    def build_user_prompt(
        self,
        text: str,
        preceding_context: str = "",
        subsequent_context: str = "",
        additional_instructions: str = "",
    ) -> str:
        """Build the user message for fixing.

        Args:
            text: The text to fix.
            preceding_context: Not used for fix operations.
            subsequent_context: Not used for fix operations.
            additional_instructions: Specific issues to address.

        Returns:
            Formatted prompt for cleanup.
        """
        parts: list[str] = [
            "[TEXT TO FIX]",
            text,
        ]

        if additional_instructions:
            parts.append(f"\n[SPECIFIC ISSUES]\n{additional_instructions}")

        return "\n".join(parts)
