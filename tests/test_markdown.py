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
        "---\ntitle: Front Matter Title\nlanguage: de\n---\n\n# Kapitel\n\nHallo.\n",
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


def test_remote_images_allowed_stay_external(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text(
        "# Images\n\n![Remote](https://example.com/cover.png)\n",
        encoding="utf-8",
    )
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(title="Example"),
            chapters=[MarkdownChapter(path=chapter)],
            options=BuildOptions(allow_remote_resources=True),
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        chapter_text = archive.read("OEBPS/Text/chapter-001.xhtml").decode("utf-8")

    assert "https://example.com/cover.png" in chapter_text
    assert not any(name.startswith("OEBPS/Images/") for name in archive.namelist())


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


def test_discover_markdown_chapters_sorts_folder(tmp_path: Path) -> None:
    (tmp_path / "02-body.md").write_text("# Body\n", encoding="utf-8")
    (tmp_path / "01-start.md").write_text("# Start\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore\n", encoding="utf-8")

    from text2epub import discover_markdown_chapters

    chapters = discover_markdown_chapters(tmp_path)

    assert [chapter.path.name for chapter in chapters] == ["01-start.md", "02-body.md"]


def test_create_epub_from_markdown_folder(tmp_path: Path) -> None:
    manuscript = tmp_path / "manuscript"
    manuscript.mkdir()
    (manuscript / "00-metadata.md").write_text(
        "---\n"
        "title: Folder Book\n"
        "language: en\n"
        "author: Ada Lovelace\n"
        "---\n\n"
        "# Introduction\n\nAlpha.\n",
        encoding="utf-8",
    )
    (manuscript / "01-chapter.md").write_text(
        "# Chapter One\n\nBeta.\n", encoding="utf-8"
    )
    output = tmp_path / "folder-book.epub"

    from text2epub import create_epub_from_markdown_folder

    create_epub_from_markdown_folder(manuscript, output)

    with zipfile.ZipFile(output) as archive:
        content_opf = archive.read("OEBPS/content.opf").decode("utf-8")
        first = archive.read("OEBPS/Text/chapter-001.xhtml").decode("utf-8")
        second = archive.read("OEBPS/Text/chapter-002.xhtml").decode("utf-8")

    assert "<dc:title>Folder Book</dc:title>" in content_opf
    assert "<dc:creator>Ada Lovelace</dc:creator>" in content_opf
    assert "Alpha." in first
    assert "Beta." in second


def test_markdown_escapes_inline_xhtml_by_default(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text("# Inline\n\nThis is <em>escaped</em>.\n", encoding="utf-8")
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

    assert "&lt;em&gt;escaped&lt;/em&gt;" in chapter_text
    assert "<em>escaped</em>" not in chapter_text


def test_markdown_allows_safe_inline_xhtml_when_enabled(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text(
        '# Inline\n\nThis is <em class="voice">preserved</em>, '
        "<strong>strong</strong>, <span>span</span>, "
        '<a href="chapter.xhtml#target">link</a>, '
        "line<br/>break, <sup>sup</sup>, and <sub>sub</sub>.\n",
        encoding="utf-8",
    )
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(title="Example"),
            chapters=[MarkdownChapter(path=chapter)],
            options=BuildOptions(allow_inline_xhtml=True),
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        chapter_text = archive.read("OEBPS/Text/chapter-001.xhtml").decode("utf-8")

    assert '<em class="voice">preserved</em>' in chapter_text
    assert "<strong>strong</strong>" in chapter_text
    assert "<span>span</span>" in chapter_text
    assert '<a href="chapter.xhtml#target">link</a>' in chapter_text
    assert "line<br/>break" in chapter_text
    assert "<sup>sup</sup>" in chapter_text
    assert "<sub>sub</sub>" in chapter_text


def test_markdown_rejects_unsafe_inline_xhtml_when_enabled(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text(
        '# Inline\n\nThis is <span onclick="evil()">unsafe</span>.\n',
        encoding="utf-8",
    )

    with pytest.raises(BuildError):
        create_epub_from_markdown(
            MarkdownBook(
                metadata=EpubMetadata(title="Example"),
                chapters=[MarkdownChapter(path=chapter)],
                options=BuildOptions(allow_inline_xhtml=True),
            ),
            tmp_path / "book.epub",
        )


def test_markdown_rejects_raw_block_xhtml_when_enabled(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text("# Inline\n\n<div>raw block</div>\n", encoding="utf-8")

    with pytest.raises(BuildError):
        create_epub_from_markdown(
            MarkdownBook(
                metadata=EpubMetadata(title="Example"),
                chapters=[MarkdownChapter(path=chapter)],
                options=BuildOptions(allow_inline_xhtml=True),
            ),
            tmp_path / "book.epub",
        )


def test_markdown_rejects_malformed_inline_xhtml_when_enabled(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text("# Inline\n\nThis is <em>unclosed.\n", encoding="utf-8")

    with pytest.raises(BuildError):
        create_epub_from_markdown(
            MarkdownBook(
                metadata=EpubMetadata(title="Example"),
                chapters=[MarkdownChapter(path=chapter)],
                options=BuildOptions(allow_inline_xhtml=True),
            ),
            tmp_path / "book.epub",
        )


def test_markdown_rejects_raw_inline_img_when_enabled(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text(
        '# Inline\n\nThis is <img src="image.png" alt="raw"/> inline.\n',
        encoding="utf-8",
    )

    with pytest.raises(BuildError):
        create_epub_from_markdown(
            MarkdownBook(
                metadata=EpubMetadata(title="Example"),
                chapters=[MarkdownChapter(path=chapter)],
                options=BuildOptions(allow_inline_xhtml=True),
            ),
            tmp_path / "book.epub",
        )


def test_markdown_allows_inline_xhtml_namespaced_attributes(
    tmp_path: Path,
) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text(
        "# Inline\n\nThis is "
        '<span xml:lang="fr" epub:type="z3998:verse">texte</span>.\n',
        encoding="utf-8",
    )
    output = tmp_path / "book.epub"

    create_epub_from_markdown(
        MarkdownBook(
            metadata=EpubMetadata(title="Example"),
            chapters=[MarkdownChapter(path=chapter)],
            options=BuildOptions(allow_inline_xhtml=True),
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        chapter_text = archive.read("OEBPS/Text/chapter-001.xhtml").decode("utf-8")

    assert '<span xml:lang="fr" epub:type="z3998:verse">texte</span>' in chapter_text
