from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .errors import BuildError
from .markdown import (
    RenderedAsset,
    discover_markdown_chapters,
    prepare_markdown_book,
    relative_href,
)
from .models import (
    BuildOptions,
    EpubMetadata,
    MarkdownBook,
    MarkdownChapter,
    XhtmlChapter,
)
from .nav import build_nav_document
from .ncx import build_ncx_document
from .opf import build_content_opf
from .package import (
    CONTAINER_ENTRY,
    CONTENT_OPF_ENTRY,
    MIMETYPE_ENTRY,
    MIMETYPE_VALUE,
    NAV_ENTRY,
    PackageEntry,
    validate_epub_package,
    write_generated_epub,
)
from .validation import ensure_no_unresolved_tokens
from .xhtml import render_xhtml_document

DEFAULT_CSS = """body {
  line-height: 1.4;
}
p {
  margin: 0 0 1em 0;
}
h1, h2, h3 {
  margin-top: 1.5em;
}
"""


def create_epub_from_markdown_files(
    chapter_paths: Sequence[Path | str],
    output_path: Path | str,
    *,
    metadata: EpubMetadata | None = None,
    options: BuildOptions | None = None,
) -> Path:
    """Create an EPUB from an explicit list of Markdown files.

    The supplied order is the EPUB spine order. Use this helper when your
    application already knows the chapter files and should not rely on folder
    discovery. Metadata may come from the first file's front matter when
    ``metadata`` is omitted or fields are left empty.
    """

    chapters = [MarkdownChapter(path=Path(path)) for path in chapter_paths]
    if not chapters:
        raise BuildError("create_epub_from_markdown_files requires at least one file.")
    book = MarkdownBook(
        metadata=metadata or EpubMetadata(title="", language=""),
        chapters=chapters,
        options=options or BuildOptions(),
    )
    return create_epub_from_markdown(book, output_path)


def create_epub_from_markdown_folder(
    input_dir: Path | str,
    output_path: Path | str,
    *,
    metadata: EpubMetadata | None = None,
    options: BuildOptions | None = None,
    pattern: str = "*.md",
    recursive: bool = False,
) -> Path:
    """Create an EPUB from Markdown files discovered in a folder.

    Direct children matching ``pattern`` are sorted by filename by default. This
    supports simple manuscript folder conventions such as
    ``00-front-matter.md``, ``01-introduction.md`` and ``02-chapter.md``. Set
    ``recursive=True`` to sort matching files by relative path.
    """

    chapters = discover_markdown_chapters(
        input_dir,
        pattern=pattern,
        recursive=recursive,
    )
    book = MarkdownBook(
        metadata=metadata or EpubMetadata(title="", language=""),
        chapters=chapters,
        options=options or BuildOptions(),
    )
    return create_epub_from_markdown(book, output_path)


def create_epub_from_markdown(book: MarkdownBook, output_path: Path | str) -> Path:
    rendered = prepare_markdown_book(book)
    return create_epub(
        metadata=rendered.metadata,
        chapters=rendered.chapters,
        output_path=output_path,
        options=rendered.options,
        assets=rendered.assets,
    )


