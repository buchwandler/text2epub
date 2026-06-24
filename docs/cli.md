# Command-line interface

## Version

```bash
text2epub version
```

Prints the package version reported by `text2epub._version`.

## Build from Markdown

```bash
text2epub markdown INPUT.md -o OUTPUT.epub
text2epub markdown CHAPTER_DIR -o OUTPUT.epub --title "Book" --language en
text2epub markdown CHAPTER_DIR -o OUTPUT.epub --title-page --toc-page --toc-page-numbers
text2epub markdown CHAPTER_DIR -o OUTPUT.epub --allow-inline-xhtml
```

When `CHAPTER_DIR` is a directory, direct `*.md` children are sorted by filename
and used as spine order. This supports manuscript folders such as:

```text
chapters/
├── 00-front-matter.md
├── 01-introduction.md
└── 02-chapter.md
```

Options:

- `--title`, `--language`, `--creator`, `--identifier`, `--publisher`, `--description`, `--rights`, `--date`: metadata fields.
- `--no-ncx`: omit the EPUB 2 NCX table of contents file.
- `--non-deterministic`: use fresh UUID/timestamps instead of deterministic output.
- `--allow-remote-resources`: allow remote image URLs to remain external.
- `--allow-inline-xhtml`: preserve safe inline XHTML such as `<em>`, `<strong>`, `<span>`, and `<a>` in Markdown text. Raw block XHTML and unsafe attributes are rejected.
- `--title-page`: insert a generated reader-visible title page before the Markdown chapters.
- `--toc-page`: insert a generated reader-visible table of contents page after the title page, or first when no title page is requested.
- `--toc-page-numbers`: request automatic TOC page numbers with CSS `target-counter()` on the generated TOC page. Unsupported readers still show linked TOC entries.
- `--json`: print a machine-readable result.

## Rebuild an EPUB

```bash
text2epub rebuild SOURCE.epub MANIFEST.json REPLACEMENTS.json -o OUTPUT.epub
```

The replacements file contains a `replacements` array:

```json
{
  "replacements": [
    {
      "block_id": "spine-0001:block-000001",
      "text": "Updated text.",
      "expected_source": "Original text.",
      "allow_inline_xhtml": false
    }
  ]
}
```

Options:

- `--allow-unresolved-tokens`: disable unresolved-token failure for rebuild output.
- `--json`: print the replacement report as JSON.

## Validate an EPUB

```bash
text2epub validate OUTPUT.epub
text2epub validate OUTPUT.epub --json
```

Validation checks ZIP readability, the EPUB `mimetype` entry,
`META-INF/container.xml`, and unresolved-token patterns in text entries.
