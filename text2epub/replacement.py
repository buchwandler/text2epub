from __future__ import annotations

import html
import json
import zipfile
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import ReplacementError, UnsafeFragmentError
from .inline_xhtml import validate_inline_fragment as validate_safe_inline_fragment
from .models import (
    OutputRewriteReport,
    Replacement,
    ReplacementPlan,
    ReplacementReport,
)
from .output_rewrite import (
    apply_output_rewrite,
    effective_noop_report,
    is_effective_rewrite,
    validate_rewrite_options,
)
from .package import (
    XHTML_MEDIA_TYPES,
    coerce_path,
    copy_epub,
    load_package_model,
    rewrite_epub,
    validate_epub_package,
)
from .validation import (
    ensure_no_unresolved_tokens,
    is_text_entry,
    sha256_bytes,
    sha256_path,
)


def rebuild_epub(plan: ReplacementPlan, output_path: Path | str) -> ReplacementReport:
    source_epub = coerce_path(plan.source_epub)
    output = coerce_path(output_path)
    validate_epub_package(source_epub)

    rewrite_options = plan.output_rewrite
    effective_rewrite = (
        rewrite_options is not None and is_effective_rewrite(rewrite_options)
    )

    # Validate option combinations before any manifest or package IO so that
    # scope/flag errors surface as ValidationError rather than manifest errors.
    if effective_rewrite:
        assert rewrite_options is not None
        validate_rewrite_options(
            rewrite_options,
            manifest_available=plan.extraction_manifest is not None,
        )

    needs_manifest = bool(plan.replacements) or (
        effective_rewrite
        and rewrite_options is not None
        and rewrite_options.content_scope == "replacement-manifest"
    )

    with zipfile.ZipFile(source_epub) as archive:
        source_names = archive.namelist()

        manifest = None
        manifest_index: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
        manifest_hrefs: list[str] = []
        if needs_manifest:
            manifest = load_manifest(plan.extraction_manifest)
            validate_source_manifest_hash(source_epub, manifest)
            manifest_index = build_manifest_index(manifest)
            manifest_hrefs = unique_manifest_xhtml_hrefs(manifest)
        detect_duplicate_blocks(plan.replacements)


        # Fast path: no block replacements and no effective rewrite.
        if not plan.replacements and not effective_rewrite:
            copy_epub(source_epub, output)
            report = ReplacementReport(
                output_path=output,
                changed_entries=[],
                unchanged_entries=source_names,
                replacement_count=0,
                unresolved_token_count=0,
            )
            if rewrite_options is not None:
                report.output_rewrite = effective_noop_report(
                    load_package_model(archive)
                )
            return report

        package_model = None
        if effective_rewrite:
            package_model = load_package_model(archive)

        # Block replacements -> byte overlays keyed by archive name.
        overlays = _compute_block_overlays(
            archive, plan.replacements, manifest_index
        )

        # Output rewrite composes on top of block overlays via an overlay-aware reader.
        rewrite_report: OutputRewriteReport | None = None
        if effective_rewrite:
            assert package_model is not None
            assert rewrite_options is not None

            def entry_reader(name: str) -> bytes:
                if name in overlays:
                    return overlays[name]
                return archive.read(name)

            rewrite_overlays, rewrite_report = apply_output_rewrite(
                archive,
                package_model,
                rewrite_options,
                entry_reader,
                manifest_hrefs=manifest_hrefs,
            )
            overlays.update(rewrite_overlays)
        elif rewrite_options is not None:
            assert package_model is not None
            rewrite_report = effective_noop_report(package_model)

        # No effective change -> byte-identical copy.
        if not overlays:
            copy_epub(source_epub, output)
            return ReplacementReport(
                output_path=output,
                changed_entries=[],
                unchanged_entries=source_names,
                replacement_count=len(plan.replacements),
                unresolved_token_count=0,
                output_rewrite=rewrite_report,
            )

        # Scan final changed text for unresolved tokens before writing.
        changed_text_entries: dict[str, str] = {}
        for name, data in overlays.items():
            if is_text_entry(name):
                changed_text_entries[name] = data.decode("utf-8")
        unresolved_token_count = 0
        if plan.options.fail_on_unresolved_tokens:
            unresolved_token_count = ensure_no_unresolved_tokens(
                changed_text_entries,
                plan.options.unresolved_token_patterns,
            )

        rewrite_epub(source_epub, output, overlays)
        changed_entries = [name for name in source_names if name in overlays]
        unchanged_entries = [
            name for name in source_names if name not in overlays
        ]
        return ReplacementReport(
            output_path=output,
            changed_entries=changed_entries,
            unchanged_entries=unchanged_entries,
            replacement_count=len(plan.replacements),
            unresolved_token_count=unresolved_token_count,
            output_rewrite=rewrite_report,
        )



