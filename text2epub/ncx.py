from __future__ import annotations

from collections.abc import Sequence
from xml.sax.saxutils import escape

from .models import XhtmlChapter


def build_ncx_document(
    title: str,
    chapters: Sequence[XhtmlChapter],
    *,
    identifier: str,
    language: str,
) -> str:
    nav_points = "\n".join(
        (
            f'    <navPoint id="navPoint-{index}" playOrder="{index}">\n'
            f"      <navLabel><text>{escape(chapter.title)}</text></navLabel>\n"
            f'      <content src="{escape(chapter.href)}" />\n'
            "    </navPoint>"
        )
        for index, chapter in enumerate(chapters, start=1)
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" '
        f'xml:lang="{escape(language or "en")}">\n'
        "  <head>\n"
        f'    <meta name="dtb:uid" content="{escape(identifier)}" />\n'
        "  </head>\n"
        f"  <docTitle><text>{escape(title)}</text></docTitle>\n"
        "  <navMap>\n"
        f"{nav_points}\n"
        "  </navMap>\n"
        "</ncx>\n"
    )
