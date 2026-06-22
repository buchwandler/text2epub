from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from text2epub import Replacement, ReplacementPlan, rebuild_epub
from text2epub.errors import ReplacementError, UnsafeFragmentError, ValidationError
from text2epub.validation import sha256_path

from .helpers import create_manifest_for_fragment, create_test_epub, write_manifest


def test_identity_replacements_byte_identical(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Original text.</p>"])
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Original text.",
        replacement_mode="text_node_sequence",
    )
    manifest_path = write_manifest(tmp_path / "manifest.json", manifest)
    output = tmp_path / "out.epub"

    report = rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            extraction_manifest=manifest_path,
            replacements=[
                Replacement(
                    block_id="spine-0001:block-000001",
                    text="Original text.",
                )
            ],
        ),
        output,
    )

    assert sha256_path(output) == sha256_path(source)
    assert report.changed_entries == []


def test_single_text_replacement_changes_only_target_entry(tmp_path: Path) -> None:
    source = create_test_epub(
        tmp_path / "source.epub",
        ["<p>Original text.</p>", "<p>Keep me.</p>"],
        extra_entries={"OEBPS/Images/cover.png": b"png-bytes"},
    )
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Original text.",
        replacement_mode="text_node_sequence",
    )
    output = tmp_path / "out.epub"

    report = rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            extraction_manifest=manifest,
            replacements=[
                Replacement(
                    block_id="spine-0001:block-000001",
                    text="Updated text.",
                    allow_inline_xhtml=False,
                )
            ],
        ),
        output,
    )

    assert report.changed_entries == ["OEBPS/Text/chapter01.xhtml"]
    with (
        zipfile.ZipFile(source) as source_archive,
        zipfile.ZipFile(output) as out_archive,
    ):
        assert (
            source_archive.read("OEBPS/Text/chapter02.xhtml")
            == out_archive.read("OEBPS/Text/chapter02.xhtml")
        )
        assert (
            source_archive.read("OEBPS/Images/cover.png")
            == out_archive.read("OEBPS/Images/cover.png")
        )
        assert b"Updated text." in out_archive.read("OEBPS/Text/chapter01.xhtml")


def test_replacement_escapes_plain_text(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Original text.</p>"])
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Original text.",
        replacement_mode="text_node_sequence",
    )
    output = tmp_path / "out.epub"

    rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            extraction_manifest=manifest,
            replacements=[
                Replacement(
                    block_id="spine-0001:block-000001",
                    text="5 < 6 & 7",
                    allow_inline_xhtml=False,
                )
            ],
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        text = archive.read("OEBPS/Text/chapter01.xhtml").decode("utf-8")

    assert "5 &lt; 6 &amp; 7" in text


def test_replacement_allows_safe_inline_xhtml(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Old text.</p>"])
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Old text.",
        replacement_mode="whole_block_body",
    )
    output = tmp_path / "out.epub"

    rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            extraction_manifest=manifest,
            replacements=[
                Replacement(
                    block_id="spine-0001:block-000001",
                    text="<em>New</em> text.",
                )
            ],
        ),
        output,
    )

    with zipfile.ZipFile(output) as archive:
        text = archive.read("OEBPS/Text/chapter01.xhtml").decode("utf-8")

    assert "<p><em>New</em> text.</p>" in text


def test_replacement_rejects_script_fragment(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Old text.</p>"])
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Old text.",
        replacement_mode="whole_block_body",
    )

    with pytest.raises(UnsafeFragmentError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                extraction_manifest=manifest,
                replacements=[
                    Replacement(
                        block_id="spine-0001:block-000001",
                        text="<script>alert(1)</script>",
                    )
                ],
            ),
            tmp_path / "out.epub",
        )


def test_replacement_rejects_javascript_href(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Old text.</p>"])
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Old text.",
        replacement_mode="whole_block_body",
    )

    with pytest.raises(UnsafeFragmentError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                extraction_manifest=manifest,
                replacements=[
                    Replacement(
                        block_id="spine-0001:block-000001",
                        text='<a href="javascript:alert(1)">bad</a>',
                    )
                ],
            ),
            tmp_path / "out.epub",
        )


def test_expected_source_mismatch_fails(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Original text.</p>"])
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Original text.",
        replacement_mode="text_node_sequence",
    )

    with pytest.raises(ReplacementError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                extraction_manifest=manifest,
                replacements=[
                    Replacement(
                        block_id="spine-0001:block-000001",
                        text="Updated text.",
                        expected_source="Different text.",
                    )
                ],
            ),
            tmp_path / "out.epub",
        )


def test_source_entry_hash_mismatch_fails(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Original text.</p>"])
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Original text.",
        replacement_mode="text_node_sequence",
    )
    manifest["entries"][0]["raw_sha256"] = "not-the-right-hash"

    with pytest.raises(ReplacementError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                extraction_manifest=manifest,
                replacements=[
                    Replacement(
                        block_id="spine-0001:block-000001",
                        text="Updated text.",
                    )
                ],
            ),
            tmp_path / "out.epub",
        )


def test_unknown_block_id_fails(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Original text.</p>"])
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Original text.",
        replacement_mode="text_node_sequence",
    )

    with pytest.raises(ReplacementError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                extraction_manifest=manifest,
                replacements=[Replacement(block_id="missing", text="Updated text.")],
            ),
            tmp_path / "out.epub",
        )


def test_leaked_booktx_tokens_fail(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Original text.</p>"])
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Original text.",
        replacement_mode="text_node_sequence",
    )

    with pytest.raises(ValidationError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                extraction_manifest=manifest,
                replacements=[
                    Replacement(
                        block_id="spine-0001:block-000001",
                        text="Hello __TAG_001__.",
                    )
                ],
            ),
            tmp_path / "out.epub",
        )
