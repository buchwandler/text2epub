# rebuild-translation

Safely rebuilds an existing EPUB by applying text replacements through a
`ReplacementPlan`. This is the package-preserving workflow that `booktx` and
automated translation pipelines build on.

## What it demonstrates

- A source EPUB generated from `source/chapter-01.md`.
- An extraction manifest built in-process with byte offsets and `source_sha256`
  / `raw_sha256` guards.
- Two replacement modes against the same chapter:
  - `text_node_sequence` with `allow_inline_xhtml=False` for a plain-text
    translation (special characters are escaped).
  - `text_node_sequence` with `allow_inline_xhtml=True` for a fragment that adds
    `<em>` emphasis.
- A no-op plan (no replacements) that copies the source EPUB byte for byte.
- A language-only output rewrite (`OutputRewriteOptions`) that patches the OPF
  and XHTML language to `es` with zero block replacements.
- A language-plus-CSS output rewrite that also injects caller-supplied CSS.
  text2epub injects the CSS verbatim and does not guarantee reader rendering.
- The `ReplacementReport` fields: `changed_entries`, `replacement_count`,
  `unresolved_token_count`, and the nested `output_rewrite` report.

## Run it

From the repository root, with `text2epub` installed:

```bash
python examples/rebuild-translation/build.py
```

Outputs land in `dist/`:

- `source.epub` - the generated input.
- `manifest.json` - the extraction manifest written to disk.
- `translated.epub` - the rebuilt output.
- `noop.epub` - a byte-identical copy of the source.
- `language-only.epub` - publication language rewritten to `es`.
- `language-and-css.epub` - language rewritten plus caller-supplied CSS injected.

## Equivalent CLI

After running the script once to produce `source.epub` and `manifest.json`:

```bash
text2epub rebuild \
  examples/rebuild-translation/dist/source.epub \
  examples/rebuild-translation/dist/manifest.json \
  examples/rebuild-translation/replacements.json \
  -o examples/rebuild-translation/dist/translated.epub
```

`replacements.json` mirrors the replacements applied by `build.py`.

## Safety notes

- Rebuilds never operate in place. Always write to a distinct output path.
- `expected_source` makes a replacement fail if the source text no longer
  matches what the manifest recorded.
- Replacements that leak placeholder tokens such as `__TAG_001__` are rejected
  unless you pass `fail_on_unresolved_tokens=False`.
