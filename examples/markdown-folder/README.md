# markdown-folder

The simplest Markdown example. The `manuscript/` folder contains only
Markdown files, no build script, no images, and no stylesheet. Build it with a
single CLI command or the folder convenience API.

## What it demonstrates

- A book built from every `*.md` file in `manuscript/`, sorted by filename into
  spine order.
- YAML-like front matter in the first file (`00-front-matter.md`) drives the
  EPUB metadata. No metadata is passed on the command line.
- The first `#` heading in each file becomes the chapter title.
- Lists, links, and code blocks render to XHTML using the built-in default CSS.

## Run it

From the repository root, with `text2epub` installed:

```bash
text2epub markdown examples/markdown-folder/manuscript \
  -o examples/markdown-folder/dist/book.epub
```

The first file supplies the title, language, and other metadata, so the CLI
needs no `--title` or `--language` flags. To override any of it, pass the
matching flag, for example `--title "Custom Title"`.

Validate the result:

```bash
text2epub validate examples/markdown-folder/dist/book.epub
```

## Equivalent Python

There is no `build.py` because the folder convenience API is one call:

```python
from pathlib import Path

from text2epub import create_epub_from_markdown_folder

create_epub_from_markdown_folder(
    Path("examples/markdown-folder/manuscript"),
    Path("examples/markdown-folder/dist/book.epub"),
)
```

## Notes

- `dist/` is gitignored. Build output is not committed; regenerate it with the
  command above.
- For a version with a custom stylesheet, a packaged image, and a Python build
  script, see [`markdown-essays`](../markdown-essays).
