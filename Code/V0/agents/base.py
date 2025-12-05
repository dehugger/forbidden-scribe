"""Base agent class for text operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from wrappers.llm_client import LLMClientBase, LLMResponse


@dataclass
class AgentResult:
    """Result from agent operation."""

    success: bool
    text: str
    model: str
    operation: str
    error: Optional[str] = None


class AgentBase(ABC):
    """Base class for all editing agents.

    Agents handle specific text operations like editing, fixing,
    condensing, or expanding passages. Each agent has its own
    system prompt and prompt-building logic.
    """

    # Operation name for audit logging
    operation_name: str = "agent"

    def __init__(
        self,
        client: LLMClientBase,
        system_prompt_path: Optional[Path] = None,
    ) -> None:
        """Initialize the agent.

        Args:
            client: LLM client for API calls.
            system_prompt_path: Path to custom system prompt file.
        """
        self.client = client
        self._custom_prompt: Optional[str] = None

        if system_prompt_path and system_prompt_path.exists():
            self._custom_prompt = system_prompt_path.read_text(encoding="utf-8")

    @property
    @abstractmethod
    def default_prompt(self) -> str:
        """Default system prompt if none provided."""
        pass

    @property
    def system_prompt(self) -> str:
        """Get the system prompt to use."""
        return self._custom_prompt or self.default_prompt

    @abstractmethod
    def build_user_prompt(
        self,
        text: str,
        preceding_context: str = "",
        subsequent_context: str = "",
        additional_instructions: str = "",
    ) -> str:
        """Build the user message for this agent type.

        Args:
            text: The text to operate on.
            preceding_context: Text that comes before (for continuity).
            subsequent_context: Text that comes after (for continuity).
            additional_instructions: Extra user instructions.

        Returns:
            Formatted user prompt string.
        """
        pass

    def execute(
        self,
        text: str,
        preceding_context: str = "",
        subsequent_context: str = "",
        additional_instructions: str = "",
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> AgentResult:
        """Execute the agent on the given text.

        Args:
            text: The text to operate on.
            preceding_context: Text that comes before.
            subsequent_context: Text that comes after.
            additional_instructions: Extra user instructions.
            max_tokens: Maximum response tokens (None for default).
            temperature: Sampling temperature.

        Returns:
            AgentResult with the operation outcome.
        """
        prompt = self.build_user_prompt(
            text=text,
            preceding_context=preceding_context,
            subsequent_context=subsequent_context,
            additional_instructions=additional_instructions,
        )

        response: LLMResponse = self.client.complete(
            prompt=prompt,
            system_prompt=self.system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        return AgentResult(
            success=response.success,
            text=response.text,
            model=response.model,
            operation=self.operation_name,
            error=response.error,
        )