def _compute_block_overlays(
    archive: zipfile.ZipFile,
    replacements: list[Replacement],
    manifest_index: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> dict[str, bytes]:
    """Apply block replacements and return archive-keyed byte overlays."""
    raw_text_cache: dict[str, str] = {}
    entry_changes: dict[str, list[tuple[int, int, str, str]]] = defaultdict(list)

    for replacement in replacements:
        entry_info, block = manifest_index.get(replacement.block_id, (None, None))
        if entry_info is None or block is None:
            raise ReplacementError(
                f"Replacement block {replacement.block_id} was not found in "
                "the extraction manifest."
            )
        href = str(entry_info["href"])
        if href not in archive.namelist():
            raise ReplacementError(
                f"Replacement block {replacement.block_id} targets missing ZIP "
                f"entry {href!r}."
            )
        source_bytes = archive.read(href)
        validate_entry_hash(href, source_bytes, entry_info, replacement.block_id)
        entry_text = raw_text_cache.get(href)
        if entry_text is None:
            entry_text = source_bytes.decode("utf-8")
            raw_text_cache[href] = entry_text

        start, end = block_range(block, replacement.block_id)
        if end > len(entry_text):
            raise ReplacementError(
                f"Replacement block {replacement.block_id} points outside ZIP "
                f"entry {href!r}."
            )
        source_fragment = entry_text[start:end]
        expected_fragment = expected_source_fragment(block)
        if expected_fragment is not None and source_fragment != expected_fragment:
            raise ReplacementError(
                f"Replacement block {replacement.block_id} in {href!r} no longer "
                "matches the extraction manifest source fragment."
            )
        block_text = str(block.get("text", ""))
        if (
            replacement.expected_source is not None
            and replacement.expected_source != block_text
        ):
            raise ReplacementError(
                f"Replacement block {replacement.block_id} expected source "
                f"{replacement.expected_source!r}, but the manifest recorded "
                f"{block_text!r}."
            )

        replacement_mode = str(block.get("replacement_mode", "whole_block_body"))
        rendered = render_replacement_text(
            replacement,
            block_id=replacement.block_id,
            mode=replacement_mode,
        )
        if is_identity_replacement(replacement, block_text, source_fragment, rendered):
            continue
        entry_changes[href].append((start, end, rendered, replacement.block_id))

    overlays: dict[str, bytes] = {}
    for href, changes in entry_changes.items():
        original = raw_text_cache[href]
        validate_non_overlapping_ranges(href, changes)
        updated = apply_changes(original, changes)
        overlays[href] = updated.encode("utf-8")
    return overlays

def load_manifest(
    manifest: Path | str | Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if manifest is None:
        raise ReplacementError(
            "Replacement plans with replacements require an extraction manifest."
        )
    if isinstance(manifest, Mapping):
        payload = manifest
    else:
        payload = json.loads(coerce_path(manifest).read_text(encoding="utf-8"))
    schema_version = payload.get("schema_version")
    if schema_version not in (None, 1):
        raise ReplacementError(
            f"Unsupported extraction manifest schema version {schema_version!r}."
        )
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ReplacementError("Extraction manifest must contain an entries list.")
    return payload


def unique_manifest_xhtml_hrefs(manifest: Mapping[str, Any]) -> list[str]:
    """Return unique XHTML entry hrefs from an extraction manifest, in order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for entry in manifest["entries"]:
        media_type = str(entry.get("media_type", "")).strip().lower()
        if media_type not in XHTML_MEDIA_TYPES:
            continue
        href = str(entry.get("href", ""))
        if href and href not in seen:
            seen.add(href)
            ordered.append(href)
    return ordered


def validate_source_manifest_hash(
    source_epub: Path, manifest: Mapping[str, Any]
) -> None:
    expected_sha = manifest.get("source_sha256")
    if expected_sha and sha256_path(source_epub) != expected_sha:
        raise ReplacementError(
            f"Source EPUB {source_epub} does not match extraction manifest "
            "source_sha256."
        )


def build_manifest_index(
    manifest: Mapping[str, Any],
) -> dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]]:
    indexed: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for entry in manifest["entries"]:
        blocks = entry.get("blocks", [])
        for block in blocks:
            block_id = block.get("block_id")
            if not block_id:
                raise ReplacementError("Manifest block is missing block_id.")
            normalized_block_id = str(block_id)
            if normalized_block_id in indexed:
                raise ReplacementError(
                    f"Manifest block {normalized_block_id} appears more than once."
                )
            indexed[normalized_block_id] = (entry, block)
    return indexed


def detect_duplicate_blocks(replacements: list[Replacement]) -> None:
    seen: set[str] = set()
    for replacement in replacements:
        if replacement.block_id in seen:
            raise ReplacementError(
                f"Replacement block {replacement.block_id} was supplied more than once."
            )
        seen.add(replacement.block_id)


def validate_entry_hash(
    href: str,
    source_bytes: bytes,
    entry_info: Mapping[str, Any],
    block_id: str,
) -> None:
    expected_sha = entry_info.get("raw_sha256")
    if expected_sha and sha256_bytes(source_bytes) != expected_sha:
        raise ReplacementError(
            f"Replacement block {block_id} targets {href!r}, but the source entry "
            "hash does not match the extraction manifest."
        )


def block_range(block: Mapping[str, Any], block_id: str) -> tuple[int, int]:
    replacement_mode = str(block.get("replacement_mode", "whole_block_body"))
    if replacement_mode == "whole_block_body":
        start = block.get("body_source_start", block.get("source_start"))
        end = block.get("body_source_end", block.get("source_end"))
    elif replacement_mode == "text_node_sequence":
        start = block.get("source_start")
        end = block.get("source_end")
    else:
        raise ReplacementError(
            f"Replacement block {block_id} uses unsupported replacement mode "
            f"{replacement_mode!r}."
        )
    if not isinstance(start, int) or not isinstance(end, int):
        raise ReplacementError(
            f"Replacement block {block_id} is missing valid source offsets."
        )
    if start < 0 or end < start:
        raise ReplacementError(
            f"Replacement block {block_id} has invalid range {start}:{end}."
        )
    return start, end


def expected_source_fragment(block: Mapping[str, Any]) -> str | None:
    source_fragment = block.get("source_fragment")
    if isinstance(source_fragment, str):
        return source_fragment
    replacement_mode = str(block.get("replacement_mode", "whole_block_body"))
    if replacement_mode == "text_node_sequence":
        text = block.get("text")
        if isinstance(text, str):
            return text
    return None


def render_replacement_text(
    replacement: Replacement,
    *,
    block_id: str,
    mode: str,
) -> str:
    if replacement.allow_inline_xhtml:
        validate_inline_fragment(replacement.text, block_id=block_id, mode=mode)
        return replacement.text
    return html.escape(replacement.text, quote=False)


def validate_inline_fragment(fragment: str, *, block_id: str, mode: str) -> None:
    try:
        validate_safe_inline_fragment(
            fragment,
            context=f"Replacement block {block_id}",
            mode=mode,
        )
    except UnsafeFragmentError:
        raise


def is_identity_replacement(
    replacement: Replacement,
    block_text: str,
    source_fragment: str,
    rendered: str,
) -> bool:
    return (
        rendered == source_fragment
        or replacement.text == block_text
        or (
            replacement.expected_source is not None
            and replacement.text == replacement.expected_source
        )
    )


def validate_non_overlapping_ranges(
    href: str, changes: list[tuple[int, int, str, str]]
) -> None:
    ordered = sorted(changes, key=lambda item: item[0])
    previous_end = -1
    for start, end, _, block_id in ordered:
        if start < previous_end:
            raise ReplacementError(
                f"Replacement block {block_id} overlaps another replacement in "
                f"ZIP entry {href!r}."
            )
        previous_end = end


def apply_changes(original: str, changes: list[tuple[int, int, str, str]]) -> str:
    updated = original
    for start, end, replacement_text, _ in sorted(
        changes, key=lambda item: item[0], reverse=True
    ):
        updated = updated[:start] + replacement_text + updated[end:]
    return updated
