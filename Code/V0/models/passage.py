"""Passage model for storing user input and AI response pairs."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid


@dataclass
class PassageAuditEntry:
    """Single audit log entry for passage changes."""

    timestamp: str
    operation: str  # "create", "edit", "reroll", "fix", "condense", "expand"
    model: Optional[str]
    previous_text: Optional[str]
    new_text: str

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "timestamp": self.timestamp,
            "operation": self.operation,
            "model": self.model,
            "previous_text": self.previous_text,
            "new_text": self.new_text,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PassageAuditEntry":
        """Deserialize from dictionary."""
        return cls(
            timestamp=data.get("timestamp", ""),
            operation=data.get("operation", ""),
            model=data.get("model"),
            previous_text=data.get("previous_text"),
            new_text=data.get("new_text", ""),
        )


def _generate_id() -> str:
    """Generate a short unique ID."""
    return str(uuid.uuid4())[:8]


def _now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Passage:
    """Immutable user/AI pairing with editable text overlay.

    The user_entry and ai_response fields are immutable records of the
    original submission. The text field is the current editable version
    that can be modified by the user or AI agents.
    """

    id: str = field(default_factory=_generate_id)
    rank: int = 0
    user_entry: str = ""  # Original user input (immutable)
    ai_response: str = ""  # Original AI response (immutable)
    text: str = ""  # Current editable text
    model: str = ""  # Model that generated ai_response
    created_at: str = field(default_factory=_now_iso)
    manual_edited: bool = False
    pending: bool = False  # Waiting for AI response
    audit_log: list[PassageAuditEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize text to ai_response or user_entry if not set."""
        if not self.text:
            if self.ai_response:
                self.text = self.ai_response
            elif self.user_entry:
                self.text = self.user_entry

    def update_text(
        self,
        new_text: str,
        operation: str,
        model: Optional[str] = None
    ) -> None:
        """Update text with audit logging.

        Args:
            new_text: The new text content.
            operation: Type of operation (edit, reroll, fix, condense, expand).
            model: Model used for AI operations, None for manual edits.
        """
        entry = PassageAuditEntry(
            timestamp=_now_iso(),
            operation=operation,
            model=model,
            previous_text=self.text,
            new_text=new_text,
        )
        self.audit_log.append(entry)
        self.text = new_text
        if operation == "manual_edit":
            self.manual_edited = True

    def revert_to_original(self) -> None:
        """Revert text to original AI response."""
        if self.text != self.ai_response:
            self.update_text(self.ai_response, "revert", None)

    def to_dict(self) -> dict:
        """Serialize for JSON storage."""
        return {
            "id": self.id,
            "rank": self.rank,
            "user_entry": self.user_entry,
            "ai_response": self.ai_response,
            "text": self.text,
            "model": self.model,
            "created_at": self.created_at,
            "manual_edited": self.manual_edited,
            "pending": self.pending,
            "audit_log": [e.to_dict() for e in self.audit_log],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Passage":
        """Deserialize from JSON."""
        audit_entries = [
            PassageAuditEntry.from_dict(e)
            for e in data.get("audit_log", [])
        ]
        return cls(
            id=data.get("id", _generate_id()),
            rank=data.get("rank", 0),
            user_entry=data.get("user_entry", ""),
            ai_response=data.get("ai_response", ""),
            text=data.get("text", data.get("ai_response", "")),
            model=data.get("model", ""),
            created_at=data.get("created_at", _now_iso()),
            manual_edited=data.get("manual_edited", False),
            pending=data.get("pending", False),
            audit_log=audit_entries,
        )

    @classmethod
    def create(
        cls,
        user_entry: str,
        ai_response: str,
        model: str,
        rank: int = 0
    ) -> "Passage":
        """Factory method to create a new passage.

        Args:
            user_entry: Original user input text.
            ai_response: AI-generated response text.
            model: Name of the model that generated the response.
            rank: Display order (default 0).

        Returns:
            New Passage instance with audit log entry for creation.
        """
        passage = cls(
            rank=rank,
            user_entry=user_entry,
            ai_response=ai_response,
            text=ai_response,
            model=model,
        )
        # Log creation
        passage.audit_log.append(
            PassageAuditEntry(
                timestamp=passage.created_at,
                operation="create",
                model=model,
                previous_text=None,
                new_text=ai_response,
            )
        )
        return passage

    @classmethod
    def create_pending(
        cls,
        user_entry: str,
        rank: int = 0
    ) -> "Passage":
        """Factory method to create a pending passage.

        Creates a passage that shows user input while waiting for AI response.

        Args:
            user_entry: Original user input text.
            rank: Display order (default 0).

        Returns:
            New Passage instance marked as pending.
        """
        passage = cls(
            rank=rank,
            user_entry=user_entry,
            ai_response="",
            text=user_entry,
            model="",
            pending=True,
        )
        return passage
