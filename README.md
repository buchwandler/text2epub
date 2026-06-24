[![PyPI - Version](https://img.shields.io/pypi/v/text2epub)](https://pypi.org/project/text2epub/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/text2epub)
![PyPI - Downloads](https://img.shields.io/pypi/dm/text2epub)
[![codecov](https://codecov.io/gh/holgern/text2epub/graph/badge.svg?token=qd3VBCOQZd)](https://codecov.io/gh/holgern/text2epub)

# text2epub

`text2epub` is a typed Python library and CLI for creating EPUB files from
plain-text writing workflows. It is useful when you keep a manuscript as one
Markdown file, as a folder of numbered Markdown chapters, or as already-rendered
XHTML chapter fragments.

It also includes a conservative rebuild workflow for tools such as `booktx` that
need to apply validated text replacements to an existing EPUB without rewriting
unchanged package entries.

## Features

- create new EPUBs from one Markdown file
- create new EPUBs from a folder of ordered Markdown files
- discover chapters from filename-based manuscript conventions
- generate XHTML, OPF, NAV, NCX, CSS, and deterministic ZIP output
- optionally add a generated title page and reader-visible contents page
- request automatic TOC page numbers with CSS `target-counter()` for readers that support paged-media counters
- package local image assets referenced by Markdown
- optionally preserve safe inline XHTML in Markdown, such as `<em>`, `<strong>`, `<span>`, and `<a>`
- support YAML-like front matter for common EPUB metadata
- build EPUBs from explicit XHTML chapter bodies
- safely rebuild existing EPUBs from extraction manifests and replacement plans
- byte-identical no-op and identity rebuild paths
- basic EPUB package validation and unresolved-token checks

## Installation

```bash
uv pip install text2epub
```

For development from a checkout:

```bash
python -m pip install -e .
```

## Folder-based Markdown workflow

A simple manuscript folder can use filenames to define reading order:

```text
manuscript/
├── 00-front-matter.md
├── 01-introduction.md
├── 02-method.md
└── 03-appendix.md
```

The first file may contain front matter for book metadata:

```markdown
---
title: Example Book
language: en
author: Ada Lovelace
publisher: Example Press
date: 2026-06-22
---

# Introduction

This becomes the first EPUB chapter.
```

Build it from Python with the convenience API:

```python
from pathlib import Path

from text2epub import BuildOptions, create_epub_from_markdown_folder

create_epub_from_markdown_folder(
    Path("manuscript"),
    Path("book.epub"),
    options=BuildOptions(
        include_title_page=True,
        include_toc_page=True,
        toc_page_numbers=True,
    ),
)
```

Or build the same folder from the CLI:

```bash
text2epub markdown manuscript/ -o book.epub --title-page --toc-page --toc-page-numbers
```

## Explicit Python API

Use `create_epub_from_markdown_files` when your application already controls the
chapter list and order:

```python
from pathlib import Path

from text2epub import BuildOptions, EpubMetadata, create_epub_from_markdown_files

create_epub_from_markdown_files(
    [Path("01-introduction.md"), Path("02-body.md")],
    Path("book.epub"),
    metadata=EpubMetadata(title="Example Book", language="en"),
    options=BuildOptions(include_title_page=True, include_toc_page=True),
)
```

Use the lower-level model API when you need per-chapter ids, hrefs, titles, or
custom build options:

```python
from pathlib import Path

from text2epub import (
    BuildOptions,
    EpubMetadata,
    MarkdownBook,
    MarkdownChapter,
    create_epub_from_markdown,
)

book = MarkdownBook(
    metadata=EpubMetadata(title="Example Book", language="en"),
    chapters=[MarkdownChapter(path=Path("chapter-01.md"))],
    options=BuildOptions(deterministic=True),
)
create_epub_from_markdown(book, Path("book.epub"))
```


## Safe inline XHTML in Markdown

Raw HTML is escaped by default. When your source text comes from `epub2text`
structured fragment export or another trusted pipeline, enable safe inline XHTML
to preserve phrasing markup inside Markdown paragraphs:

```markdown
This keeps <em>emphasis</em> and <strong>strength</strong>.
```

```python
from text2epub import BuildOptions

options = BuildOptions(allow_inline_xhtml=True)
```

```bash
text2epub markdown manuscript/ -o book.epub --allow-inline-xhtml
```

Only safe inline tags are accepted. Raw block HTML and unsafe attributes such as
`onclick` are rejected.

## Rebuild API

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
            )
        ],
    ),
    Path("rebuilt.epub"),
)
print(report.changed_entries)
```

## CLI

```bash
text2epub markdown INPUT.md -o OUTPUT.epub
text2epub markdown CHAPTER_DIR -o OUTPUT.epub --title "Book" --language en
text2epub markdown CHAPTER_DIR -o OUTPUT.epub --title-page --toc-page --toc-page-numbers
text2epub markdown CHAPTER_DIR -o OUTPUT.epub --allow-inline-xhtml
text2epub rebuild SOURCE.epub MANIFEST.json REPLACEMENTS.json -o OUTPUT.epub
text2epub validate OUTPUT.epub
text2epub version
```

## Documentation

The Sphinx documentation lives under `docs/`. Build it locally with:

```bash
python -m pip install -e ".[docs]"
python -m sphinx -b html docs docs/_build/html
```

Start with `docs/index.md` for the user guide and `docs/release-checklist.md` for release validation.

## Page numbers in EPUB readers

EPUB files do not contain universal static page numbers. When `toc_page_numbers=True`
or `--toc-page-numbers` is used, `text2epub` writes CSS using `target-counter()`
on the generated contents page. Reading systems with paged-media counter support
can fill those numbers automatically; other readers still display the linked
contents entries without page numbers.
