from __future__ import annotations

from collections.abc import Sequence
from xml.sax.saxutils import escape

from .models import XhtmlChapter


def build_nav_document(
    title: str, chapters: Sequence[XhtmlChapter], language: str
) -> str:
    chapter_lines = "\n".join(
        "      "
        f'<li><a href="{escape(chapter.href)}">{escape(chapter.title)}</a></li>'
        for chapter in chapters
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" '
        f'lang="{escape(language or "en")}" xml:lang="{escape(language or "en")}">\n'
        "<head>\n"
        f"  <title>{escape(title)}</title>\n"
        "</head>\n"
        "<body>\n"
        '  <nav epub:type="toc" id="toc">\n'
        "    <h1>Table of Contents</h1>\n"
        "    <ol>\n"
        f"{chapter_lines}\n"
        "    </ol>\n"
        "  </nav>\n"
        "</body>\n"
        "</html>\n"
    )
