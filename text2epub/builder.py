from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

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
.title-page {
  text-align: center;
  margin-top: 20%;
}
.title-page .subtitle {
  font-size: 1.2em;
}
.title-page .creator,
.title-page .publisher,
.title-page .date {
  margin-top: 1.5em;
}
.reader-toc ol {
  list-style-type: none;
  margin-left: 0;
  padding-left: 0;
}
.reader-toc li {
  margin: 0.35em 0;
}
.reader-toc.with-page-numbers a::after {
  content: leader('.') ' ' target-counter(attr(href), page);
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


def compose_spine_chapters(
    metadata: EpubMetadata,
    content_chapters: Sequence[XhtmlChapter],
    options: BuildOptions,
) -> list[XhtmlChapter]:
    """Return the EPUB spine, optionally prefixed by generated front matter."""

    existing_ids = {chapter.id for chapter in content_chapters}
    existing_hrefs = {chapter.href for chapter in content_chapters}
    generated: list[XhtmlChapter] = []

    if options.include_title_page:
        title_id = unique_generated_value("title-page", existing_ids)
        existing_ids.add(title_id)
        title_href = unique_generated_value("Text/title-page.xhtml", existing_hrefs)
        existing_hrefs.add(title_href)
        generated.append(
            XhtmlChapter(
                id=title_id,
                href=title_href,
                title="Title Page",
                body_xhtml=build_title_page_body(metadata),
            )
        )

    if options.include_toc_page:
        toc_id = unique_generated_value("table-of-contents", existing_ids)
        existing_ids.add(toc_id)
        toc_href = unique_generated_value(
            "Text/table-of-contents.xhtml", existing_hrefs
        )
        generated.append(
            XhtmlChapter(
                id=toc_id,
                href=toc_href,
                title="Table of Contents",
                body_xhtml=build_toc_page_body(
                    content_chapters,
                    toc_href=toc_href,
                    include_page_numbers=options.toc_page_numbers,
                ),
            )
        )

    return [*generated, *content_chapters]


def build_title_page_body(metadata: EpubMetadata) -> str:
    """Build the generated reader-visible title page body."""

    lines = [
        '<section class="title-page" epub:type="titlepage">',
        f"  <h1>{escape(metadata.title or 'Untitled')}</h1>",
    ]
    if metadata.description:
        lines.append(f'  <p class="subtitle">{escape(metadata.description)}</p>')
    creator_names = [author_name(author) for author in metadata.creators]
    if creator_names:
        lines.append(f'  <p class="creator">{escape(", ".join(creator_names))}</p>')
    if metadata.publisher:
        lines.append(f'  <p class="publisher">{escape(metadata.publisher)}</p>')
    if metadata.date:
        lines.append(f'  <p class="date">{escape(metadata.date)}</p>')
    if metadata.rights:
        lines.append(f'  <p class="rights">{escape(metadata.rights)}</p>')
    lines.append("</section>")
    return "\n".join(lines)


def build_toc_page_body(
    chapters: Sequence[XhtmlChapter],
    *,
    toc_href: str,
    include_page_numbers: bool,
) -> str:
    """Build a generated reader-visible table of contents body."""

    class_name = (
        "reader-toc with-page-numbers" if include_page_numbers else "reader-toc"
    )
    chapter_lines = []
    for chapter in chapters:
        href = relative_href(toc_href, chapter.href)
        chapter_lines.append(
            f'    <li><a href="{escape(href)}">{escape(chapter.title)}</a></li>'
        )
    return (
        f'<nav class="{class_name}" epub:type="toc">\n'
        "  <h1>Table of Contents</h1>\n"
        "  <ol>\n" + "\n".join(chapter_lines) + "\n  </ol>\n"
        "</nav>"
    )


def author_name(author: object) -> str:
    name = getattr(author, "name", None)
    if isinstance(name, str):
        return name
    return str(author)


def unique_generated_value(base: str, existing: set[str]) -> str:
    if base not in existing:
        return base
    if "." in base:
        stem, suffix = base.rsplit(".", 1)
        suffix = f".{suffix}"
    else:
        stem, suffix = base, ""
    index = 2
    while True:
        candidate = f"{stem}-{index}{suffix}"
        if candidate not in existing:
            return candidate
        index += 1


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
    content_chapters = list(chapters)
    identifier = resolve_identifier(metadata, content_chapters, resolved_options)
    resolved_metadata = replace(metadata, identifier=identifier)
    modified = modified_timestamp(resolved_options)
    spine_chapters = compose_spine_chapters(
        resolved_metadata,
        content_chapters,
        resolved_options,
    )

    stylesheet_text = compose_stylesheet(resolved_options)
    stylesheet_present = bool(stylesheet_text)
    generated_text_entries: dict[str, str] = {}
    package_entries: list[PackageEntry] = [
        PackageEntry(MIMETYPE_ENTRY, MIMETYPE_VALUE),
        PackageEntry(CONTAINER_ENTRY, container_xml().encode("utf-8")),
    ]

    for chapter in spine_chapters:
        stylesheet_href = None
        if stylesheet_present:
            stylesheet_href = relative_href(chapter.href, "Styles/book.css")
        chapter_document = render_xhtml_document(
            chapter.title,
            chapter.body_xhtml,
            resolved_metadata.language or "en",
            stylesheet_href=stylesheet_href,
        )
        entry_name = f"OEBPS/{chapter.href}"
        generated_text_entries[entry_name] = chapter_document
        package_entries.append(
            PackageEntry(entry_name, chapter_document.encode("utf-8"))
        )

    nav_document = build_nav_document(
        resolved_metadata.title,
        content_chapters,
        resolved_metadata.language or "en",
    )
    generated_text_entries[NAV_ENTRY] = nav_document
    package_entries.append(PackageEntry(NAV_ENTRY, nav_document.encode("utf-8")))

    if resolved_options.include_ncx:
        ncx_document = build_ncx_document(
            resolved_metadata.title,
            content_chapters,
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
        spine_chapters,
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
