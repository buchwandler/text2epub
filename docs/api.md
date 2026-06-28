# Python API reference

This page documents the stable public API exposed from `text2epub.__init__`.

## Models

```{eval-rst}
.. autoclass:: text2epub.Author
   :members:

.. autoclass:: text2epub.EpubMetadata
   :members:

.. autoclass:: text2epub.BuildOptions
   :members:

.. autoclass:: text2epub.MarkdownBook
   :members:

.. autoclass:: text2epub.MarkdownChapter
   :members:

.. autoclass:: text2epub.XhtmlChapter
   :members:

.. autoclass:: text2epub.Replacement
   :members:

.. autoclass:: text2epub.ReplacementPlan
   :members:

.. autoclass:: text2epub.ReplacementReport
   :members:

.. autoclass:: text2epub.OutputRewriteOptions
   :members:

.. autoclass:: text2epub.OutputRewriteReport
   :members:
```

## Markdown builders

Use these helpers for general-purpose Markdown projects.

```{eval-rst}
.. autofunction:: text2epub.discover_markdown_chapters

.. autofunction:: text2epub.create_epub_from_markdown_folder

.. autofunction:: text2epub.create_epub_from_markdown_files

.. autofunction:: text2epub.create_epub_from_markdown
```

## XHTML builder

```{eval-rst}
.. autofunction:: text2epub.create_epub
```

## Rebuilds

```{eval-rst}
.. autofunction:: text2epub.rebuild_epub
```

## Exceptions

```{eval-rst}
.. automodule:: text2epub.errors
   :members:
```
