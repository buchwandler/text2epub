from __future__ import annotations

try:
    from ._version import version as __version__
except Exception:  # pragma: no cover
    __version__ = "0.0.0+unknown"

from .builder import (
    create_epub,
    create_epub_from_markdown,
    create_epub_from_markdown_files,
    create_epub_from_markdown_folder,
)
from .markdown import discover_markdown_chapters
from .models import (
    Author,
    BuildOptions,
    EpubMetadata,
    MarkdownBook,
    MarkdownChapter,
    OutputRewriteOptions,
    OutputRewriteReport,
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
    "OutputRewriteOptions",
    "OutputRewriteReport",
    "Replacement",
    "ReplacementPlan",
    "ReplacementReport",
    "XhtmlChapter",
    "create_epub",
    "create_epub_from_markdown",
    "create_epub_from_markdown_files",
    "create_epub_from_markdown_folder",
    "discover_markdown_chapters",
    "rebuild_epub",
]
