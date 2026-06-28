from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path

import pytest

from text2epub import OutputRewriteOptions, ReplacementPlan, rebuild_epub
from text2epub.errors import PackageError, ValidationError
from text2epub.output_rewrite import (
    is_effective_rewrite,
    validate_language_tag,
)
from text2epub.package import resolve_opf_href

from .helpers import PNG_BYTES, chapter_document, create_test_epub, write_epub

# ---------------------------------------------------------------------------
# Custom EPUB builder for discovery / scope / fixed-layout / language fixtures
# ---------------------------------------------------------------------------


def build_custom_epub(
    path: Path,
    *,
    opf_path: str = "OEBPS/content.opf",
    chapters: list[tuple[str, str]],
    extra_manifest: list[dict] | None = None,
    extra_entries: dict[str, bytes] | None = None,
    extra_metadata: str = "",
    fixed_layout: bool = False,
    with_nav: bool = True,
) -> Path:
    opf_dir = posixpath.dirname(opf_path)

    manifest_lines: list[str] = []
    spine_lines: list[str] = []
    chapter_entries: list[tuple[str, bytes, int]] = []

    for index, (href_rel, body) in enumerate(chapters, start=1):
        item_id = f"chapter-{index:03d}"
        archive_name = resolve_opf_href(opf_dir, href_rel)
        manifest_lines.append(
            f'    <item id="{item_id}" href="{href_rel}" '
            f'media-type="application/xhtml+xml" />'
        )
        spine_lines.append(f'    <itemref idref="{item_id}" />')
        chapter_entries.append(
            (
                archive_name,
                chapter_document(body, title=f"Chapter {index}").encode("utf-8"),
                zipfile.ZIP_DEFLATED,
            )
        )

    for extra in extra_manifest or []:
        props = extra.get("properties")
        prop_attr = f' properties="{props}"' if props else ""
        manifest_lines.append(
            f'    <item id="{extra["id"]}" href="{extra["href"]}" '
            f'media-type="{extra["media_type"]}"{prop_attr} />'
        )

    rendition_meta = (
        '    <meta property="rendition:layout">pre-paginated</meta>\n'
        if fixed_layout
        else ""
    )

    nav_entry: tuple[str, bytes, int] | None = None
    if with_nav:
        nav_href = "nav.xhtml"
        nav_archive = resolve_opf_href(opf_dir, nav_href)
        manifest_lines.insert(
            0,
            f'    <item id="nav" href="{nav_href}" '
            f'media-type="application/xhtml+xml" properties="nav" />',
        )
        nav_document = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops">\n'
            "<head><title>Contents</title></head>\n"
            '<body><nav epub:type="toc" id="toc"><ol></ol></nav></body>\n'
            "</html>\n"
        )
        nav_entry = (nav_archive, nav_document.encode("utf-8"), zipfile.ZIP_DEFLATED)

    content_opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="bookid" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        "  <metadata>\n"
        "    <dc:title>Fixture</dc:title>\n"
        "    <dc:language>en</dc:language>\n"
        '    <dc:identifier id="bookid">urn:uuid:fixture</dc:identifier>\n'
        f"{rendition_meta}"
        f"{extra_metadata}"
        "  </metadata>\n"
        "  <manifest>\n" + "\n".join(manifest_lines) + "\n  </manifest>\n"
        "  <spine>\n" + "\n".join(spine_lines) + "\n  </spine>\n"
        "</package>\n"
    )

    container = (
        b'<?xml version="1.0" encoding="utf-8"?>\n'
        b'<container version="1.0" '
        b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        b"  <rootfiles>\n"
        b'    <rootfile full-path="' + opf_path.encode("utf-8") + b'" '
        b'media-type="application/oebps-package+xml" />\n'
        b"  </rootfiles>\n"
        b"</container>\n"
    )

    entries: list[tuple[str, bytes, int]] = [
        ("mimetype", b"application/epub+zip", zipfile.ZIP_STORED),
        ("META-INF/container.xml", container, zipfile.ZIP_DEFLATED),
        (opf_path, content_opf.encode("utf-8"), zipfile.ZIP_DEFLATED),
    ]
    if nav_entry is not None:
        entries.append(nav_entry)
    entries.extend(chapter_entries)
    for name, data in (extra_entries or {}).items():
        entries.append((name, data, zipfile.ZIP_DEFLATED))

    write_epub(path, entries)
    return path


