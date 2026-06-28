from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from text2epub import ReplacementPlan, rebuild_epub
from text2epub.errors import PackageError, ValidationError
from text2epub.package import rewrite_epub, validate_epub_package
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


def _find_temp_files(directory: Path) -> list[Path]:
    return [
        p
        for p in directory.iterdir()
        if p.name.startswith(".") and p.name.endswith(".tmp")
    ]


def test_noop_rebuild_leaves_no_temp_files(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Hello.</p>"])
    rebuild_epub(
        ReplacementPlan(source_epub=source, replacements=[]),
        tmp_path / "out.epub",
    )
    assert _find_temp_files(tmp_path) == []


def test_rewrite_leaves_no_temp_files_after_success(tmp_path: Path) -> None:
    source = create_test_epub(
        tmp_path / "source.epub", ["<p>Hello.</p>", "<p>World.</p>"]
    )
    rewrite_epub(
        source,
        tmp_path / "out.epub",
        {"OEBPS/Text/chapter01.xhtml": b"<?xml version='1.0'?><html></html>"},
    )
    assert _find_temp_files(tmp_path) == []


def test_failed_rewrite_leaves_existing_destination_untouched(
    tmp_path: Path,
) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Hello.</p>"])
    destination = tmp_path / "out.epub"
    destination.write_bytes(b"ORIGINAL-MARKER")
    # An overlay that corrupts mimetype guarantees temp validation fails.
    with pytest.raises((ValidationError, PackageError)):
        rewrite_epub(source, destination, {"mimetype": b"not-an-epub"})
    assert destination.read_bytes() == b"ORIGINAL-MARKER"
    assert _find_temp_files(tmp_path) == []


def test_rewrite_preserves_mimetype_first_and_uncompressed(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Hello.</p>"])
    out = tmp_path / "out.epub"
    rewrite_epub(source, out, {})
    with zipfile.ZipFile(out) as archive:
        infos = archive.infolist()
        first = infos[0]
    assert first.filename == "mimetype"
    assert first.compress_type == zipfile.ZIP_STORED


def test_rewrite_preserves_archive_comment_and_order(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Hello.</p>"])
    # Re-write the source with a known archive comment.
    entries: list[tuple[str, bytes, int]] = []
    with zipfile.ZipFile(source) as src:
        comment = b"test-archive-comment"
        for info in src.infolist():
            entries.append((info.filename, src.read(info.filename), info.compress_type))
    with zipfile.ZipFile(source, "w") as archive:
        archive.comment = comment
        for name, data, compress_type in entries:
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = compress_type
            archive.writestr(info, data)
    out = tmp_path / "out.epub"
    rewrite_epub(source, out, {})
    with (
        zipfile.ZipFile(source) as src,
        zipfile.ZipFile(out) as dst,
    ):
        assert src.comment == dst.comment
        assert src.namelist() == dst.namelist()
