# text2epub documentation

`text2epub` is a typed Python package for creating EPUB files from text-first
workflows and for safely rebuilding existing EPUB packages from structured
extraction manifests.

The general-purpose creation workflow supports single Markdown files, folders of
ordered Markdown chapters, explicit chapter lists, and already-rendered XHTML
bodies. The rebuild workflow remains conservative for automation tools such as
`booktx`, where preserving unchanged ZIP entries and failing closed on stale
inputs matters.

```{toctree}
:maxdepth: 2
:caption: User guide

getting-started
markdown
rebuild
cli
api
release-checklist
```

## Supported workflows

- Generate a new EPUB from one Markdown file.
- Generate a new EPUB from a folder of Markdown chapters sorted by filename.
- Add generated title and reader-visible contents pages to Markdown or XHTML builds.
- Request automatic TOC page numbers for reading systems that support CSS paged-media counters.
- Discover chapters from manuscript naming schemes such as `00-front-matter.md`,
  `01-introduction.md`, and `02-chapter.md`.
- Build an EPUB from already-rendered XHTML chapter bodies.
- Rebuild an existing EPUB from a manifest plus replacement JSON.
- Validate the basic ZIP/package structure and scan text entries for unresolved
  internal tokens.

## Design priorities

1. Make the common Markdown-to-EPUB path easy for general Python users.
2. Keep output deterministic by default so builds are reproducible.
3. Preserve source EPUB bytes for no-op and identity rebuilds.
4. Fail closed when rebuild inputs are stale or unsafe.
5. Keep generated front matter optional so scripts can choose plain chapter-only output or book-like output.
6. Keep the public API small enough for automation tools and scripts.

## Limits

`text2epub validate` is a package-level smoke check. It does not replace
EPUBCheck and does not perform full EPUB specification validation of OPF, NAV,
NCX, XHTML, CSS, or remote-resource policy.