def _read_out(out: Path, name: str) -> str:
    with zipfile.ZipFile(out) as archive:
        return archive.read(name).decode("utf-8")


def override_entry(epub_path: Path, archive_name: str, new_bytes: bytes) -> None:
    """Rewrite an existing EPUB member's payload bytes, preserving order."""
    entries: list[tuple[str, bytes, int]] = []
    with zipfile.ZipFile(epub_path) as src:
        for info in src.infolist():
            payload = (
                new_bytes if info.filename == archive_name else src.read(info.filename)
            )
            entries.append((info.filename, payload, info.compress_type))
    write_epub(epub_path, entries)


OPF_PKG = "application/oebps-package+xml"


def _container_bytes(rootfiles: list[tuple[str, str]]) -> bytes:
    """Build a META-INF/container.xml for a list of (full-path, media-type)."""
    parts = [
        b'<?xml version="1.0" encoding="utf-8"?>\n',
        b'<container version="1.0" '
        b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n',
        b"  <rootfiles>\n",
    ]
    for full_path, media_type in rootfiles:
        parts.append(
            b'    <rootfile full-path="'
            + full_path.encode()
            + b'" media-type="'
            + media_type.encode()
            + b'" />\n'
        )
    parts.append(b"  </rootfiles>\n</container>\n")
    return b"".join(parts)


def _simple_package_opf(
    *,
    include_language: bool = True,
    href: str = "c.xhtml",
) -> str:
    """Minimal OPF package with one XHTML manifest item and spine entry."""
    language = "<dc:language>en</dc:language>" if include_language else ""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<metadata><dc:title>X</dc:title>"
        + language
        + '<dc:identifier id="b">x</dc:identifier></metadata>'
        '<manifest><item id="c" href="' + href + '" '
        'media-type="application/xhtml+xml"/></manifest>'
        '<spine><itemref idref="c"/></spine></package>'
    )


# ---------------------------------------------------------------------------
# Effective-rewrite detection and option validation
# ---------------------------------------------------------------------------


def test_default_options_are_not_an_effective_rewrite() -> None:
    assert is_effective_rewrite(OutputRewriteOptions()) is False


def test_empty_css_is_an_effective_rewrite(tmp_path: Path) -> None:
    assert is_effective_rewrite(OutputRewriteOptions(css_text="")) is True


def test_patch_flags_make_an_effective_rewrite() -> None:
    assert (
        is_effective_rewrite(
            OutputRewriteOptions(language="es", patch_content_language=True)
        )
        is True
    )


def test_language_tag_validation_rejects_bad_tags() -> None:
    for bad in ["", "   ", "en_US", "en US", "en--US", "a" * 12]:
        with pytest.raises(ValidationError):
            validate_language_tag(bad)


def test_language_tag_validation_accepts_good_tags() -> None:
    for good in ["en", "es", "pt-BR", "zh-Hans", "en-US", "x1"]:
        validate_language_tag(good)


def test_patch_without_language_fails(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Hi.</p>"])
    with pytest.raises(ValidationError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                output_rewrite=OutputRewriteOptions(patch_content_language=True),
            ),
            tmp_path / "out.epub",
        )


def test_body_language_requires_content_language(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Hi.</p>"])
    with pytest.raises(ValidationError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                output_rewrite=OutputRewriteOptions(
                    language="es",
                    patch_body_language=True,
                ),
            ),
            tmp_path / "out.epub",
        )


def test_invalid_style_id_fails(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Hi.</p>"])
    with pytest.raises(ValidationError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                output_rewrite=OutputRewriteOptions(css_text="p {}", style_id="1bad"),
            ),
            tmp_path / "out.epub",
        )


# ---------------------------------------------------------------------------
# Package discovery
# ---------------------------------------------------------------------------


def test_opf_discovery_works_outside_default_path(tmp_path: Path) -> None:
    source = build_custom_epub(
        tmp_path / "source.epub",
        opf_path="content/package.opf",
        chapters=[("chapters/c01.xhtml", "<p>Hello.</p>")],
    )
    out = tmp_path / "out.epub"
    report = rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="fr",
                patch_package_language=True,
            ),
        ),
        out,
    )
    assert report.output_rewrite is not None
    assert report.output_rewrite.opf_path == "content/package.opf"
    assert "<dc:language>fr</dc:language>" in _read_out(out, "content/package.opf")