def create_epub(
    metadata: EpubMetadata,
    chapters: Sequence[XhtmlChapter],
    output_path: Path | str,
    *,
    options: BuildOptions | None = None,
    assets: Sequence[RenderedAsset] | None = None,
) -> Path:
    if not chapters:
        raise BuildError("create_epub requires at least one XHTML chapter.")

    resolved_options = options or BuildOptions()
    resolved_assets = list(assets or [])
    identifier = resolve_identifier(metadata, chapters, resolved_options)
    resolved_metadata = replace(metadata, identifier=identifier)
    modified = modified_timestamp(resolved_options)

    stylesheet_text = compose_stylesheet(resolved_options)
    stylesheet_present = bool(stylesheet_text)
    generated_text_entries: dict[str, str] = {}
    package_entries: list[PackageEntry] = [
        PackageEntry(MIMETYPE_ENTRY, MIMETYPE_VALUE),
        PackageEntry(CONTAINER_ENTRY, container_xml().encode("utf-8")),
    ]

    chapter_docs: list[XhtmlChapter] = []
    for chapter in chapters:
        stylesheet_href = None
        if stylesheet_present:
            stylesheet_href = relative_href(chapter.href, "Styles/book.css")
        chapter_document = render_xhtml_document(
            chapter.title,
            chapter.body_xhtml,
            resolved_metadata.language or "en",
            stylesheet_href=stylesheet_href,
        )
        chapter_docs.append(chapter)
        entry_name = f"OEBPS/{chapter.href}"
        generated_text_entries[entry_name] = chapter_document
        package_entries.append(
            PackageEntry(entry_name, chapter_document.encode("utf-8"))
        )

    nav_document = build_nav_document(
        resolved_metadata.title,
        chapter_docs,
        resolved_metadata.language or "en",
    )
    generated_text_entries[NAV_ENTRY] = nav_document
    package_entries.append(PackageEntry(NAV_ENTRY, nav_document.encode("utf-8")))

    if resolved_options.include_ncx:
        ncx_document = build_ncx_document(
            resolved_metadata.title,
            chapter_docs,
            identifier=identifier,
            language=resolved_metadata.language or "en",
        )
        generated_text_entries["OEBPS/toc.ncx"] = ncx_document
        package_entries.append(
            PackageEntry("OEBPS/toc.ncx", ncx_document.encode("utf-8"))
        )

    if stylesheet_text:
        package_entries.append(
            PackageEntry("OEBPS/Styles/book.css", stylesheet_text.encode("utf-8"))
        )

    asset_items: list[tuple[str, str, str]] = []
    for index, asset in enumerate(resolved_assets, start=1):
        item_id = f"image-{index:03d}"
        asset_items.append((item_id, asset.href, asset.media_type))
        package_entries.append(PackageEntry(f"OEBPS/{asset.href}", asset.data))

    content_opf = build_content_opf(
        resolved_metadata,
        chapter_docs,
        identifier=identifier,
        modified=modified,
        include_ncx=resolved_options.include_ncx,
        stylesheet_present=stylesheet_present,
        asset_items=asset_items,
    )
    generated_text_entries[CONTENT_OPF_ENTRY] = content_opf
    package_entries.append(PackageEntry(CONTENT_OPF_ENTRY, content_opf.encode("utf-8")))

    if resolved_options.fail_on_unresolved_tokens:
        ensure_no_unresolved_tokens(
            generated_text_entries, resolved_options.unresolved_token_patterns
        )

    result_path = write_generated_epub(
        package_entries,
        output_path,
        deterministic=resolved_options.deterministic,
    )
    validate_epub_package(result_path)
    return result_path


def compose_stylesheet(options: BuildOptions) -> str | None:
    parts: list[str] = []
    if options.include_default_css:
        parts.append(DEFAULT_CSS.strip())
    if options.css_text:
        parts.append(options.css_text.strip())
    for css_file in options.css_files:
        if not css_file.exists():
            raise BuildError(f"CSS file {css_file} does not exist.")
        parts.append(css_file.read_text(encoding="utf-8").strip())
    combined = "\n\n".join(part for part in parts if part)
    return combined or None


def resolve_identifier(
    metadata: EpubMetadata,
    chapters: Sequence[XhtmlChapter],
    options: BuildOptions,
) -> str:
    if metadata.identifier:
        return metadata.identifier
    if options.deterministic:
        seed = "|".join(
            [
                metadata.title,
                metadata.language or "en",
                *(
                    f"{chapter.id}:{chapter.href}:{chapter.title}:{chapter.body_xhtml}"
                    for chapter in chapters
                ),
            ]
        )
        return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, seed)}"
    return f"urn:uuid:{uuid.uuid4()}"


def modified_timestamp(options: BuildOptions) -> str:
    if options.deterministic:
        return "1980-01-01T00:00:00Z"
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def container_xml() -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        "  <rootfiles>\n"
        '    <rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml" />\n'
        "  </rootfiles>\n"
        "</container>\n"
    )
