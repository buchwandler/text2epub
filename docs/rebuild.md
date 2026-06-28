# Safe EPUB rebuilds

The rebuild workflow applies text replacements to an existing EPUB using an extraction manifest. It is designed for automated translation or post-processing systems that must preserve source package entries whenever possible.

## Replacement plan

```python
from pathlib import Path

from text2epub import Replacement, ReplacementPlan, rebuild_epub

report = rebuild_epub(
    ReplacementPlan(
        source_epub=Path("source.epub"),
        extraction_manifest=Path("manifest.json"),
        replacements=[
            Replacement(
                block_id="spine-0001:block-000001",
                text="Translated paragraph.",
                expected_source="Original paragraph.",
                allow_inline_xhtml=False,
            )
        ],
    ),
    Path("rebuilt.epub"),
)

print(report.changed_entries)
```

## Manifest shape

The extraction manifest can be supplied as a mapping or JSON file. The expected schema is intentionally small:

```json
{
  "schema_version": 1,
  "source_sha256": "sha256-of-source-epub",
  "entries": [
    {
      "href": "OEBPS/Text/chapter01.xhtml",
      "media_type": "application/xhtml+xml",
      "spine_index": 1,
      "raw_sha256": "sha256-of-entry-bytes",
      "blocks": [
        {
          "block_id": "spine-0001:block-000001",
          "text": "Original paragraph.",
          "source_start": 128,
          "source_end": 147,
          "replacement_mode": "text_node_sequence"
        }
      ]
    }
  ]
}
```

`source_sha256` and `raw_sha256` are optional, but strongly recommended. When present, they protect against applying replacements to the wrong source file or a stale ZIP entry.

## Replacement modes

`text_node_sequence` replaces the byte-decoded text range from `source_start` to `source_end`.

`whole_block_body` replaces `body_source_start` to `body_source_end` when present, otherwise it falls back to `source_start` and `source_end`. This mode supports safe inline XHTML fragments.

## Safety checks

A rebuild fails when:

- the source EPUB fails basic package validation,
- the manifest source hash does not match the source EPUB,
- a replacement references an unknown or duplicate block,
- source offsets are missing, invalid, outside the entry, or overlapping,
- the current source fragment differs from the manifest fragment,
- a replacement leaks configured internal placeholder tokens,
- an inline XHTML fragment contains forbidden tags, attributes, event handlers, JavaScript links, or malformed XML.

No-op plans and identity replacements copy the source EPUB without rewriting entries. Rebuilds do not operate in place; use a distinct output path.

## Output rewrite (language and CSS)

`rebuild_epub` accepts an optional `OutputRewriteOptions` through
`ReplacementPlan.output_rewrite`. It is the supported way to update
publication-level metadata when replacement text changes the publication
language, and to inject deterministic, caller-owned CSS. text2epub does not
choose a target language or interpret injected CSS - those concerns stay with
the caller.

```python
from text2epub import OutputRewriteOptions, ReplacementPlan, rebuild_epub

report = rebuild_epub(
    ReplacementPlan(
        source_epub="source.epub",
        output_rewrite=OutputRewriteOptions(
            language="es",
            patch_package_language=True,
            patch_content_language=True,
            css_text="p { hyphens: auto; }",
        ),
    ),
    "rebuilt.epub",
)
print(report.output_rewrite)
```

When `output_rewrite` is `None`, or the options request no effective change
(no language patch flag set and `css_text is None`), the rebuild preserves
current copy and byte-identity behavior exactly.

### Language

- `language` is required when any of `patch_package_language`,
  `patch_content_language`, or `patch_body_language` is enabled.
- `patch_package_language` updates the primary OPF `dc:language` (adding one if
  none exists, preserving additional distinct `dc:language` values).
- `patch_content_language` sets the root `html@lang` and `html@xml:lang`.
- `patch_body_language` additionally sets `body@lang`/`body@xml:lang` and is
  invalid unless content language patching is enabled.
- Existing descendant language attributes (for example a `lang="fr"` quote) are
  preserved.
- Language tags are validated as BCP-47-style: empty, whitespace-only,
  underscore-form, and otherwise syntactically invalid tags are rejected.

### CSS

`css_text` is caller-owned CSS. text2epub validates that it is text and injects
it as a single `<style id="text2epub-output-policy" type="text/css">` element.

- `style_id` must be a valid XML/HTML id token.
- Zero matching styles insert one at the end of `<head>`; one matching style
  replaces its text; more than one is an error rather than an arbitrary repair.
- A missing `<head>` is an error for a targeted XHTML document.
- `css_text=None` means do not inspect or change generated styles. An empty
  string is an explicit request to remove an existing matching style.
- Applying identical options twice produces one style and no semantic change
  (idempotent).
- CSS is skipped for fixed-layout content unless
  `inject_css_into_fixed_layout=True`. Language patching still applies to
  fixed-layout XHTML.

text2epub does **not** promise that injected CSS overrides source or reader
styles; rendered behavior depends on the reading system and is out of scope.

### Content targeting

`content_scope` selects which XHTML documents the rewrite applies to:

- `replacement-manifest` uses the unique XHTML hrefs from the extraction
  manifest (requires a manifest even when there are no replacements).
- `spine` uses XHTML manifest items referenced by the spine, in spine order.
- `spine-and-navigation` (default) uses spine items plus the navigation
  document, deduplicated in archive order.
- `explicit` uses `content_hrefs`, resolved relative to the OPF unless they
  already name an exact archive member. Empty lists, duplicate or traversal
  hrefs, hrefs absent from the manifest, non-XHTML targets, and archive
  duplicate-name ambiguity are rejected.

The OPF is located through `META-INF/container.xml`, so rebuilt sources are not
required to keep their package at `OEBPS/content.opf`.

### Reporting and atomic output

When a non-`None` rewrite object is supplied, `ReplacementReport.output_rewrite`
is populated with an `OutputRewriteReport` (with `applied=False` for an
effective no-op). `ReplacementReport.changed_entries` is the archive-order
union of block-replacement, OPF, content-language, and CSS changes;
`replacement_count` continues to count requested block replacements only.

Output publication is atomic: a sibling temporary EPUB is written in the
destination directory, validated, and only then moved into place. On any
failure the temporary file is removed and an existing destination is left
untouched.