def test_missing_rootfile_fails(tmp_path: Path) -> None:
    source = tmp_path / "source.epub"
    container = _container_bytes([("OEBPS/content.opf", "application/xml")])
    write_epub(
        source,
        [
            ("mimetype", b"application/epub+zip", zipfile.ZIP_STORED),
            ("META-INF/container.xml", container, zipfile.ZIP_DEFLATED),
            (
                "OEBPS/content.opf",
                b"<?xml version='1.0'?><package/>",
                zipfile.ZIP_DEFLATED,
            ),
        ],
    )
    with pytest.raises(PackageError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                output_rewrite=OutputRewriteOptions(
                    language="es", patch_package_language=True
                ),
            ),
            tmp_path / "out.epub",
        )


def test_multiple_rootfiles_warns_and_selects_first(tmp_path: Path) -> None:
    opf = _simple_package_opf()
    container = _container_bytes([("OEBPS/a.opf", OPF_PKG), ("OEBPS/b.opf", OPF_PKG)])
    source = tmp_path / "source.epub"
    write_epub(
        source,
        [
            ("mimetype", b"application/epub+zip", zipfile.ZIP_STORED),
            ("META-INF/container.xml", container, zipfile.ZIP_DEFLATED),
            ("OEBPS/a.opf", opf.encode(), zipfile.ZIP_DEFLATED),
            ("OEBPS/b.opf", opf.encode(), zipfile.ZIP_DEFLATED),
            (
                "OEBPS/c.xhtml",
                chapter_document("<p>x</p>").encode(),
                zipfile.ZIP_DEFLATED,
            ),
        ],
    )
    report = rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="es", patch_package_language=True
            ),
        ),
        tmp_path / "out.epub",
    )
    assert report.output_rewrite is not None
    assert report.output_rewrite.opf_path == "OEBPS/a.opf"
    assert any("multiple OPF rootfiles" in w for w in report.output_rewrite.warnings)


# ---------------------------------------------------------------------------
# Content scopes
# ---------------------------------------------------------------------------


def test_spine_scope_targets_only_spine_xhtml(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>One.</p>", "<p>Two.</p>"])
    report = rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="es",
                patch_content_language=True,
                content_scope="spine",
                css_text="p {}",
            ),
        ),
        tmp_path / "out.epub",
    )
    assert report.output_rewrite is not None
    assert sorted(report.output_rewrite.targeted_content_entries) == [
        "OEBPS/Text/chapter01.xhtml",
        "OEBPS/Text/chapter02.xhtml",
    ]
    assert "OEBPS/nav.xhtml" not in report.output_rewrite.css_injected_entries


def test_spine_and_navigation_scope_includes_nav(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>One.</p>"])
    report = rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="es",
                patch_content_language=True,
                content_scope="spine-and-navigation",
            ),
        ),
        tmp_path / "out.epub",
    )
    assert report.output_rewrite is not None
    assert sorted(report.output_rewrite.targeted_content_entries) == [
        "OEBPS/Text/chapter01.xhtml",
        "OEBPS/nav.xhtml",
    ]


def test_replacement_manifest_scope_requires_manifest(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>One.</p>"])
    with pytest.raises(ValidationError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                output_rewrite=OutputRewriteOptions(
                    language="es",
                    patch_content_language=True,
                    content_scope="replacement-manifest",
                ),
            ),
            tmp_path / "out.epub",
        )


def test_explicit_scope_resolves_opf_relative_hrefs(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>One.</p>", "<p>Two.</p>"])
    report = rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="es",
                patch_content_language=True,
                content_scope="explicit",
                content_hrefs=["Text/chapter02.xhtml"],
            ),
        ),
        tmp_path / "out.epub",
    )
    assert report.output_rewrite is not None
    assert report.output_rewrite.targeted_content_entries == [
        "OEBPS/Text/chapter02.xhtml"
    ]
    out = _read_out(tmp_path / "out.epub", "OEBPS/Text/chapter02.xhtml")
    assert 'lang="es"' in out


