from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from text2epub import ReplacementPlan, rebuild_epub
from text2epub.errors import ValidationError
from text2epub.package import validate_epub_package
from text2epub.validation import scan_epub_for_unresolved_tokens, sha256_path

from .helpers import create_test_epub


def test_noop_rebuild_byte_identical(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Original text.</p>"])
    output = tmp_path / "out.epub"

    report = rebuild_epub(ReplacementPlan(source_epub=source, replacements=[]), output)

    assert sha256_path(output) == sha256_path(source)
    assert report.changed_entries == []


def test_mimetype_first_and_uncompressed(tmp_path: Path) -> None:
    epub_path = create_test_epub(tmp_path / "source.epub", ["<p>Hello.</p>"])

    with zipfile.ZipFile(epub_path) as archive:
        first = archive.infolist()[0]

    assert first.filename == "mimetype"
    assert first.compress_type == zipfile.ZIP_STORED


def test_invalid_missing_container_fails(tmp_path: Path) -> None:
    epub_path = tmp_path / "broken.epub"
    with zipfile.ZipFile(epub_path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip")

    with pytest.raises(ValidationError):
        validate_epub_package(epub_path)


def test_unresolved_token_scan_fails_with_entry_name(tmp_path: Path) -> None:
    epub_path = create_test_epub(
        tmp_path / "source.epub",
        ["<p>Hello __TAG_001__.</p>"],
    )

    findings = scan_epub_for_unresolved_tokens(epub_path)

    assert findings == [("OEBPS/Text/chapter01.xhtml", "__TAG_001__")]
