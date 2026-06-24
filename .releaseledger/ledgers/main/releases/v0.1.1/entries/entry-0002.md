---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0002
release_version: v0.1.1
kind: added
summary: Added optional title page and table of contents generation
status: accepted
audience: null
scopes: []
source_refs:
  - git:9526e2ee865ce9669f0960fdbf7d1d355e7af419
paths:
  - text2epub/builder.py
  - text2epub/cli.py
  - text2epub/models.py
issues: []
prs: []
sources: []
breaking: false
internal: false
order: 2
---

New --title-page and --toc flags on the markdown command generate an EPUB title page and a table-of-contents page from chapter headings.