def test_explicit_scope_rejects_traversal(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>One.</p>"])
    with pytest.raises(ValidationError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                output_rewrite=OutputRewriteOptions(
                    language="es",
                    patch_content_language=True,
                    content_scope="explicit",
                    content_hrefs=["../../etc/passwd"],
                ),
            ),
            tmp_path / "out.epub",
        )


def test_explicit_scope_rejects_duplicates(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>One.</p>"])
    with pytest.raises(ValidationError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                output_rewrite=OutputRewriteOptions(
                    language="es",
                    patch_content_language=True,
                    content_scope="explicit",
                    content_hrefs=[
                        "Text/chapter01.xhtml",
                        "OEBPS/Text/chapter01.xhtml",
                    ],
                ),
            ),
            tmp_path / "out.epub",
        )


def test_explicit_scope_rejects_missing_target(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>One.</p>"])
    with pytest.raises(ValidationError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                output_rewrite=OutputRewriteOptions(
                    language="es",
                    patch_content_language=True,
                    content_scope="explicit",
                    content_hrefs=["Text/missing.xhtml"],
                ),
            ),
            tmp_path / "out.epub",
        )


def test_explicit_scope_rejects_non_xhtml_target(tmp_path: Path) -> None:
    source = create_test_epub(
        tmp_path / "source.epub",
        ["<p>One.</p>"],
        extra_entries={"OEBPS/Images/cover.png": PNG_BYTES},
    )
    with pytest.raises(ValidationError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                output_rewrite=OutputRewriteOptions(
                    language="es",
                    patch_content_language=True,
                    content_scope="explicit",
                    content_hrefs=["Images/cover.png"],
                ),
            ),
            tmp_path / "out.epub",
        )


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_explicit_scope_rejects_archive_duplicate_ambiguity(tmp_path: Path) -> None:
    # Hand-build an archive with a duplicate member name to create ambiguity.
    source = tmp_path / "source.epub"
    opf = _simple_package_opf()
    container = _container_bytes([("OEBPS/content.opf", OPF_PKG)])
    body = chapter_document("<p>x</p>").encode()
    write_epub(
        source,
        [
            ("mimetype", b"application/epub+zip", zipfile.ZIP_STORED),
            ("META-INF/container.xml", container, zipfile.ZIP_DEFLATED),
            ("OEBPS/content.opf", opf.encode(), zipfile.ZIP_DEFLATED),
            ("OEBPS/c.xhtml", body, zipfile.ZIP_DEFLATED),
            ("OEBPS/c.xhtml", body, zipfile.ZIP_DEFLATED),  # duplicate member
        ],
    )
    with pytest.raises(ValidationError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                output_rewrite=OutputRewriteOptions(
                    language="es",
                    patch_content_language=True,
                    content_scope="explicit",
                    content_hrefs=["OEBPS/c.xhtml"],
                ),
            ),
            tmp_path / "out.epub",
        )


# ---------------------------------------------------------------------------
# Language rewriting
# ---------------------------------------------------------------------------


def test_language_only_rewrite_with_zero_replacements(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Hello.</p>"])
    out = tmp_path / "out.epub"
    report = rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="es",
                patch_package_language=True,
                patch_content_language=True,
            ),
        ),
        out,
    )
    assert report.replacement_count == 0
    assert report.output_rewrite is not None
    assert report.output_rewrite.old_primary_language == "en"
    assert report.output_rewrite.new_primary_language == "es"
    opf = _read_out(out, "OEBPS/content.opf")
    assert "<dc:language>es</dc:language>" in opf
    ch = _read_out(out, "OEBPS/Text/chapter01.xhtml")
    assert 'lang="es"' in ch and 'xml:lang="es"' in ch


