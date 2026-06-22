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
