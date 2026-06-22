# Markdown to EPUB

The Markdown workflow renders Markdown to XHTML chapters, packages local image
assets, generates EPUB metadata files, and writes a deterministic ZIP package by
default.

## Folder schema

For general-purpose projects, keep the manuscript in a folder and name files so
sorted filenames match reading order:

```text
manuscript/
├── 00-front-matter.md
├── 01-introduction.md
├── 02-chapter.md
└── 99-appendix.md
```

The Python helper discovers direct `*.md` children and returns them in filename
order:

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

Use `discover_markdown_chapters` when you want to inspect or customize the
chapter list before building:

```python
from pathlib import Path

from text2epub import EpubMetadata, MarkdownBook, create_epub_from_markdown
from text2epub import discover_markdown_chapters

chapters = discover_markdown_chapters(Path("manuscript"))
book = MarkdownBook(metadata=EpubMetadata(title="Book"), chapters=chapters)
create_epub_from_markdown(book, Path("book.epub"))
```

## Inputs

`text2epub markdown` accepts either one Markdown file or a directory. For
directories, direct `*.md` children are sorted by filename and used as spine
order.

```bash
text2epub markdown manuscript/ -o book.epub --title "Book" --language en --title-page --toc-page --toc-page-numbers
```

The Python folder helper exposes the same default. Set `recursive=True` when you
want matching files below nested folders sorted by relative path.

## Generated title and contents pages

The EPUB package always includes the EPUB NAV document for reading-system
navigation. For book-like manuscripts you can also insert reader-visible pages
into the spine:

```python
from text2epub import BuildOptions

options = BuildOptions(
    include_title_page=True,
    include_toc_page=True,
    toc_page_numbers=True,
)
```

The generated title page uses metadata such as title, description, creators,
publisher, date, and rights. The generated contents page links to the Markdown
chapters, not to the generated front-matter pages.

`toc_page_numbers=True` writes CSS using `target-counter(attr(href), page)`. This
requests automatic page numbers from reading systems that support paged-media
counters. EPUB readers without that support keep the TOC links but omit the page
numbers.

## Front matter

The first Markdown file may include simple YAML-like front matter. Only
`key: value` lines are parsed.

```markdown
---
title: Front Matter Title
language: en
author: Ada Lovelace
publisher: Example Press
description: Short description.
rights: Copyright holder/date.
date: 2026-06-22
identifier: urn:uuid:example
---

# Chapter One
```

Explicit metadata passed through the Python API or CLI takes precedence over
front matter.

## Headings

Headings receive stable IDs generated from heading text:

```markdown
# Hello World

## Hello World
```

The rendered IDs become `hello-world` and `hello-world-2`. The first `#` heading
in each file is used as the chapter title when no explicit chapter title is set.

## Images

Local images are copied into `OEBPS/Images/` and chapter image references are
rewritten to relative package paths.

```markdown
![Cover](cover.png)
```

Remote images are rejected by default. Set `allow_remote_resources=True` in
`BuildOptions` or pass `--allow-remote-resources` to leave remote image URLs
external. External resources may not be accepted by all stores or reading
systems.

## Links and raw HTML

Raw HTML in Markdown is disabled. Links with `javascript:` URLs are rejected.
Other links are escaped during XHTML serialization.