def test_opf_adds_language_when_none_exists(tmp_path: Path) -> None:
    opf_no_lang = _simple_package_opf(include_language=False)
    source = tmp_path / "source.epub"
    write_epub(
        source,
        [
            ("mimetype", b"application/epub+zip", zipfile.ZIP_STORED),
            (
                "META-INF/container.xml",
                _container_bytes([("OEBPS/content.opf", OPF_PKG)]),
                zipfile.ZIP_DEFLATED,
            ),
            ("OEBPS/content.opf", opf_no_lang.encode(), zipfile.ZIP_DEFLATED),
            (
                "OEBPS/c.xhtml",
                chapter_document("<p>x</p>").encode(),
                zipfile.ZIP_DEFLATED,
            ),
        ],
    )
    out = tmp_path / "out.epub"
    rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="de", patch_package_language=True
            ),
        ),
        out,
    )
    opf = _read_out(out, "OEBPS/content.opf")
    assert opf.count("<dc:language>") == 1
    assert "<dc:language>de</dc:language>" in opf


def test_multiple_dc_language_preserves_extras(tmp_path: Path) -> None:
    source = build_custom_epub(
        tmp_path / "source.epub",
        chapters=[("c.xhtml", "<p>x</p>")],
        extra_metadata=(
            "    <dc:language>fr</dc:language>\n    <dc:language>en-US</dc:language>\n"
        ),
    )
    out = tmp_path / "out.epub"
    rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="es", patch_package_language=True
            ),
        ),
        out,
    )
    opf = _read_out(out, "OEBPS/content.opf")
    # first updated to es, fr and en-US preserved
    assert "<dc:language>es</dc:language>" in opf
    assert "<dc:language>fr</dc:language>" in opf
    assert "<dc:language>en-US</dc:language>" in opf
    # original primary 'en' is replaced (not duplicated)
    assert opf.count("<dc:language>en</dc:language>") == 0


def test_root_language_preserves_descendant_attributes(tmp_path: Path) -> None:
    body = '<p>English.</p><p lang="fr" xml:lang="fr">Francais.</p>'
    source = build_custom_epub(
        tmp_path / "source.epub",
        chapters=[("c.xhtml", body)],
    )
    out = tmp_path / "out.epub"
    rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="es", patch_content_language=True
            ),
        ),
        out,
    )
    ch = _read_out(out, "OEBPS/c.xhtml")
    assert "<html" in ch and 'lang="es"' in ch
    # descendant foreign-language attributes survive
    assert 'lang="fr"' in ch and 'xml:lang="fr"' in ch


def test_body_language_patching(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Hi.</p>"])
    out = tmp_path / "out.epub"
    rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="es",
                patch_content_language=True,
                patch_body_language=True,
            ),
        ),
        out,
    )
    ch = _read_out(out, "OEBPS/Text/chapter01.xhtml")
    assert "<body" in ch
    body_start = ch.index("<body")
    body_tag = ch[body_start : ch.index(">", body_start) + 1]
    assert 'lang="es"' in body_tag and 'xml:lang="es"' in body_tag


# ---------------------------------------------------------------------------
# CSS rewriting
# ---------------------------------------------------------------------------


def test_css_inserts_style_into_head(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Hi.</p>"])
    out = tmp_path / "out.epub"
    rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(css_text="p { color: red; }"),
        ),
        out,
    )
    ch = _read_out(out, "OEBPS/Text/chapter01.xhtml")
    assert 'id="text2epub-output-policy"' in ch
    assert "color: red" in ch


def test_css_replaces_existing_matching_style(tmp_path: Path) -> None:
    body = "<p>Hi.</p>"
    custom_head = (
        "<head><title>T</title>"
        '<style id="text2epub-output-policy" type="text/css">old {}</style>'
        "</head>"
    )
    doc = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">\n'
        f"{custom_head}\n<body>\n{body}\n</body>\n</html>\n"
    )
    source = tmp_path / "source.epub"
    write_epub(
        source,
        [
            ("mimetype", b"application/epub+zip", zipfile.ZIP_STORED),
            (
                "META-INF/container.xml",
                _container_bytes([("OEBPS/content.opf", OPF_PKG)]),
                zipfile.ZIP_DEFLATED,
            ),
            (
                "OEBPS/content.opf",
                _simple_package_opf(href="Text/c.xhtml").encode(),
                zipfile.ZIP_DEFLATED,
            ),
            ("OEBPS/Text/c.xhtml", doc.encode(), zipfile.ZIP_DEFLATED),
        ],
    )
    out = tmp_path / "out.epub"
    rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(css_text="new { color: blue; }"),
        ),
        out,
    )
    ch = _read_out(out, "OEBPS/Text/c.xhtml")
    assert "new { color: blue; }" in ch
    assert "old {}" not in ch
    assert ch.count('id="text2epub-output-policy"') == 1


