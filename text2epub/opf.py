from __future__ import annotations

from collections.abc import Sequence
from xml.sax.saxutils import escape

from .models import Author, EpubMetadata, XhtmlChapter


def build_content_opf(
    metadata: EpubMetadata,
    chapters: Sequence[XhtmlChapter],
    *,
    identifier: str,
    modified: str,
    include_ncx: bool,
    stylesheet_present: bool,
    asset_items: Sequence[tuple[str, str, str]],
) -> str:
    manifest_lines = [
        '    <item id="nav" href="nav.xhtml" '
        'media-type="application/xhtml+xml" properties="nav" />'
    ]
    if include_ncx:
        manifest_lines.append(
            '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />'
        )
    if stylesheet_present:
        manifest_lines.append(
            '    <item id="style-book" href="Styles/book.css" media-type="text/css" />'
        )
    manifest_lines.extend(
        (
            f'    <item id="{escape(chapter.id)}" '
            f'href="{escape(chapter.href)}" '
            f'media-type="{escape(chapter.media_type)}" />'
        )
        for chapter in chapters
    )
    manifest_lines.extend(
        (
            f'    <item id="{escape(item_id)}" href="{escape(href)}" '
            f'media-type="{escape(media_type)}" />'
        )
        for item_id, href, media_type in asset_items
    )
    spine_lines = [
        f'    <itemref idref="{escape(chapter.id)}" />' for chapter in chapters
    ]
    if include_ncx:
        spine_open = '  <spine toc="ncx">'
    else:
        spine_open = "  <spine>"
    metadata_lines = [
        f"    <dc:title>{escape(metadata.title)}</dc:title>",
        f"    <dc:language>{escape(metadata.language or 'en')}</dc:language>",
        f'    <dc:identifier id="bookid">{escape(identifier)}</dc:identifier>',
        f"    <meta property=\"dcterms:modified\">{escape(modified)}</meta>",
    ]
    metadata_lines.extend(
        f"    <dc:creator>{escape(_author_name(author))}</dc:creator>"
        for author in metadata.creators
    )
    metadata_lines.extend(
        f"    <dc:contributor>{escape(_author_name(author))}</dc:contributor>"
        for author in metadata.contributors
    )
    optional_fields = {
        "publisher": metadata.publisher,
        "description": metadata.description,
        "rights": metadata.rights,
        "date": metadata.date,
    }
    for tag, value in optional_fields.items():
        if value:
            metadata_lines.append(f"    <dc:{tag}>{escape(value)}</dc:{tag}>")
    metadata_block = "\n".join(metadata_lines)
    manifest_block = "\n".join(manifest_lines)
    spine_block = "\n".join(spine_lines)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="bookid" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        "  <metadata>\n"
        f"{metadata_block}\n"
        "  </metadata>\n"
        "  <manifest>\n"
        f"{manifest_block}\n"
        "  </manifest>\n"
        f"{spine_open}\n"
        f"{spine_block}\n"
        "  </spine>\n"
        "</package>\n"
    )


def _author_name(author: str | Author) -> str:
    if isinstance(author, Author):
        return author.name
    return author
