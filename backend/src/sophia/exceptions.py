"""Sophia exception hierarchy.

All exceptions inherit from SophiaError and carry a three-part structure:
message (what happened), detail (technical context), suggestion (what to do next).
"""


class SophiaError(Exception):
    """Base exception for all Sophia errors."""

    def __init__(
        self,
        message: str,
        detail: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        self.message = message
        self.detail = detail
        self.suggestion = suggestion
        super().__init__(message)

    def __str__(self) -> str:
        parts = [self.message]
        if self.detail:
            parts.append(f"Detail: {self.detail}")
        if self.suggestion:
            parts.append(f"Suggestion: {self.suggestion}")
        return " | ".join(parts)


class DatabaseError(SophiaError):
    """Error related to database operations."""

    def __init__(
        self,
        message: str = "A database error occurred",
        detail: str | None = None,
        suggestion: str | None = "Check database connectivity and encryption key",
    ) -> None:
        super().__init__(message, detail, suggestion)


class ClientNotFoundError(SophiaError):
    """Raised when a client cannot be found."""

    def __init__(
        self,
        message: str = "Client not found",
        detail: str | None = None,
        suggestion: str | None = "Check client name spelling or use roster view",
    ) -> None:
        super().__init__(message, detail, suggestion)


class DuplicateClientError(SophiaError):
    """Raised when attempting to create a client that already exists."""

    def __init__(
        self,
        message: str = "A client with this name already exists",
        detail: str | None = None,
        suggestion: str | None = "Use a different name or update the existing client",
    ) -> None:
        super().__init__(message, detail, suggestion)


class VoiceExtractionError(SophiaError):
    """Raised when voice profile extraction fails."""

    def __init__(
        self,
        message: str = "Voice extraction failed",
        detail: str | None = None,
        suggestion: str | None = "Provide more source materials or check content quality",
    ) -> None:
        super().__init__(message, detail, suggestion)


class ValidationError(SophiaError):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str = "Validation error",
        detail: str | None = None,
        suggestion: str | None = "Check input format and required fields",
    ) -> None:
        super().__init__(message, detail, suggestion)


class BackupError(SophiaError):
    """Raised when backup operations fail."""

    def __init__(
        self,
        message: str = "Backup operation failed",
        detail: str | None = None,
        suggestion: str | None = "Check backup directory permissions and disk space",
    ) -> None:
        super().__init__(message, detail, suggestion)


class ContentGenerationError(SophiaError):
    """Raised when content generation fails.

    Typically from three-input validation (missing research, intelligence,
    or voice profile) or other generation pipeline failures.
    """

    def __init__(
        self,
        message: str = "Content generation failed",
        detail: str | None = None,
        reason: str | None = None,
        suggestion: str | None = "Ensure research, intelligence profile, and voice profile exist for the client",
    ) -> None:
        self.reason = reason
        super().__init__(message, detail, suggestion)


class RegenerationLimitError(SophiaError):
    """Raised when a draft has reached the maximum regeneration attempts (3).

    Suggests starting fresh from different research rather than further
    iterating on the same draft.
    """

    def __init__(
        self,
        message: str = "Regeneration limit reached",
        detail: str | None = None,
        suggestion: str | None = (
            "Consider starting fresh from different research. "
            "You've reached the 3-attempt limit for this option."
        ),
    ) -> None:
        super().__init__(message, detail, suggestion)
