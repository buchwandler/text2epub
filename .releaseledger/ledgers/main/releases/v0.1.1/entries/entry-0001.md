---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0001
release_version: v0.1.1
kind: added
summary: Added support for creating EPUBs from a directory of markdown files
status: accepted
audience: null
scopes: []
source_refs:
  - git:d18f212ad120cf02be62a2519846ef8b1f60f6a8
paths:
  - text2epub/builder.py
  - text2epub/cli.py
  - text2epub/markdown.py
issues: []
prs: []
sources: []
breaking: false
internal: false
order: 1
---

The markdown command now accepts a directory of .md files in addition to a single file. A new markdown-folder example demonstrates the feature.
