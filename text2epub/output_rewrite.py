"""Generic EPUB output rewrite engine.

This module implements the opt-in output rewrite described in the EPUB output
rewrite brief: package-language rewriting, XHTML root/body language attributes,
and caller-supplied inline CSS. It is product-agnostic: text2epub does not
choose a target language, define a hyphenation policy, or interpret the
semantics of injected CSS.

The engine is driven by :class:`text2epub.models.OutputRewriteOptions` and
operates on a :class:`text2epub.package.PackageModel` plus an overlay-aware
entry reader so that block replacements and output rewrites compose on the same
XHTML document.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Callable

from lxml import etree

from .errors import PackageError, ValidationError
from .models import OutputRewriteOptions, OutputRewriteReport
from .package import (
    DC_NS,
    OPF_NS,
    XHTML_NS,
    XML_NS,
    PackageModel,
    _parse_xml,
    href_is_traversal,
    is_xhtml_media_type,
)

__all__ = [
    "EntryReader",
    "apply_output_rewrite",
    "is_effective_rewrite",
    "resolve_content_targets",
    "validate_rewrite_options",
]

EntryReader = Callable[[str], bytes]

_BCP47_SUBTAG = re.compile(r"^[A-Za-z0-9]{1,8}$")
_XML_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9._:-]*$")
_DECLARATION_ENCODING = re.compile(
    rb"<\?xml[^>]*?encoding=[\"']([^\"']+)[\"']", re.IGNORECASE
)


def detect_declared_encoding(raw: bytes, default: str = "utf-8") -> str:
    """Return the encoding named in the XML declaration, or ``default``."""
    match = _DECLARATION_ENCODING.search(raw[:256])
    if match is None:
        return default
    return match.group(1).decode("ascii", "replace")


def has_xml_declaration(raw: bytes) -> bool:
    return raw.lstrip()[:5] == b"<?xml"


def serialize_tree(
    tree: etree._ElementTree, original_bytes: bytes, *, declared_encoding: str
) -> bytes:
    """Serialize a modified tree while preserving declaration and doctype.

    A declaration is emitted only when the original document had one, and the
    declared encoding is honoured. lxml preserves comments, processing
    instructions, namespace prefixes, and the internal doctype.
    """
    if has_xml_declaration(original_bytes):
        return etree.tostring(tree, encoding=declared_encoding, xml_declaration=True)
    return etree.tostring(tree, encoding=declared_encoding, xml_declaration=False)


def is_effective_rewrite(options: OutputRewriteOptions) -> bool:
    """Return ``True`` when ``options`` request any actual change.

    Empty-string CSS counts as an explicit request (to remove an existing
    generated style); ``None`` CSS means do not inspect generated styles.
    """
    if any(
        (
            options.patch_package_language,
            options.patch_content_language,
            options.patch_body_language,
        )
    ):
        return True
    return options.css_text is not None


def is_valid_xml_id(value: str) -> bool:
    return bool(value) and bool(_XML_ID.match(value))


def validate_language_tag(tag: str) -> None:
    """Validate a BCP-47-style language tag against basic syntax."""
    if tag is None or tag.strip() == "":
        raise ValidationError("Output rewrite language tag must not be empty.")
    if tag.strip() != tag:
        raise ValidationError(
            f"Output rewrite language tag {tag!r} must not have surrounding whitespace."
        )
    if "_" in tag:
        raise ValidationError(
            f"Output rewrite language tag {tag!r} uses underscore form; "
            "use hyphen-separated subtags."
        )
    subtags = tag.split("-")
    if not all(_BCP47_SUBTAG.match(subtag) for subtag in subtags):
        raise ValidationError(
            f"Output rewrite language tag {tag!r} is not a valid BCP-47-style tag."
        )


def validate_rewrite_options(
    options: OutputRewriteOptions, *, manifest_available: bool
) -> None:
    """Validate option combinations before the rewrite runs."""
    language_patching = (
        options.patch_package_language
        or options.patch_content_language
        or options.patch_body_language
    )
    if language_patching and not options.language:
        raise ValidationError(
            "Output rewrite language patching requires a non-empty language tag."
        )
    if options.patch_body_language and not options.patch_content_language:
        raise ValidationError(
            "patch_body_language is invalid unless patch_content_language is enabled."
        )
    if options.language is not None:
        validate_language_tag(options.language)
    if not is_valid_xml_id(options.style_id):
        raise ValidationError(
            f"Output rewrite style_id {options.style_id!r} is not a valid XML id token."
        )
    if options.content_scope == "replacement-manifest" and not manifest_available:
        raise ValidationError(
            "content_scope 'replacement-manifest' requires an extraction manifest."
        )
    if options.content_scope == "explicit" and not options.content_hrefs:
        raise ValidationError(
            "content_scope 'explicit' requires a non-empty content_hrefs list."
        )


def resolve_content_targets(
    package: PackageModel,
    options: OutputRewriteOptions,
    *,
    manifest_hrefs: list[str] | None,
    archive_name_counts: dict[str, int],
) -> list[str]:
    """Resolve the ordered set of XHTML archive entries a rewrite targets.

    The returned list is ordered by archive (ZIP member) order and de-duplicated.
    Validation failures raise :class:`ValidationError` with the offending href.
    """
    scope = options.content_scope
    candidates: list[str] = []

    if scope == "replacement-manifest":
        if not manifest_hrefs:
            raise ValidationError(
                "content_scope 'replacement-manifest' found no XHTML entries "
                "in the extraction manifest."
            )
        for href in manifest_hrefs:
            item = package.item_by_archive_name(href)
            if item is None:
                raise ValidationError(
                    f"Extraction manifest href {href!r} is not present "
                    "in the OPF manifest."
                )
            if not is_xhtml_media_type(item.media_type):
                raise ValidationError(
                    f"Extraction manifest href {href!r} is not an XHTML "
                    "manifest item."
                )
            candidates.append(href)

    elif scope == "spine":
        for item_id in package.spine_item_ids:
            item = package.manifest.get(item_id)
            if item is not None and is_xhtml_media_type(item.media_type):
                candidates.append(item.archive_name)

    elif scope == "spine-and-navigation":
        for item_id in package.spine_item_ids:
            item = package.manifest.get(item_id)
            if item is not None and is_xhtml_media_type(item.media_type):
                candidates.append(item.archive_name)
        if package.nav_item is not None:
            candidates.append(package.nav_item.archive_name)

    elif scope == "explicit":
        candidates = _resolve_explicit_targets(
            package, options.content_hrefs, archive_name_counts
        )
    else:  # pragma: no cover - Literal exhausts the options
        raise ValidationError(f"Unsupported content_scope {scope!r}.")

    ordered = _dedupe_preserve_archive_order(package, candidates)
    if not ordered:
        raise ValidationError(
            f"content_scope {scope!r} resolved to no XHTML content targets."
        )
    return ordered


def _resolve_explicit_href(package: PackageModel, href: str) -> str:
    from .package import resolve_opf_href

    cleaned = href.strip().replace("\\", "/")
    return resolve_opf_href(package.opf_dir, cleaned)


def _resolve_explicit_targets(
    package: PackageModel,
    hrefs: list[str],
    archive_name_counts: dict[str, int],
) -> list[str]:
    """Resolve and validate ``content_hrefs`` for the explicit scope."""
    resolved_list: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        if href in package._archive_names:
            resolved = href
        else:
            resolved_opf = _resolve_explicit_href(package, href)
            resolved = resolved_opf if resolved_opf in package._archive_names else href
        _validate_explicit_target(href, resolved, seen, archive_name_counts, package)
        seen.add(resolved)
        resolved_list.append(resolved)
    return resolved_list


def _validate_explicit_target(
    href: str,
    resolved: str,
    seen: set[str],
    archive_name_counts: dict[str, int],
    package: PackageModel,
) -> None:
    if href_is_traversal(resolved):
        raise ValidationError(
            f"Explicit content href {href!r} resolves outside the package "
            f"({resolved!r})."
        )
    if resolved in seen:
        raise ValidationError(
            f"Explicit content href {href!r} duplicates another resolved target."
        )
    if archive_name_counts.get(resolved, 0) > 1:
        raise ValidationError(
            f"Explicit content href {href!r} resolves to {resolved!r} which is "
            "ambiguous in the archive (duplicate ZIP member names)."
        )
    item = package.item_by_archive_name(resolved)
    if item is None:
        raise ValidationError(
            f"Explicit content href {href!r} resolves to {resolved!r} which is "
            "not in the OPF manifest."
        )
    if not is_xhtml_media_type(item.media_type):
        raise ValidationError(
            f"Explicit content href {href!r} resolves to non-XHTML target "
            f"{resolved!r}."
        )


def _dedupe_preserve_archive_order(
    package: PackageModel, candidates: list[str]
) -> list[str]:
    seen: set[str] = set()
    unique = [name for name in candidates if not (name in seen or seen.add(name))]
    return sorted(unique, key=package.archive_order)


def _patch_opf_language(
    opf_bytes: bytes, *, new_language: str, opf_path: str
) -> bytes:
    declared_encoding = detect_declared_encoding(opf_bytes)
    tree = _parse_xml(opf_bytes, context=opf_path)
    package_element = tree.getroot()
    metadata = package_element.find(f"{{{OPF_NS}}}metadata")
    if metadata is None:
        raise PackageError(f"OPF {opf_path!r} has no <metadata> element.")
    language_elements = metadata.findall(f"{{{DC_NS}}}language")
    if language_elements:
        language_elements[0].text = new_language
    else:
        language_element = etree.SubElement(metadata, f"{{{DC_NS}}}language")
        language_element.text = new_language
    return serialize_tree(tree, opf_bytes, declared_encoding=declared_encoding)


def _apply_style_to_head(
    head: etree._Element, *, style_id: str, css_text: str
) -> None:
    matching = [
        element
        for element in head.iterfind(f"{{{XHTML_NS}}}style")
        if element.get("id") == style_id
    ]
    if len(matching) > 1:
        raise ValidationError(
            f"Multiple <style id={style_id!r}> elements already exist in <head>; "
            "refusing ambiguous CSS rewrite."
        )
    if css_text == "":
        for element in matching:
            head.remove(element)
        return
    if len(matching) == 1:
        matching[0].text = css_text
        return
    style_element = etree.SubElement(head, f"{{{XHTML_NS}}}style")
    style_element.set("id", style_id)
    style_element.set("type", "text/css")
    style_element.text = css_text


def _rewrite_xhtml_entry(
    entry_bytes: bytes,
    *,
    entry_name: str,
    options: OutputRewriteOptions,
    do_content_language: bool,
    inject_css: bool,
) -> tuple[bytes | None, bool, bool]:
    """Return ``(new_bytes_or_None, did_language, did_css)`` for one XHTML entry."""
    declared_encoding = detect_declared_encoding(entry_bytes)
    tree = _parse_xml(entry_bytes, context=entry_name)
    root = tree.getroot()
    did_language = False
    did_css = False

    if do_content_language and root.tag == f"{{{XHTML_NS}}}html":
        root.set("lang", options.language)  # type: ignore[arg-type]
        root.set(f"{{{XML_NS}}}lang", options.language)  # type: ignore[arg-type]
        if options.patch_body_language:
            body = root.find(f"{{{XHTML_NS}}}body")
            if body is not None:
                body.set("lang", options.language)  # type: ignore[arg-type]
                body.set(f"{{{XML_NS}}}lang", options.language)  # type: ignore[arg-type]
        did_language = True

    if inject_css:
        head = root.find(f"{{{XHTML_NS}}}head")
        if head is None:
            raise ValidationError(
                f"XHTML entry {entry_name!r} has no <head>; cannot apply CSS style "
                f"{options.style_id!r}."
            )
        _apply_style_to_head(
            head, style_id=options.style_id, css_text=options.css_text or ""
        )
        did_css = True

    if not (did_language or did_css):
        return None, False, False

    new_bytes = serialize_tree(tree, entry_bytes, declared_encoding=declared_encoding)
    return new_bytes, did_language, did_css


def apply_output_rewrite(
    archive: zipfile.ZipFile,
    package: PackageModel,
    options: OutputRewriteOptions,
    entry_reader: EntryReader,
    *,
    manifest_hrefs: list[str] | None,
) -> tuple[dict[str, bytes], OutputRewriteReport]:
    """Apply an output rewrite and return ``(overlays, report)``.

    ``entry_reader`` must return overlay bytes for entries already changed by an
    earlier pipeline step (such as block replacements), and source bytes
    otherwise. This keeps block and output changes from discarding each other.
    """
    report = OutputRewriteReport(applied=True, opf_path=package.opf_archive_name)
    report.warnings.extend(package.warnings)
    report.old_primary_language = package.primary_language
    overlays: dict[str, bytes] = {}

    archive_name_counts: dict[str, int] = {}
    for name in package._archive_names:
        archive_name_counts[name] = archive_name_counts.get(name, 0) + 1

    if options.patch_package_language:
        opf_bytes = entry_reader(package.opf_archive_name)
        new_opf = _patch_opf_language(
            opf_bytes, new_language=options.language, opf_path=package.opf_archive_name
        )
        report.new_primary_language = options.language
        if new_opf != opf_bytes:
            overlays[package.opf_archive_name] = new_opf
            report.changed_entries.append(package.opf_archive_name)

    targets = resolve_content_targets(
        package,
        options,
        manifest_hrefs=manifest_hrefs,
        archive_name_counts=archive_name_counts,
    )
    report.targeted_content_entries = list(targets)

    do_content_language = options.patch_content_language or options.patch_body_language
    css_requested = options.css_text is not None
    inject_css = css_requested and (
        not package.is_fixed_layout or options.inject_css_into_fixed_layout
    )
    if (
        css_requested
        and package.is_fixed_layout
        and not options.inject_css_into_fixed_layout
    ):
        report.fixed_layout_skipped_entries = list(targets)
        report.warnings.append(
            "CSS injection skipped for fixed-layout publication; set "
            "inject_css_into_fixed_layout=True to override."
        )

    for entry_name in targets:
        raw = entry_reader(entry_name)
        new_bytes, did_language, did_css = _rewrite_xhtml_entry(
            raw,
            entry_name=entry_name,
            options=options,
            do_content_language=do_content_language,
            inject_css=inject_css,
        )
        if did_language:
            report.language_patched_entries.append(entry_name)
        if did_css:
            report.css_injected_entries.append(entry_name)
        if new_bytes is not None and new_bytes != raw:
            overlays[entry_name] = new_bytes
            report.changed_entries.append(entry_name)

    report.changed_entries = sorted(report.changed_entries, key=package.archive_order)
    return overlays, report


def effective_noop_report(package: PackageModel) -> OutputRewriteReport:
    """Report used when ``OutputRewriteOptions`` requests no effective change."""
    return OutputRewriteReport(
        applied=False,
        opf_path=package.opf_archive_name,
        old_primary_language=package.primary_language,
        warnings=list(package.warnings),
    )


__all__ = [
    "EntryReader",
    "apply_output_rewrite",
    "effective_noop_report",
    "is_effective_rewrite",
    "resolve_content_targets",
    "validate_language_tag",
    "validate_rewrite_options",
]
