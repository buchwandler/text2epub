from __future__ import annotations

from pathlib import Path

from text2epub import (
    BuildOptions,
    OutputRewriteOptions,
    OutputRewriteReport,
    Replacement,
    ReplacementPlan,
    ReplacementReport,
)


def test_output_rewrite_options_defaults() -> None:
    options = OutputRewriteOptions()
    assert options.language is None
    assert options.patch_package_language is False
    assert options.patch_content_language is False
    assert options.patch_body_language is False
    assert options.css_text is None
    assert options.style_id == "text2epub-output-policy"
    assert options.content_scope == "spine-and-navigation"
    assert options.content_hrefs == []
    assert options.inject_css_into_fixed_layout is False


def test_output_rewrite_report_defaults() -> None:
    report = OutputRewriteReport()
    assert report.applied is False
    assert report.opf_path is None
    assert report.changed_entries == []
    assert report.targeted_content_entries == []
    assert report.language_patched_entries == []
    assert report.css_injected_entries == []
    assert report.fixed_layout_skipped_entries == []
    assert report.old_primary_language is None
    assert report.new_primary_language is None
    assert report.warnings == []


def test_replacement_plan_remains_valid_without_output_rewrite() -> None:
    plan = ReplacementPlan(
        source_epub=Path("source.epub"),
        replacements=[Replacement(block_id="b1", text="hi")],
    )
    assert plan.output_rewrite is None
    assert isinstance(plan.options, BuildOptions)


def test_replacement_plan_accepts_output_rewrite() -> None:
    plan = ReplacementPlan(
        source_epub=Path("source.epub"),
        replacements=[],
        output_rewrite=OutputRewriteOptions(
            language="es",
            patch_package_language=True,
            patch_content_language=True,
            css_text="p { color: red; }",
        ),
    )
    assert plan.output_rewrite is not None
    assert plan.output_rewrite.language == "es"
    assert plan.output_rewrite.patch_package_language is True
    assert plan.output_rewrite.patch_content_language is True


def test_replacement_report_remains_valid_without_output_rewrite() -> None:
    report = ReplacementReport(
        output_path=Path("out.epub"),
        changed_entries=[],
        unchanged_entries=["mimetype"],
        replacement_count=0,
        unresolved_token_count=0,
    )
    assert report.output_rewrite is None
    assert report.warnings == []


def test_replacement_report_accepts_output_rewrite() -> None:
    nested = OutputRewriteReport(
        applied=True,
        opf_path="OEBPS/content.opf",
        changed_entries=["OEBPS/content.opf"],
        language_patched_entries=["OEBPS/Text/chapter01.xhtml"],
    )
    report = ReplacementReport(
        output_path=Path("out.epub"),
        changed_entries=["OEBPS/content.opf", "OEBPS/Text/chapter01.xhtml"],
        unchanged_entries=["mimetype"],
        replacement_count=0,
        unresolved_token_count=0,
        output_rewrite=nested,
    )
    assert report.output_rewrite is not None
    assert report.output_rewrite.applied is True
    assert report.output_rewrite.opf_path == "OEBPS/content.opf"


def test_replacement_report_positional_construction_stays_compatible() -> None:
    # Positional construction with the original five fields must keep working
    # even though output_rewrite was added with a default.
    report = ReplacementReport(
        Path("out.epub"), ["a"], ["b"], 1, 0
    )
    assert report.output_path == Path("out.epub")
    assert report.changed_entries == ["a"]
    assert report.unchanged_entries == ["b"]
    assert report.replacement_count == 1
    assert report.unresolved_token_count == 0
    assert report.output_rewrite is None
