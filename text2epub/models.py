from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

DEFAULT_UNRESOLVED_TOKEN_PATTERNS = [
    r"__(?:TAG|NAME)_\d+__",
    r"__SPANTX_\d+__",
]


@dataclass(slots=True)
class Author:
    name: str
    file_as: str | None = None
    role: str | None = None


@dataclass(slots=True)
class EpubMetadata:
    title: str
    language: str = "en"
    creators: list[str | Author] = field(default_factory=list)
    contributors: list[str | Author] = field(default_factory=list)
    publisher: str | None = None
    description: str | None = None
    identifier: str | None = None
    rights: str | None = None
    date: str | None = None


@dataclass(slots=True)
class BuildOptions:
    epub_version: str = "3.0"
    include_ncx: bool = True
    pretty_print: bool = False
    css_text: str | None = None
    css_files: list[Path] = field(default_factory=list)
    deterministic: bool = True
    fail_on_unresolved_tokens: bool = True
    unresolved_token_patterns: list[str] = field(
        default_factory=lambda: DEFAULT_UNRESOLVED_TOKEN_PATTERNS.copy()
    )
    include_default_css: bool = True
    allow_remote_resources: bool = False
    allow_inline_xhtml: bool = False
    include_title_page: bool = False
    include_toc_page: bool = False
    toc_page_numbers: bool = False


@dataclass(slots=True)
class MarkdownChapter:
    path: Path
    title: str | None = None
    href: str | None = None
    id: str | None = None


@dataclass(slots=True)
class MarkdownBook:
    metadata: EpubMetadata
    chapters: list[MarkdownChapter]
    options: BuildOptions = field(default_factory=BuildOptions)


@dataclass(slots=True)
class XhtmlChapter:
    id: str
    href: str
    title: str
    body_xhtml: str
    media_type: str = "application/xhtml+xml"


@dataclass(slots=True)
class OutputRewriteOptions:
    """Opt-in output rewrite applied during :func:`rebuild_epub`.

    The options describe generic, product-agnostic changes. text2epub does not
    resolve a target language for a caller and does not interpret injected CSS.
    """

    language: str | None = None
    patch_package_language: bool = False
    patch_content_language: bool = False
    patch_body_language: bool = False

    css_text: str | None = None
    style_id: str = "text2epub-output-policy"
    content_scope: Literal[
        "replacement-manifest",
        "spine",
        "spine-and-navigation",
        "explicit",
    ] = "spine-and-navigation"
    content_hrefs: list[str] = field(default_factory=list)
    inject_css_into_fixed_layout: bool = False


@dataclass(slots=True)
class OutputRewriteReport:
    """Structured detail for an output rewrite applied during a rebuild."""

    applied: bool = False
    opf_path: str | None = None
    changed_entries: list[str] = field(default_factory=list)
    targeted_content_entries: list[str] = field(default_factory=list)
    language_patched_entries: list[str] = field(default_factory=list)
    css_injected_entries: list[str] = field(default_factory=list)
    fixed_layout_skipped_entries: list[str] = field(default_factory=list)
    old_primary_language: str | None = None
    new_primary_language: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Replacement:
    block_id: str
    text: str
    expected_source: str | None = None
    allow_inline_xhtml: bool = True


@dataclass(slots=True)
class ReplacementPlan:
    source_epub: Path | str
    extraction_manifest: Path | str | Mapping[str, Any] | None = None
    replacements: list[Replacement] = field(default_factory=list)
    options: BuildOptions = field(default_factory=BuildOptions)
    output_rewrite: OutputRewriteOptions | None = None


@dataclass(slots=True)
class ReplacementReport:
    output_path: Path
    changed_entries: list[str]
    unchanged_entries: list[str]
    replacement_count: int
    unresolved_token_count: int
    warnings: list[str] = field(default_factory=list)
    output_rewrite: OutputRewriteReport | None = None
