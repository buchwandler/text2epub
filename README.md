[![PyPI - Version](https://img.shields.io/pypi/v/text2epub)](https://pypi.org/project/text2epub/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/text2epub)
![PyPI - Downloads](https://img.shields.io/pypi/dm/text2epub)
[![codecov](https://codecov.io/gh/holgern/text2epub/graph/badge.svg?token=qd3VBCOQZd)](https://codecov.io/gh/holgern/text2epub)

# text2epub

`text2epub` is a typed Python library for two EPUB output workflows:

1. **Safe rebuilds of existing EPUBs** from structured extraction manifests and
   validated text replacements.
2. **New EPUB creation from Markdown** with generated XHTML, OPF, NAV, NCX,
   CSS, and deterministic package output.

The primary client is `booktx`, so package-preserving rebuild behavior takes
priority over convenience features.

## Features

- byte-identical no-op and identity rebuild paths
- ZIP-level EPUB validation
- strict unresolved-token scanning for rewritten or generated text entries
- safe plain-text and inline-XHTML replacement support
- Markdown-to-EPUB generation for single-file and multi-file books
- deterministic output by default
- small public API and CLI smoke commands

## Installation

```bash
uv pip install -e .
```

## Python API

```python
from pathlib import Path

from text2epub import (
    BuildOptions,
    EpubMetadata,
    MarkdownBook,
    MarkdownChapter,
    Replacement,
    ReplacementPlan,
    create_epub_from_markdown,
    rebuild_epub,
)

book = MarkdownBook(
    metadata=EpubMetadata(title="Example Book", language="en"),
    chapters=[MarkdownChapter(path=Path("chapter-01.md"))],
    options=BuildOptions(deterministic=True),
)
create_epub_from_markdown(book, Path("book.epub"))

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
