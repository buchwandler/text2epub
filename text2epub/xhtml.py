from __future__ import annotations

from xml.sax.saxutils import escape


def render_xhtml_document(
    title: str,
    body_xhtml: str,
    language: str,
    stylesheet_href: str | None = None,
) -> str:
    stylesheet = ""
    if stylesheet_href:
        stylesheet = (
            '  <link rel="stylesheet" type="text/css" '
            f'href="{escape(stylesheet_href)}" />\n'
        )
    escaped_title = escape(title)
    escaped_language = escape(language or "en")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" lang="{escaped_language}" '
        f'xml:lang="{escaped_language}">\n'
        "<head>\n"
        f"  <title>{escaped_title}</title>\n"
        f"{stylesheet}"
        "</head>\n"
        "<body>\n"
        f"{body_xhtml}\n"
        "</body>\n"
        "</html>\n"
    )
