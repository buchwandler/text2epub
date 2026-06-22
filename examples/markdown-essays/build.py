"""Build a multi-chapter EPUB from a folder of Markdown files.

Run from the repository root after installing text2epub:

    python examples/markdown-essays/build.py

Output: examples/markdown-essays/dist/essays.epub
"""

from __future__ import annotations

from pathlib import Path

from text2epub import (
    BuildOptions,
    EpubMetadata,
    MarkdownBook,
    MarkdownChapter,
    create_epub_from_markdown,
)

HERE = Path(__file__).resolve().parent
CHAPTERS = HERE / "chapters"
OUTPUT = HERE / "dist" / "essays.epub"


def main() -> None:
    # Direct children of chapters/ are sorted by filename and become the spine.
    chapter_paths = sorted(CHAPTERS.glob("*.md"))

    book = MarkdownBook(
        # title and language are left empty so the YAML-like front matter in
        # chapter 01 (title, language, author, publisher, description, rights,
        # date, identifier) is used. Any field set here would override it.
        metadata=EpubMetadata(title="", language=""),
        chapters=[MarkdownChapter(path=path) for path in chapter_paths],
        options=BuildOptions(
            deterministic=True,
            include_title_page=True,
            include_toc_page=True,
            toc_page_numbers=True,
            css_files=[HERE / "style.css"],
        ),
    )

    output = create_epub_from_markdown(book, OUTPUT)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
