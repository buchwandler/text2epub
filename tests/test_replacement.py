from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from text2epub import (
    OutputRewriteOptions,
    Replacement,
    ReplacementPlan,
    rebuild_epub,
)
from text2epub.errors import (
    PackageError,
    ReplacementError,
    UnsafeFragmentError,
    ValidationError,
)
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
        assert source_archive.read("OEBPS/Text/chapter02.xhtml") == out_archive.read(
            "OEBPS/Text/chapter02.xhtml"
        )
        assert source_archive.read("OEBPS/Images/cover.png") == out_archive.read(
            "OEBPS/Images/cover.png"
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


def test_duplicate_block_ids_in_manifest_fail(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Original text.</p>"])
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Original text.",
        replacement_mode="text_node_sequence",
    )
    duplicate = dict(manifest["entries"][0]["blocks"][0])
    manifest["entries"][0]["blocks"].append(duplicate)

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


def test_rebuild_refuses_in_place_output(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Original text.</p>"])

    with pytest.raises(PackageError, match="overwrite the source EPUB"):
        rebuild_epub(ReplacementPlan(source_epub=source, replacements=[]), source)


def test_block_replacement_and_output_rewrite_compose(tmp_path: Path) -> None:
    source = create_test_epub(
        tmp_path / "source.epub",
        ["<p>Original text.</p>"],
    )
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Original text.",
        replacement_mode="text_node_sequence",
    )
    out = tmp_path / "out.epub"
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
            output_rewrite=OutputRewriteOptions(
                language="es",
                patch_package_language=True,
                patch_content_language=True,
                css_text="p { color: red; }",
            ),
        ),
        out,
    )
    # The single chapter entry carries both the block replacement and the rewrite.
    assert "OEBPS/Text/chapter01.xhtml" in report.changed_entries
    assert "OEBPS/content.opf" in report.changed_entries
    with zipfile.ZipFile(out) as archive:
        ch = archive.read("OEBPS/Text/chapter01.xhtml").decode("utf-8")
        opf = archive.read("OEBPS/content.opf").decode("utf-8")
    assert "Updated text." in ch
    assert 'lang="es"' in ch
    assert 'id="text2epub-output-policy"' in ch
    assert "<dc:language>es</dc:language>" in opf


def test_metadata_only_rewrite_without_replacements_or_manifest(
    tmp_path: Path,
) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Original text.</p>"])
    out = tmp_path / "out.epub"
    report = rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="es",
                patch_package_language=True,
            ),
        ),
        out,
    )
    assert report.replacement_count == 0
    assert report.changed_entries == ["OEBPS/content.opf"]
    assert report.output_rewrite is not None
    assert report.output_rewrite.applied is True


def test_changed_entries_are_archive_ordered_union(tmp_path: Path) -> None:
    source = create_test_epub(
        tmp_path / "source.epub",
        ["<p>Original text.</p>", "<p>Keep.</p>"],
    )
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Original text.",
        replacement_mode="text_node_sequence",
    )
    out = tmp_path / "out.epub"
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
            output_rewrite=OutputRewriteOptions(
                language="es",
                patch_content_language=True,
            ),
        ),
        out,
    )
    source_order = zipfile.ZipFile(source).namelist()
    assert report.changed_entries == [
        name for name in source_order if name in set(report.changed_entries)
    ]
    # both chapter entries and nav get language; chapter01 also has the block change.
    assert set(report.changed_entries) >= {
        "OEBPS/Text/chapter01.xhtml",
        "OEBPS/Text/chapter02.xhtml",
        "OEBPS/nav.xhtml",
    }
    # replacement_count counts block replacements only.
    assert report.replacement_count == 1


def test_noop_plan_with_noop_rewrite_options_is_byte_identical(
    tmp_path: Path,
) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Original text.</p>"])
    out = tmp_path / "out.epub"
    report = rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(),
        ),
        out,
    )
    assert sha256_path(out) == sha256_path(source)
    assert report.changed_entries == []
    assert report.output_rewrite is not None
    assert report.output_rewrite.applied is False
