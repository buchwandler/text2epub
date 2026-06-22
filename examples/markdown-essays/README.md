# markdown-essays

Generates a multi-chapter EPUB entirely from Markdown. This is the high-level
`create_epub_from_markdown` workflow.

## What it demonstrates

- A book built from every `*.md` file in `chapters/`, sorted into spine order.
- A generated title page is inserted before the Markdown chapters.
- A generated reader-visible table of contents is inserted after the title page.
- The TOC page requests automatic page numbers with CSS `target-counter()`; readers that do not support paged-media counters still show normal links.
- YAML-like front matter in the first chapter drives the EPUB metadata.
- Headings get stable IDs (`on-markdown`, `a-table-of-features`).
- A local image (`assets/cover.png`) is copied into the package and rewritten to
  a relative path.
- A table, a fenced code block, a blockquote, and a link render to XHTML.
- A custom stylesheet (`style.css`) is merged with the default CSS.

## Run it

From the repository root, with `text2epub` installed:

```bash
python examples/markdown-essays/build.py
```

The package is written to `dist/essays.epub`. The builder validates the ZIP
package on the way out. To run the standalone token/package check:

```bash
text2epub validate examples/markdown-essays/dist/essays.epub
```

## Equivalent CLI

```bash
text2epub markdown examples/markdown-essays/chapters \
  -o examples/markdown-essays/dist/essays.epub
```

The CLI command above builds the Markdown chapters but does not enable the generated
title page, generated reader-visible TOC page, or custom stylesheet. The equivalent
front-matter command is:

```bash
text2epub markdown examples/markdown-essays/chapters \
  -o examples/markdown-essays/dist/essays.epub \
  --title-page --toc-page --toc-page-numbers
```

The CLI does not load a custom `css_files` stylesheet; it only applies the
built-in default CSS. Use the Python API shown in `build.py` for custom CSS.
