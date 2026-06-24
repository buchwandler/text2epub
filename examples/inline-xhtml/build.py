"""Build an EPUB demonstrating safe inline XHTML in Markdown.

Run from the repository root after installing text2epub:

    python examples/inline-xhtml/build.py

Output: examples/inline-xhtml/dist/inline-xhtml-demo.epub
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
OUTPUT = HERE / "dist" / "inline-xhtml-demo.epub"


def main() -> None:
    chapter_paths = sorted(CHAPTERS.glob("*.md"))

    book = MarkdownBook(
        # Metadata comes from the YAML front matter in the chapter.
        metadata=EpubMetadata(title="", language=""),
        chapters=[MarkdownChapter(path=path) for path in chapter_paths],
        options=BuildOptions(
            deterministic=True,
            allow_inline_xhtml=True,
        ),
    )

    output = create_epub_from_markdown(book, OUTPUT)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
