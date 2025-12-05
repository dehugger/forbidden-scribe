"""Document model for managing passage collections."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json

from models.passage import Passage
from models.config import APIConfig, DocumentMeta


@dataclass
class Document:
    """Complete document with config, metadata, and passages.

    Documents are stored as JSON files containing:
    - config: API settings for this document
    - meta: Document metadata (name, setting, prompt selection)
    - content.passages: Array of Passage objects
    """

    file_path: Optional[Path] = None
    config: APIConfig = field(default_factory=APIConfig)
    meta: DocumentMeta = field(default_factory=DocumentMeta)
    passages: list[Passage] = field(default_factory=list)
    modified: bool = False

    def add_passage(
        self,
        user_entry: str,
        ai_response: str,
        model: str
    ) -> Passage:
        """Create and append a new passage.

        Args:
            user_entry: Original user input text.
            ai_response: AI-generated response text.
            model: Name of the model that generated the response.

        Returns:
            The newly created Passage.
        """
        passage = Passage.create(
            user_entry=user_entry,
            ai_response=ai_response,
            model=model,
            rank=len(self.passages),
        )
        self.passages.append(passage)
        self.modified = True
        return passage

    def add_pending_passage(self, user_entry: str) -> Passage:
        """Create and append a pending passage.

        Args:
            user_entry: Original user input text.

        Returns:
            The newly created pending Passage.
        """
        passage = Passage.create_pending(
            user_entry=user_entry,
            rank=len(self.passages),
        )
        self.passages.append(passage)
        self.modified = True
        return passage

    def get_passage(self, index: int) -> Optional[Passage]:
        """Get passage by index with bounds checking.

        Args:
            index: Zero-based index of the passage.

        Returns:
            Passage at index, or None if out of bounds.
        """
        if 0 <= index < len(self.passages):
            return self.passages[index]
        return None

    def get_passage_by_id(self, passage_id: str) -> Optional[Passage]:
        """Get passage by unique ID.

        Args:
            passage_id: Unique identifier of the passage.

        Returns:
            Passage with matching ID, or None if not found.
        """
        for passage in self.passages:
            if passage.id == passage_id:
                return passage
        return None

    def delete_passage(self, index: int) -> bool:
        """Delete passage at index.

        Args:
            index: Zero-based index of the passage to delete.

        Returns:
            True if deletion succeeded, False if index out of bounds.
        """
        if 0 <= index < len(self.passages):
            del self.passages[index]
            self.rerank_passages()
            self.modified = True
            return True
        return False

    def move_passage(self, from_index: int, to_index: int) -> bool:
        """Move passage from one position to another.

        Args:
            from_index: Current index of the passage.
            to_index: Target index for the passage.

        Returns:
            True if move succeeded, False if indices out of bounds.
        """
        if not (0 <= from_index < len(self.passages)):
            return False
        if not (0 <= to_index < len(self.passages)):
            return False
        if from_index == to_index:
            return True

        passage = self.passages.pop(from_index)
        self.passages.insert(to_index, passage)
        self.rerank_passages()
        self.modified = True
        return True

    def rerank_passages(self) -> None:
        """Reassign rank values after reordering."""
        for i, passage in enumerate(self.passages):
            passage.rank = i

    def get_context_text(
        self,
        passage_index: int,
        max_chars: int = 2000
    ) -> str:
        """Get preceding passage text for context.

        Args:
            passage_index: Index of the current passage.
            max_chars: Maximum characters to include (default 2000).

        Returns:
            Combined text of preceding passages up to max_chars.
        """
        if passage_index <= 0:
            return ""

        preceding: list[str] = []
        char_count = 0

        for i in range(passage_index - 1, -1, -1):
            text = self.passages[i].text
            if char_count + len(text) > max_chars:
                break
            preceding.insert(0, text)
            char_count += len(text)

        return "\n\n".join(preceding)

    def get_subsequent_text(
        self,
        passage_index: int,
        max_chars: int = 2000
    ) -> str:
        """Get subsequent passage text for context.

        Args:
            passage_index: Index of the current passage.
            max_chars: Maximum characters to include (default 2000).

        Returns:
            Combined text of subsequent passages up to max_chars.
        """
        if passage_index >= len(self.passages) - 1:
            return ""

        subsequent: list[str] = []
        char_count = 0

        for i in range(passage_index + 1, len(self.passages)):
            text = self.passages[i].text
            if char_count + len(text) > max_chars:
                break
            subsequent.append(text)
            char_count += len(text)

        return "\n\n".join(subsequent)

    def get_full_text(self) -> str:
        """Get combined text of all passages.

        Returns:
            All passage texts joined with double newlines.
        """
        return "\n\n".join(p.text for p in self.passages)

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "config": self.config.to_dict(),
            "meta": self.meta.to_dict(),
            "content": {
                "passages": [p.to_dict() for p in self.passages],
            },
        }

    def save(self, path: Optional[Path] = None) -> tuple[bool, str]:
        """Save document to JSON file.

        Args:
            path: File path to save to. Uses file_path if not specified.

        Returns:
            Tuple of (success, message).
        """
        save_path = path or self.file_path
        if not save_path:
            return False, "No file path specified"

        try:
            # Ensure parent directory exists
            save_path = Path(save_path)  # Ensure it's a Path object
            save_path.parent.mkdir(parents=True, exist_ok=True)

            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
            self.file_path = save_path
            self.modified = False
            return True, f"Saved: {save_path.name}"
        except PermissionError:
            return False, f"Permission denied: {save_path}"
        except OSError as e:
            return False, f"Save error: {e}"
        except Exception as e:
            return False, f"Unexpected error: {e}"

    @classmethod
    def load(cls, path: Path) -> "Document":
        """Load document from JSON file.

        Args:
            path: Path to the JSON document file.

        Returns:
            Document instance populated from file.

        Raises:
            FileNotFoundError: If file does not exist.
            json.JSONDecodeError: If file is not valid JSON.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        doc = cls(
            file_path=path,
            config=APIConfig.from_dict(data.get("config", {})),
            meta=DocumentMeta.from_dict(data.get("meta", {})),
        )

        for p_data in data.get("content", {}).get("passages", []):
            doc.passages.append(Passage.from_dict(p_data))

        return doc

    @classmethod
    def new(cls, name: str = "Untitled") -> "Document":
        """Create a new empty document.

        Args:
            name: Document name (default "Untitled").

        Returns:
            New empty Document instance.
        """
        doc = cls()
        doc.meta.document_name = name
        return doc
