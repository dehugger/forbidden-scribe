"""LLM API client wrapper for OpenAI-compatible endpoints."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import logging
import json

from logging_config import get_logger


@dataclass
class LLMResponse:
    """Standardized response from LLM API call."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    success: bool
    error: Optional[str] = None


class LLMClientBase(ABC):
    """Abstract base class for LLM API clients."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send completion request to the LLM.

        Args:
            prompt: The user prompt/message.
            system_prompt: System instructions for the model.
            max_tokens: Maximum tokens in response (None for unlimited).
            temperature: Sampling temperature (0.0-1.0).

        Returns:
            LLMResponse with the completion result.
        """
        pass


class OpenAICompatibleClient(LLMClientBase):
    """Wrapper for OpenAI-compatible APIs (Cerebras, local models, etc.)."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        logger: Optional[logging.Logger] = None,
        debug: bool = False,
    ) -> None:
        """Initialize the OpenAI-compatible client.

        Args:
            api_key: API key for authentication. Can be empty for local
                servers like LM Studio that don't require auth.
            base_url: Base URL for the API endpoint.
            model: Model name to use for completions.
            logger: Optional logger instance.
            debug: Enable detailed request/response logging.
        """
        # Import here to allow module to load without openai installed
        from openai import OpenAI

        # Use dummy key for servers that don't require auth (like LM Studio)
        # OpenAI client requires non-empty api_key even if server ignores it
        effective_key = api_key if api_key else "lm-studio"

        self.client = OpenAI(base_url=base_url, api_key=effective_key)
        self.model = model
        self.logger = logger or get_logger("llm_client")
        self.debug = debug

    def complete(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send completion request to the API.

        Args:
            prompt: The user prompt/message.
            system_prompt: System instructions for the model.
            max_tokens: Maximum tokens in response (None uses default 4096).
            temperature: Sampling temperature (0.0-1.0).

        Returns:
            LLMResponse with the completion result.
        """
        try:
            self.logger.info(
                f"API call: {len(prompt)} chars prompt, model={self.model}"
            )

            # Build request payload
            request_payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens or 4096,
                "temperature": temperature,
            }

            # Log request payload in debug mode
            if self.debug:
                self.logger.debug("=== LLM Request Payload ===")
                self.logger.debug(
                    json.dumps(request_payload, indent=2, ensure_ascii=False)
                )
                self.logger.debug("=== End Request Payload ===")

            response = self.client.chat.completions.create(**request_payload)

            text = response.choices[0].message.content or ""
            usage = response.usage

            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0

            # Log response payload in debug mode
            if self.debug:
                response_payload = {
                    "id": getattr(response, "id", None),
                    "model": getattr(response, "model", None),
                    "choices": [
                        {
                            "index": choice.index,
                            "message": {
                                "role": choice.message.role,
                                "content": choice.message.content,
                            },
                            "finish_reason": choice.finish_reason,
                        }
                        for choice in response.choices
                    ],
                    "usage": {
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                    },
                }
                self.logger.debug("=== LLM Response Payload ===")
                self.logger.debug(
                    json.dumps(response_payload, indent=2, ensure_ascii=False)
                )
                self.logger.debug("=== End Response Payload ===")

            self.logger.info(
                f"API success: {len(text)} chars, "
                f"{input_tokens} in / {output_tokens} out"
            )

            return LLMResponse(
                text=text,
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                success=True,
            )

        except Exception as e:
            self.logger.error(f"API error: {e}")
            return LLMResponse(
                text="",
                model=self.model,
                input_tokens=0,
                output_tokens=0,
                success=False,
                error=str(e),
            )
