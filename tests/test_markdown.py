from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from text2epub import BuildOptions, EpubMetadata, MarkdownBook, MarkdownChapter
from text2epub.builder import create_epub_from_markdown
from text2epub.errors import BuildError

from .helpers import PNG_BYTES


def test_single_markdown_to_epub(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text("# Chapter One\n\nHello world.\n", encoding="utf-8")
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(title="Example"),
            chapters=[MarkdownChapter(path=chapter)],
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        assert "mimetype" in archive.namelist()
        assert "META-INF/container.xml" in archive.namelist()
        assert "OEBPS/content.opf" in archive.namelist()
        assert "OEBPS/nav.xhtml" in archive.namelist()
        assert "OEBPS/Text/chapter-001.xhtml" in archive.namelist()


def test_front_matter_metadata(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text(
        "---\n"
        "title: Front Matter Title\n"
        "language: de\n"
        "author: Ada Lovelace\n"
        "---\n"
        "\n"
        "# Kapitel\n\nHallo.\n",
        encoding="utf-8",
    )
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(title="", language=""),
            chapters=[MarkdownChapter(path=chapter)],
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        content_opf = archive.read("OEBPS/content.opf").decode("utf-8")

    assert "<dc:title>Front Matter Title</dc:title>" in content_opf
    assert "<dc:language>de</dc:language>" in content_opf
    assert "<dc:creator>Ada Lovelace</dc:creator>" in content_opf


def test_explicit_metadata_overrides_front_matter(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text(
        "---\n"
        "title: Front Matter Title\n"
        "language: de\n"
        "---\n"
        "\n"
        "# Kapitel\n\nHallo.\n",
        encoding="utf-8",
    )
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(title="Explicit Title", language="en"),
            chapters=[MarkdownChapter(path=chapter)],
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        content_opf = archive.read("OEBPS/content.opf").decode("utf-8")

    assert "<dc:title>Explicit Title</dc:title>" in content_opf
    assert "<dc:language>en</dc:language>" in content_opf


def test_heading_ids_are_stable(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text("# Hello World\n\n## Another Heading\n", encoding="utf-8")
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(title="Example"),
            chapters=[MarkdownChapter(path=chapter)],
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        chapter_text = archive.read("OEBPS/Text/chapter-001.xhtml").decode("utf-8")

    assert 'id="hello-world"' in chapter_text
    assert 'id="another-heading"' in chapter_text


def test_duplicate_heading_ids_get_suffix(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text("# Hello\n\n## Hello\n\n## Hello\n", encoding="utf-8")
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(title="Example"),
            chapters=[MarkdownChapter(path=chapter)],
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        chapter_text = archive.read("OEBPS/Text/chapter-001.xhtml").decode("utf-8")

    assert 'id="hello"' in chapter_text
    assert 'id="hello-2"' in chapter_text
    assert 'id="hello-3"' in chapter_text


def test_tables_render(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text(
        "# Table\n\n| A | B |\n| - | - |\n| 1 | 2 |\n",
        encoding="utf-8",
    )
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(title="Example"),
            chapters=[MarkdownChapter(path=chapter)],
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        chapter_text = archive.read("OEBPS/Text/chapter-001.xhtml").decode("utf-8")

    assert "<table>" in chapter_text
    assert "<td>1</td>" in chapter_text


def test_code_blocks_preserved(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text(
        "# Code\n\n```python\nprint('hello')\n```\n",
        encoding="utf-8",
    )
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(title="Example"),
            chapters=[MarkdownChapter(path=chapter)],
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        chapter_text = archive.read("OEBPS/Text/chapter-001.xhtml").decode("utf-8")

    assert "<pre><code" in chapter_text
    assert "print('hello')" in chapter_text


def test_links_are_escaped(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text(
        "# Links\n\n[Example](https://example.com?a=1&b=2)\n",
        encoding="utf-8",
    )
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(title="Example"),
            chapters=[MarkdownChapter(path=chapter)],
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        chapter_text = archive.read("OEBPS/Text/chapter-001.xhtml").decode("utf-8")

    assert "https://example.com?a=1&amp;b=2" in chapter_text


def test_images_local_only_by_default(tmp_path: Path) -> None:
    image = tmp_path / "cover.png"
    image.write_bytes(PNG_BYTES)
    chapter = tmp_path / "chapter.md"
    chapter.write_text("# Images\n\n![Cover](cover.png)\n", encoding="utf-8")
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(title="Example"),
            chapters=[MarkdownChapter(path=chapter)],
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        chapter_text = archive.read("OEBPS/Text/chapter-001.xhtml").decode("utf-8")

    assert "OEBPS/Images/image-001.png" in archive.namelist()
    assert "../Images/image-001.png" in chapter_text


def test_remote_images_rejected_by_default(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text(
        "# Images\n\n![Remote](https://example.com/cover.png)\n",
        encoding="utf-8",
    )

    with pytest.raises(BuildError):
        create_epub_from_markdown(
            MarkdownBook(
                metadata=EpubMetadata(title="Example"),
                chapters=[MarkdownChapter(path=chapter)],
            ),
            tmp_path / "book.epub",
        )


def test_multiple_markdown_files_spine_order(tmp_path: Path) -> None:
    first = tmp_path / "01-first.md"
    second = tmp_path / "02-second.md"
    first.write_text("# First\n\nAlpha.\n", encoding="utf-8")
    second.write_text("# Second\n\nBeta.\n", encoding="utf-8")
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(title="Example"),
            chapters=[
                MarkdownChapter(path=first),
                MarkdownChapter(path=second),
            ],
            options=BuildOptions(deterministic=True),
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        content_opf = archive.read("OEBPS/content.opf").decode("utf-8")

    assert content_opf.index('idref="chapter-001"') < content_opf.index(
        'idref="chapter-002"'
    )
