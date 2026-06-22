from __future__ import annotations


class Text2EpubError(Exception):
    """Base exception for text2epub."""


class BuildError(Text2EpubError):
    """Raised when generated EPUB creation fails."""


class ValidationError(Text2EpubError):
    """Raised when validation detects an unsafe or invalid EPUB."""


class ReplacementError(Text2EpubError):
    """Raised when a replacement plan cannot be applied safely."""


class PackageError(Text2EpubError):
    """Raised when ZIP package handling fails."""


class UnsafeFragmentError(Text2EpubError):
    """Raised when inline XHTML fragments are unsafe."""
