from __future__ import annotations

from text2epub.xhtml import render_xhtml_document


def test_render_xhtml_document_includes_stylesheet() -> None:
    document = render_xhtml_document(
        "Chapter One",
        "<p>Hello.</p>",
        "en",
        stylesheet_href="../Styles/book.css",
    )

    assert "../Styles/book.css" in document
    assert 'xml:lang="en"' in document


def test_render_xhtml_document_omits_stylesheet_when_missing() -> None:
    document = render_xhtml_document("Chapter One", "<p>Hello.</p>", "en")

    assert "stylesheet" not in document
