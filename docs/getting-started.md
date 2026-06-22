# Getting started

## Install for development

```bash
python -m pip install -e .
python -m pip install -e ".[dev]"
```

Install the documentation dependencies when building the Sphinx site:

```bash
python -m pip install -e ".[docs]"
```

## Create an EPUB from a folder

Create a folder whose Markdown filenames define reading order:

```text
manuscript/
├── 00-front-matter.md
├── 01-introduction.md
└── 02-chapter.md
```

The first file may include simple front matter:

```markdown
---
title: Example Book
language: en
author: Ada Lovelace
---

# Introduction

Hello world.
```

Build the EPUB from Python:

```python
from pathlib import Path

from text2epub import create_epub_from_markdown_folder

create_epub_from_markdown_folder(
    Path("manuscript"),
    Path("example.epub"),
)
```

Or use the CLI:

```bash
text2epub markdown manuscript/ -o example.epub
```

## Create an EPUB from one Markdown file

Create a Markdown chapter:

```markdown
# Chapter One

Hello world.
```

Build the EPUB from Python:

```python
from pathlib import Path

from text2epub import EpubMetadata, create_epub_from_markdown_files

create_epub_from_markdown_files(
    [Path("chapter-01.md")],
    Path("example.epub"),
    metadata=EpubMetadata(title="Example Book", language="en"),
)
```

Or use the CLI:

```bash
text2epub markdown chapter-01.md -o example.epub --title "Example Book" --language en
```

## Validate output

```bash
text2epub validate example.epub
```

A successful response confirms that the archive has the expected EPUB ZIP basics
and that known unresolved internal tokens were not found in text entries. Run
EPUBCheck separately before publication.
