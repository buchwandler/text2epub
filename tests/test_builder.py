from __future__ import annotations

from pathlib import Path

from text2epub import BuildOptions, EpubMetadata, MarkdownBook, MarkdownChapter
from text2epub.builder import create_epub, create_epub_from_markdown
from text2epub.models import XhtmlChapter
from text2epub.validation import sha256_path


def test_generated_epub_deterministic(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text("# Hello\n\nWorld.\n", encoding="utf-8")
    left = tmp_path / "left.epub"
    right = tmp_path / "right.epub"
    book = MarkdownBook(
        metadata=EpubMetadata(title="Example"),
        chapters=[MarkdownChapter(path=chapter)],
        options=BuildOptions(deterministic=True),
    )

    create_epub_from_markdown(book, left)
    create_epub_from_markdown(book, right)

    assert sha256_path(left) == sha256_path(right)


def test_create_epub_from_xhtml_chapters(tmp_path: Path) -> None:
    output = tmp_path / "book.epub"

    create_epub(
        metadata=EpubMetadata(title="Example", language="en"),
        chapters=[
            XhtmlChapter(
                id="chapter-001",
                href="Text/chapter-001.xhtml",
                title="Chapter One",
                body_xhtml="<h1>Chapter One</h1><p>Hello.</p>",
            )
        ],
        output_path=output,
        options=BuildOptions(deterministic=True),
    )

    assert output.exists()


def test_generated_title_and_toc_pages_are_in_spine(tmp_path: Path) -> None:
    first = tmp_path / "01-first.md"
    second = tmp_path / "02-second.md"
    first.write_text("# First\n\nAlpha.\n", encoding="utf-8")
    second.write_text("# Second\n\nBeta.\n", encoding="utf-8")
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(
                title="Example",
                language="en",
                creators=["Ada Lovelace"],
                publisher="Example Press",
                date="2026-06-22",
            ),
            chapters=[MarkdownChapter(path=first), MarkdownChapter(path=second)],
            options=BuildOptions(
                deterministic=True,
                include_title_page=True,
                include_toc_page=True,
                toc_page_numbers=True,
            ),
        ),
        output,
    )

    import zipfile

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        content_opf = archive.read("OEBPS/content.opf").decode("utf-8")
        title_page = archive.read("OEBPS/Text/title-page.xhtml").decode("utf-8")
        toc_page = archive.read("OEBPS/Text/table-of-contents.xhtml").decode("utf-8")
        nav_page = archive.read("OEBPS/nav.xhtml").decode("utf-8")
        stylesheet = archive.read("OEBPS/Styles/book.css").decode("utf-8")

    assert "OEBPS/Text/title-page.xhtml" in names
    assert "OEBPS/Text/table-of-contents.xhtml" in names
    assert content_opf.index('idref="title-page"') < content_opf.index(
        'idref="table-of-contents"'
    )
    assert content_opf.index('idref="table-of-contents"') < content_opf.index(
        'idref="chapter-001"'
    )
    assert "Ada Lovelace" in title_page
    assert "with-page-numbers" in toc_page
    assert "target-counter" in stylesheet
    assert "title-page.xhtml" not in nav_page
    assert "table-of-contents.xhtml" not in nav_page
    assert "First" in nav_page
    assert "Second" in nav_page