def test_css_empty_string_removes_matching_style(tmp_path: Path) -> None:
    body = "<p>Hi.</p>"
    custom_head = (
        "<head><title>T</title>"
        '<style id="text2epub-output-policy" type="text/css">old {}</style>'
        "</head>"
    )
    doc = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">\n'
        f"{custom_head}\n<body>\n{body}\n</body>\n</html>\n"
    )
    source = build_custom_epub(
        tmp_path / "source.epub",
        chapters=[("Text/c.xhtml", "<p>placeholder</p>")],
    )
    override_entry(source, "OEBPS/Text/c.xhtml", doc.encode())

    out = tmp_path / "out.epub"
    rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(css_text=""),
        ),
        out,
    )
    ch = _read_out(out, "OEBPS/Text/c.xhtml")
    assert 'id="text2epub-output-policy"' not in ch
    assert "old {}" not in ch


def test_css_duplicate_matching_styles_fails(tmp_path: Path) -> None:
    body = "<p>Hi.</p>"
    custom_head = (
        "<head><title>T</title>"
        '<style id="text2epub-output-policy" type="text/css">a {}</style>'
        '<style id="text2epub-output-policy" type="text/css">b {}</style>'
        "</head>"
    )
    doc = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">\n'
        f"{custom_head}\n<body>\n{body}\n</body>\n</html>\n"
    )
    source = build_custom_epub(tmp_path / "source.epub", chapters=[("c.xhtml", body)])
    override_entry(source, "OEBPS/c.xhtml", doc.encode())

    with pytest.raises(ValidationError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                output_rewrite=OutputRewriteOptions(css_text="x {}"),
            ),
            tmp_path / "out.epub",
        )


def test_css_missing_head_fails(tmp_path: Path) -> None:
    doc = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">\n'
        "<body><p>Hi.</p></body>\n</html>\n"
    )
    source = build_custom_epub(
        tmp_path / "source.epub", chapters=[("c.xhtml", "<p>x</p>")]
    )
    override_entry(source, "OEBPS/c.xhtml", doc.encode())
    with pytest.raises(ValidationError):
        rebuild_epub(
            ReplacementPlan(
                source_epub=source,
                output_rewrite=OutputRewriteOptions(css_text="p {}"),
            ),
            tmp_path / "out.epub",
        )


# ---------------------------------------------------------------------------
# Idempotency and fixed layout
# ---------------------------------------------------------------------------


def test_reapplying_identical_options_is_idempotent(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Hi.</p>"])
    first = tmp_path / "first.epub"
    second = tmp_path / "second.epub"
    options = OutputRewriteOptions(
        language="es",
        patch_package_language=True,
        patch_content_language=True,
        css_text="p { color: red; }",
    )
    rebuild_epub(ReplacementPlan(source_epub=source, output_rewrite=options), first)
    report2 = rebuild_epub(
        ReplacementPlan(source_epub=first, output_rewrite=options), second
    )
    assert report2.changed_entries == []
    assert report2.output_rewrite is not None
    assert report2.output_rewrite.applied is True
    # byte-identical second pass
    assert first.read_bytes() == second.read_bytes()


def test_fixed_layout_css_skipped_by_default(tmp_path: Path) -> None:
    source = build_custom_epub(
        tmp_path / "source.epub",
        chapters=[("c.xhtml", "<p>Hi.</p>")],
        fixed_layout=True,
        with_nav=False,
    )
    out = tmp_path / "out.epub"
    report = rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="es",
                patch_content_language=True,
                css_text="p {}",
            ),
        ),
        out,
    )
    assert report.output_rewrite is not None
    assert report.output_rewrite.fixed_layout_skipped_entries == ["OEBPS/c.xhtml"]
    ch = _read_out(out, "OEBPS/c.xhtml")
    assert 'id="text2epub-output-policy"' not in ch  # css skipped
    assert 'lang="es"' in ch  # language still applied


