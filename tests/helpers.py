from __future__ import annotations

import base64
import json
import zipfile
from pathlib import Path

from text2epub.validation import sha256_bytes, sha256_path

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/w8AAusB9Y9n4J8AAAAASUVORK5CYII="
)
ZIP_DT = (2020, 1, 1, 0, 0, 0)


def chapter_document(body: str, *, title: str = "Chapter") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">\n'
        "<head>\n"
        f"  <title>{title}</title>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def create_test_epub(
    path: Path,
    chapter_bodies: list[str],
    *,
    extra_entries: dict[str, bytes] | None = None,
) -> Path:
    chapter_names = [
        f"OEBPS/Text/chapter{index:02d}.xhtml"
        for index in range(1, len(chapter_bodies) + 1)
    ]
    manifest_items = "\n".join(
        (
            f'    <item id="chapter-{index:03d}" href="Text/chapter{index:02d}.xhtml" '
            'media-type="application/xhtml+xml" />'
        )
        for index in range(1, len(chapter_bodies) + 1)
    )
    spine_items = "\n".join(
        f'    <itemref idref="chapter-{index:03d}" />'
        for index in range(1, len(chapter_bodies) + 1)
    )
    nav_items = "\n".join(
        (
            f'      <li><a href="Text/chapter{index:02d}.xhtml">'
            f"Chapter {index}</a></li>"
        )
        for index in range(1, len(chapter_bodies) + 1)
    )
    content_opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="bookid" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        "  <metadata>\n"
        "    <dc:title>Fixture</dc:title>\n"
        "    <dc:language>en</dc:language>\n"
        "    <dc:identifier id=\"bookid\">urn:uuid:fixture</dc:identifier>\n"
        "  </metadata>\n"
        "  <manifest>\n"
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
        'properties="nav" />\n'
        f"{manifest_items}\n"
        "  </manifest>\n"
        "  <spine>\n"
        f"{spine_items}\n"
        "  </spine>\n"
        "</package>\n"
    )
    nav_document = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "<head><title>Fixture</title></head>\n"
        "<body>\n"
        '  <nav epub:type="toc" id="toc">\n'
        "    <ol>\n"
        f"{nav_items}\n"
        "    </ol>\n"
        "  </nav>\n"
        "</body>\n"
        "</html>\n"
    )
    entries: list[tuple[str, bytes, int]] = [
        ("mimetype", b"application/epub+zip", zipfile.ZIP_STORED),
        (
            "META-INF/container.xml",
            (
                b'<?xml version="1.0" encoding="utf-8"?>\n'
                b'<container version="1.0" '
                b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                b"  <rootfiles>\n"
                b'    <rootfile full-path="OEBPS/content.opf" '
                b'media-type="application/oebps-package+xml" />\n'
                b"  </rootfiles>\n"
                b"</container>\n"
            ),
            zipfile.ZIP_DEFLATED,
        ),
        ("OEBPS/content.opf", content_opf.encode("utf-8"), zipfile.ZIP_DEFLATED),
        ("OEBPS/nav.xhtml", nav_document.encode("utf-8"), zipfile.ZIP_DEFLATED),
    ]
    entries.extend(
        (
            name,
            chapter_document(body, title=f"Chapter {index}").encode("utf-8"),
            zipfile.ZIP_DEFLATED,
        )
        for index, (name, body) in enumerate(
            zip(chapter_names, chapter_bodies, strict=True), start=1
        )
    )
    for name, data in (extra_entries or {}).items():
        entries.append((name, data, zipfile.ZIP_DEFLATED))
    write_epub(path, entries)
    return path


def write_epub(path: Path, entries: list[tuple[str, bytes, int]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data, compress_type in entries:
            info = zipfile.ZipInfo(name, date_time=ZIP_DT)
            info.compress_type = compress_type
            archive.writestr(info, data)


def create_manifest_for_fragment(
    epub_path: Path,
    entry_name: str,
    source_fragment: str,
    *,
    block_id: str = "spine-0001:block-000001",
    replacement_mode: str = "whole_block_body",
    block_text: str | None = None,
) -> dict[str, object]:
    with zipfile.ZipFile(epub_path) as archive:
        raw_bytes = archive.read(entry_name)
        text = raw_bytes.decode("utf-8")
    start = text.index(source_fragment)
    end = start + len(source_fragment)
    block: dict[str, object] = {
        "block_id": block_id,
        "text": block_text if block_text is not None else source_fragment,
        "source_start": start,
        "source_end": end,
        "replacement_mode": replacement_mode,
    }
    if replacement_mode == "whole_block_body":
        block["body_source_start"] = start
        block["body_source_end"] = end
        block["source_fragment"] = source_fragment
    return {
        "schema_version": 1,
        "source_sha256": sha256_path(epub_path),
        "entries": [
            {
                "href": entry_name,
                "media_type": "application/xhtml+xml",
                "spine_index": 1,
                "raw_sha256": sha256_bytes(raw_bytes),
                "blocks": [block],
            }
        ],
    }


def write_manifest(path: Path, manifest: dict[str, object]) -> Path:
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path
