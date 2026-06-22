from __future__ import annotations

try:
    from ._version import version as __version__
except Exception:  # pragma: no cover
    __version__ = "0.0.0+unknown"

from .builder import create_epub, create_epub_from_markdown
from .models import (
    Author,
    BuildOptions,
    EpubMetadata,
    MarkdownBook,
    MarkdownChapter,
    Replacement,
    ReplacementPlan,
    ReplacementReport,
    XhtmlChapter,
)
from .replacement import rebuild_epub

__all__ = [
    "__version__",
    "Author",
    "BuildOptions",
    "EpubMetadata",
    "MarkdownBook",
    "MarkdownChapter",
    "Replacement",
    "ReplacementPlan",
    "ReplacementReport",
    "XhtmlChapter",
    "create_epub",
    "create_epub_from_markdown",
    "rebuild_epub",
]
