---
title: Inline XHTML Demo
language: en
author: text2epub
publisher: Example
description: Demonstrates safe inline XHTML elements in Markdown.
rights: 2026 Example
date: 2026-06-24
identifier: urn:uuid:a1b2c3d4-e5f6-7890-abcd-ef1234567890
---

# Inline XHTML in Markdown

When `allow_inline_xhtml=True`, text2epub preserves safe phrasing markup
inside Markdown paragraphs. This is useful when your source text comes
from a structured fragment export such as `epub2text`.

## Basic formatting

This paragraph contains <em>emphasis</em> and <strong>strong emphasis</strong>.

You can also use <b>bold</b>, <i>italic</i>, <s>strikethrough</s>, and
<u>underline</u> for visual styling.

## Links and code

Read the <a href="https://www.w3.org/TR/epub-33/">EPUB specification</a>
for details. The element <code>allow_inline_xhtml</code> controls this
behavior.

## Semantic elements

The <abbr title="World Wide Web Consortium">W3C</abbr> maintains web
standards. Use <kbd>Ctrl+C</kbd> to copy text. The <mark>highlighted</mark>
text draws attention.

## Ruby annotations

<ruby>漢字<rp>(</rp><rt>かんじ</rt><rp>)</rp></ruby> demonstrates
ruby markup for East Asian text.

## Superscript and subscript

H<sub>2</sub>O is water. E = mc<sup>2</sup> is the mass-energy
equivalence formula.

## Span with class

This has a <span class="custom">styled span</span> element.

## Combined elements

<em>This is <strong>nested</strong> emphasis</em> inside a single
paragraph. Links can contain <a href="https://example.com"><em>formatted
text</em></a> too.

## Safe attributes

Elements support safe attributes like <span id="demo" class="example"
title="tooltip">id, class, and title</span>. Direction is also allowed:
<span dir="rtl">right-to-left text</span>.
