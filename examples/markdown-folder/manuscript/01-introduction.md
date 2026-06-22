# Introduction

Each Markdown file becomes one EPUB chapter. Direct `*.md` children of the
folder are sorted by filename, so prefix the files with numbers to control
the spine order.

## What this folder shows

- YAML-like front matter drives the EPUB metadata.
- The first `#` heading in each file becomes the chapter title.
- Lists, links, and code blocks render to XHTML.
