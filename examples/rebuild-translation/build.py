"""Safely rebuild an existing EPUB by applying text replacements.

This is the workflow used by automated translation and post-processing tools.
A source EPUB is generated, an extraction manifest is built in-process, and
then replacements are applied through a ReplacementPlan.

Run from the repository root after installing text2epub:

    python examples/rebuild-translation/build.py

Outputs:
  examples/rebuild-translation/dist/source.epub
  examples/rebuild-translation/dist/manifest.json
  examples/rebuild-translation/dist/translated.epub
  examples/rebuild-translation/dist/noop.epub
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from text2epub import (
    BuildOptions,
    EpubMetadata,
    MarkdownBook,
    MarkdownChapter,
    OutputRewriteOptions,
    Replacement,
    ReplacementPlan,
    create_epub_from_markdown,
    rebuild_epub,
)

HERE = Path(__file__).resolve().parent
SOURCE_MD = HERE / "source" / "chapter-01.md"
DIST = HERE / "dist"
SOURCE_EPUB = DIST / "source.epub"
TRANSLATED_EPUB = DIST / "translated.epub"
NOOP_EPUB = DIST / "noop.epub"
LANGUAGE_ONLY_EPUB = DIST / "language-only.epub"
LANGUAGE_CSS_EPUB = DIST / "language-and-css.epub"

# The single generated chapter lands in this ZIP entry (chapter id defaults to
# chapter-001, href Text/chapter-001.xhtml).
CHAPTER_ENTRY = "OEBPS/Text/chapter-001.xhtml"

# The two sentences that will be replaced, in document order.
SENTENCE_FOX = "The quick brown fox jumps over the lazy dog."
SENTENCE_SHELLS = "She sold sea shells by the sea shore."


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_source_epub() -> None:
    book = MarkdownBook(
        metadata=EpubMetadata(title="A Short Tale", language="en"),
        chapters=[MarkdownChapter(path=SOURCE_MD)],
        options=BuildOptions(deterministic=True),
    )
    create_epub_from_markdown(book, SOURCE_EPUB)
    print(f"Wrote source EPUB: {SOURCE_EPUB}")


def build_manifest() -> dict:
    """Build a minimal extraction manifest for the two replaceable sentences.

    source_sha256 and raw_sha256 are optional but recommended: they make the
    rebuild fail closed if the source EPUB or the target entry has changed.
    """
    with zipfile.ZipFile(SOURCE_EPUB) as archive:
        raw_bytes = archive.read(CHAPTER_ENTRY)
    text = raw_bytes.decode("utf-8")

    blocks = []
    for index, fragment in enumerate((SENTENCE_FOX, SENTENCE_SHELLS), start=1):
        start = text.index(fragment)
        blocks.append(
            {
                "block_id": f"spine-0001:block-{index:06d}",
                "text": fragment,
                "source_start": start,
                "source_end": start + len(fragment),
                "replacement_mode": "text_node_sequence",
            }
        )

    return {
        "schema_version": 1,
        "source_sha256": sha256_file(SOURCE_EPUB),
        "entries": [
            {
                "href": CHAPTER_ENTRY,
                "media_type": "application/xhtml+xml",
                "spine_index": 1,
                "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "blocks": blocks,
            }
        ],
    }


def rebuild_translated(manifest: dict) -> None:
    plan = ReplacementPlan(
        source_epub=SOURCE_EPUB,
        extraction_manifest=manifest,
        replacements=[
            # Plain-text translation: HTML special characters are escaped.
            Replacement(
                block_id="spine-0001:block-000001",
                text="El rápido zorro marrón salta sobre el perro perezoso.",
                expected_source=SENTENCE_FOX,
                allow_inline_xhtml=False,
            ),
            # Inline XHTML: emphasis is allowed inside the replacement.
            Replacement(
                block_id="spine-0001:block-000002",
                text="She sold <em>sea shells</em> by the sea shore.",
                expected_source=SENTENCE_SHELLS,
                allow_inline_xhtml=True,
            ),
        ],
        options=BuildOptions(fail_on_unresolved_tokens=True),
    )
    report = rebuild_epub(plan, TRANSLATED_EPUB)
    print(
        "Rebuild report:\n"
        f"  changed_entries={report.changed_entries}\n"
        f"  replacement_count={report.replacement_count}\n"
        f"  unresolved_token_count={report.unresolved_token_count}"
    )
    print(f"Wrote translated EPUB: {TRANSLATED_EPUB}")


def rebuild_noop() -> None:
    """An empty replacement plan copies the source EPUB byte for byte."""
    report = rebuild_epub(
        ReplacementPlan(source_epub=SOURCE_EPUB, replacements=[]),
        NOOP_EPUB,
    )
    identical = sha256_file(NOOP_EPUB) == sha256_file(SOURCE_EPUB)
    print(
        f"No-op rebuild changed_entries={report.changed_entries}; "
        f"byte-identical to source: {identical}"
    )
    print(f"Wrote no-op EPUB: {NOOP_EPUB}")


def rebuild_language_only() -> None:
    """Rewrite only the publication language, with zero block replacements.

    No extraction manifest is needed because the default content scope
    ('spine-and-navigation') does not require one.
    """
    report = rebuild_epub(
        ReplacementPlan(
            source_epub=SOURCE_EPUB,
            output_rewrite=OutputRewriteOptions(
                language="es",
                patch_package_language=True,
                patch_content_language=True,
            ),
        ),
        LANGUAGE_ONLY_EPUB,
    )
    ow = report.output_rewrite
    print(
        "Language-only rebuild:\n"
        f"  changed_entries={report.changed_entries}\n"
        f"  old_language={ow.old_primary_language if ow else None} "
        f"-> new_language={ow.new_primary_language if ow else None}"
    )
    print(f"Wrote language-only EPUB: {LANGUAGE_ONLY_EPUB}")


def rebuild_language_and_css() -> None:
    """Rewrite the language and inject caller-supplied CSS together.

    text2epub injects the CSS verbatim; it does not interpret its semantics or
    guarantee any particular rendering in a reading system.
    """
    css = "p { hyphens: auto; } body { text-align: justify; }"
    report = rebuild_epub(
        ReplacementPlan(
            source_epub=SOURCE_EPUB,
            output_rewrite=OutputRewriteOptions(
                language="es",
                patch_package_language=True,
                patch_content_language=True,
                css_text=css,
            ),
        ),
        LANGUAGE_CSS_EPUB,
    )
    ow = report.output_rewrite
    print(
        "Language+CSS rebuild:\n"
        f"  changed_entries={report.changed_entries}\n"
        f"  language_patched_entries={ow.language_patched_entries if ow else []}\n"
        f"  css_injected_entries={ow.css_injected_entries if ow else []}"
    )
    print(f"Wrote language+CSS EPUB: {LANGUAGE_CSS_EPUB}")


def main() -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    build_source_epub()
    manifest = build_manifest()
    (DIST / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    rebuild_translated(manifest)
    rebuild_noop()
    rebuild_language_only()
    rebuild_language_and_css()


if __name__ == "__main__":
    main()