def test_fixed_layout_css_can_be_enabled(tmp_path: Path) -> None:
    source = build_custom_epub(
        tmp_path / "source.epub",
        chapters=[("c.xhtml", "<p>Hi.</p>")],
        fixed_layout=True,
    )
    out = tmp_path / "out.epub"
    rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                css_text="p {}",
                inject_css_into_fixed_layout=True,
            ),
        ),
        out,
    )
    ch = _read_out(out, "OEBPS/c.xhtml")
    assert 'id="text2epub-output-policy"' in ch


# ---------------------------------------------------------------------------
# XML preservation and parser hardening
# ---------------------------------------------------------------------------


def test_xml_features_survive_rewrite(tmp_path: Path) -> None:
    doc = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE html>\n"
        "<!-- prolog comment -->\n"
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">\n'
        "<head><title>T</title></head>\n"
        "<?my-pi sample ?>\n"
        "<body>\n"
        "<!-- body comment -->\n"
        "<p>Inline <em>markup</em> here.</p>\n"
        '<span epub:type="noteref">note</span>\n'
        "</body>\n"
        "</html>\n"
    )
    source = build_custom_epub(
        tmp_path / "source.epub", chapters=[("c.xhtml", "<p>x</p>")]
    )
    override_entry(source, "OEBPS/c.xhtml", doc.encode())

    out = tmp_path / "out.epub"
    rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="es", patch_content_language=True
            ),
        ),
        out,
    )
    ch = _read_out(out, "OEBPS/c.xhtml")
    assert ch.startswith('<?xml version="1.0"') or ch.startswith("<?xml")
    assert "encoding=" in ch.split("?>")[0]
    assert "<!DOCTYPE html>" in ch
    assert "prolog comment" in ch
    assert "<?my-pi" in ch and "sample" in ch
    assert "body comment" in ch
    assert "<em>markup</em>" in ch
    assert 'xmlns:epub="http://www.idpf.org/2007/ops"' in ch
    assert 'epub:type="noteref"' in ch


def test_external_entity_and_network_resolution_disabled(tmp_path: Path) -> None:
    secret = "SECRET-LEAK-MARKER-12345"
    secret_path = tmp_path / "secret.txt"
    secret_path.write_text(secret)
    doc = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE html [\n"
        f'  <!ENTITY xxe SYSTEM "file://{secret_path}">\n'
        "]>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">\n'
        "<head><title>T</title></head>\n"
        "<body><p>start [&xxe;] end</p></body>\n"
        "</html>\n"
    )
    source = build_custom_epub(
        tmp_path / "source.epub", chapters=[("c.xhtml", "<p>x</p>")]
    )
    override_entry(source, "OEBPS/c.xhtml", doc.encode())

    out = tmp_path / "out.epub"
    rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="es", patch_content_language=True
            ),
        ),
        out,
    )
    ch = _read_out(out, "OEBPS/c.xhtml")
    assert secret not in ch
    assert "&xxe;" in ch  # entity reference preserved, not expanded


def test_unchanged_entries_keep_original_payload(tmp_path: Path) -> None:
    source = create_test_epub(
        tmp_path / "source.epub",
        ["<p>One.</p>", "<p>Two.</p>"],
        extra_entries={"OEBPS/Images/cover.png": PNG_BYTES},
    )
    out = tmp_path / "out.epub"
    rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(
                language="es",
                patch_content_language=True,
                content_scope="explicit",
                content_hrefs=["OEBPS/Text/chapter01.xhtml"],
            ),
        ),
        out,
    )
    with (
        zipfile.ZipFile(source) as src,
        zipfile.ZipFile(out) as dst,
    ):
        # chapter02 and the image are untouched -> identical payload bytes
        assert src.read("OEBPS/Text/chapter02.xhtml") == dst.read(
            "OEBPS/Text/chapter02.xhtml"
        )
        assert src.read("OEBPS/Images/cover.png") == dst.read("OEBPS/Images/cover.png")
        assert src.read("mimetype") == dst.read("mimetype")


def test_effective_noop_options_report_applied_false(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Hi.</p>"])
    out = tmp_path / "out.epub"
    report = rebuild_epub(
        ReplacementPlan(
            source_epub=source,
            output_rewrite=OutputRewriteOptions(),
        ),
        out,
    )
    assert report.output_rewrite is not None
    assert report.output_rewrite.applied is False
