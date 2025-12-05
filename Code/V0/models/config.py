"""Configuration models for Forbidden Scribe."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json
import os


# Environment variable names for fallback configuration
ENV_API_KEY = "FS_API_KEY"
ENV_API_URL = "FS_API_URL"
ENV_MODEL = "FS_MODEL"


@dataclass
class APIConfig:
    """API connection and model settings."""

    api_url: str = "https://api.cerebras.ai/v1"
    api_spec: str = "openai"
    model_name: str = "llama3.1-8b"
    temperature: float = 0.7
    max_input_tokens: int = 4096
    max_output_tokens: Optional[int] = None
    structured_output_schema: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "api_url": self.api_url,
            "api_spec": self.api_spec,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "structured_output_schema": self.structured_output_schema,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "APIConfig":
        """Deserialize from dictionary.

        Environment variables take precedence over config.json when set:
        - FS_API_URL overrides api_url
        - FS_MODEL overrides model_name
        """
        # Environment variables take precedence over config file
        api_url = os.environ.get(ENV_API_URL) or data.get("api_url")
        model_name = os.environ.get(ENV_MODEL) or data.get("model_name")

        return cls(
            api_url=api_url or "https://api.cerebras.ai/v1",
            api_spec=data.get("api_spec", "openai"),
            model_name=model_name or "llama3.1-8b",
            temperature=data.get("temperature", 0.7),
            max_input_tokens=data.get("max_input_tokens", 4096),
            max_output_tokens=data.get("max_output_tokens"),
            structured_output_schema=data.get("structured_output_schema"),
        )


@dataclass
class DocumentMeta:
    """Document metadata and generation settings."""

    document_name: str = "Untitled"
    setting: str = "original"  # e.g., "Harry Potter", "Worm", "original"
    system_prompt: Optional[str] = None  # Path to prompt file or None
    send_prepend_passage: bool = False
    send_append_text: bool = False

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "document_name": self.document_name,
            "setting": self.setting,
            "system_prompt": self.system_prompt,
            "send_prepend_passage": self.send_prepend_passage,
            "send_append_text": self.send_append_text,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentMeta":
        """Deserialize from dictionary."""
        return cls(
            document_name=data.get("document_name", "Untitled"),
            setting=data.get("setting", "original"),
            system_prompt=data.get("system_prompt"),
            send_prepend_passage=data.get("send_prepend_passage", True),
            send_append_text=data.get("send_append_text", False),
        )


@dataclass
class AppConfig:
    """Application-level configuration."""

    api: APIConfig = field(default_factory=APIConfig)
    default_prompt_path: str = "prompts/default_prompt.txt"
    log_path: str = "logs/forbidden_scribe.log"
    context_chars: int = 2000
    works_directory: str = "works"

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "api": self.api.to_dict(),
            "default_prompt_path": self.default_prompt_path,
            "log_path": self.log_path,
            "context_chars": self.context_chars,
            "works_directory": self.works_directory,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        """Deserialize from dictionary."""
        return cls(
            api=APIConfig.from_dict(data.get("api", {})),
            default_prompt_path=data.get(
                "default_prompt_path", "prompts/default_prompt.txt"
            ),
            log_path=data.get("log_path", "logs/forbidden_scribe.log"),
            context_chars=data.get("context_chars", 2000),
            works_directory=data.get("works_directory", "works"),
        )

    @classmethod
    def load(cls, config_path: Path) -> "AppConfig":
        """Load configuration from config.json.

        Args:
            config_path: Path to config.json file.

        Returns:
            AppConfig instance, using defaults for missing values.
        """
        config = cls()
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                config = cls.from_dict(data)
            except (json.JSONDecodeError, OSError):
                pass  # Use defaults on error
        return config

    def save(self, config_path: Path) -> bool:
        """Save configuration to file.

        Args:
            config_path: Path to save config.json.

        Returns:
            True if save succeeded.
        """
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
            return True
        except (OSError, IOError):
            return False


@dataclass
class Secrets:
    """Sensitive configuration stored separately."""

    api_key: str = ""

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "api_key": self.api_key,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Secrets":
        """Deserialize from dictionary."""
        return cls(
            api_key=data.get("api_key", ""),
        )

    @classmethod
    def load(cls, secrets_path: Path) -> "Secrets":
        """Load secrets from secrets.json.

        FS_API_KEY environment variable takes precedence over config file.

        Args:
            secrets_path: Path to secrets.json file.

        Returns:
            Secrets instance, empty if file doesn't exist and no env var.
        """
        secrets = cls()
        if secrets_path.exists():
            try:
                with open(secrets_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                secrets = cls.from_dict(data)
            except (json.JSONDecodeError, OSError):
                pass

        # Environment variable takes precedence over config file
        env_key = os.environ.get(ENV_API_KEY)
        if env_key is not None:
            secrets.api_key = env_key

        return secrets

    def save(self, secrets_path: Path) -> bool:
        """Save secrets to file.

        Args:
            secrets_path: Path to save secrets.json.

        Returns:
            True if save succeeded.
        """
        try:
            with open(secrets_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
            return True
        except (OSError, IOError):
            return False

    def is_configured(self) -> bool:
        """Check if secrets file was loaded or environment variable was set.

        Note: An empty string API key is valid for APIs that don't require
        authentication (e.g., local network APIs).

        Returns:
            True always - empty string is a valid API key value.
        """
        return True
