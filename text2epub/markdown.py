from __future__ import annotations

import mimetypes
import posixpath
import re
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from lxml import etree
from lxml import html as lxml_html
from markdown_it import MarkdownIt

from .errors import BuildError, UnsafeFragmentError
from .inline_xhtml import (
    ALLOWED_INLINE_TAGS,
    attribute_name,
)
from .inline_xhtml import (
    validate_inline_fragment as validate_safe_inline_fragment,
)
from .models import (
    BuildOptions,
    EpubMetadata,
    MarkdownBook,
    MarkdownChapter,
    XhtmlChapter,
)


@dataclass(slots=True)
class RenderedAsset:
    href: str
    media_type: str
    data: bytes


@dataclass(slots=True)
class RenderedMarkdownBook:
    metadata: EpubMetadata
    chapters: list[XhtmlChapter]
    options: BuildOptions
    assets: list[RenderedAsset]


def discover_markdown_chapters(
    input_path: Path | str,
    *,
    pattern: str = "*.md",
    recursive: bool = False,
) -> list[MarkdownChapter]:
    """Discover Markdown chapters from a file or folder.

    Files are returned in filename order, which makes naming schemes such as
    ``00-front-matter.md``, ``01-introduction.md`` and ``02-chapter.md`` a
    stable way to control EPUB spine order.

    Args:
        input_path: A Markdown file or a directory containing Markdown files.
        pattern: Glob pattern used when ``input_path`` is a directory.
        recursive: Use recursive directory discovery with ``Path.rglob``.

    Returns:
        Markdown chapters ready to pass to ``MarkdownBook``.

    Raises:
        BuildError: If the input does not exist or no matching Markdown files
            are found.
    """

    raw_input = str(input_path)
    path = Path(input_path)
    if path.is_file():
        return [MarkdownChapter(path=path)]
    if path.is_dir():
        iterator = path.rglob(pattern) if recursive else path.glob(pattern)
        chapter_paths = sorted(
            (candidate for candidate in iterator if candidate.is_file()),
            key=lambda candidate: candidate.relative_to(path).as_posix(),
        )
        if not chapter_paths:
            raise BuildError(
                f"Markdown directory {path} does not contain files matching "
                f"{pattern!r}."
            )
        return [MarkdownChapter(path=chapter_path) for chapter_path in chapter_paths]
    if is_remote_resource(raw_input):
        raise BuildError(
            f"Markdown input {raw_input!r} must be a local file or directory."
        )
    raise BuildError(f"Markdown input {path} does not exist.")


def prepare_markdown_book(book: MarkdownBook) -> RenderedMarkdownBook:
    if not book.chapters:
        raise BuildError("MarkdownBook requires at least one chapter.")

    first_front_matter: dict[str, str] = {}
    asset_registry: dict[Path, RenderedAsset] = {}
    rendered_chapters: list[XhtmlChapter] = []

    for index, chapter in enumerate(book.chapters, start=1):
        chapter_path = chapter.path
        source_text = chapter_path.read_text(encoding="utf-8")
        front_matter, markdown_body = split_front_matter(source_text)
        if index == 1:
            first_front_matter = front_matter
        chapter_id = chapter.id or f"chapter-{index:03d}"
        chapter_href = chapter.href or f"Text/{chapter_id}.xhtml"
        body_xhtml, discovered_title = render_markdown_body(
            markdown_body,
            chapter_path=chapter_path,
            chapter_href=chapter_href,
            asset_registry=asset_registry,
            allow_remote_resources=book.options.allow_remote_resources,
            allow_inline_xhtml=book.options.allow_inline_xhtml,
        )
        chapter_title = (
            chapter.title
            or front_matter.get("title")
            or discovered_title
            or _path_title(chapter_path)
        )
        rendered_chapters.append(
            XhtmlChapter(
                id=chapter_id,
                href=chapter_href,
                title=chapter_title,
                body_xhtml=body_xhtml,
            )
        )

    metadata = merge_metadata(book.metadata, first_front_matter)
    if not metadata.title:
        metadata = replace(metadata, title=rendered_chapters[0].title)

    return RenderedMarkdownBook(
        metadata=metadata,
        chapters=rendered_chapters,
        options=book.options,
        assets=list(asset_registry.values()),
    )


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            raw_front_matter = lines[1:index]
            body = "\n".join(lines[index + 1 :])
            return _parse_front_matter(raw_front_matter), body
    return {}, text


def render_markdown_body(
    markdown_text: str,
    *,
    chapter_path: Path,
    chapter_href: str,
    asset_registry: dict[Path, RenderedAsset],
    allow_remote_resources: bool,
    allow_inline_xhtml: bool,
) -> tuple[str, str | None]:
    parser = markdown_parser(allow_inline_xhtml=allow_inline_xhtml)
    if allow_inline_xhtml:
        validate_raw_xhtml_tokens(
            markdown_text, parser=parser, chapter_path=chapter_path
        )
    rendered_html = parser.render(markdown_text)
    root = lxml_html.fragment_fromstring(
        rendered_html or "<p></p>", create_parent="div"
    )
    slug_counts: dict[str, int] = {}
    discovered_title: str | None = None

    for element in root.iter():
        local_name = _local_name(element.tag)
        if local_name is None:
            continue
        if re.fullmatch(r"h[1-6]", local_name):
            heading_text = " ".join(element.itertext()).strip()
            if not heading_text:
                heading_text = "section"
            heading_id = unique_slug(heading_text, slug_counts)
            element.set("id", heading_id)
            if discovered_title is None and local_name == "h1":
                discovered_title = heading_text
            continue
        if local_name == "img":
            src = element.get("src")
            if not src:
                continue
            if is_remote_resource(src):
                if not allow_remote_resources:
                    raise BuildError(
                        f"Chapter {chapter_path} references remote image {src!r}, "
                        "which is disabled by default."
                    )
                continue
            asset_path = (chapter_path.parent / src).resolve()
            if not asset_path.exists():
                raise BuildError(
                    f"Chapter {chapter_path} references missing image {asset_path}."
                )
            asset = asset_registry.get(asset_path)
            if asset is None:
                asset = RenderedAsset(
                    href=_asset_href(asset_path, len(asset_registry) + 1),
                    media_type=(
                        mimetypes.guess_type(asset_path.name)[0]
                        or "application/octet-stream"
                    ),
                    data=asset_path.read_bytes(),
                )
                asset_registry[asset_path] = asset
            element.set("src", relative_href(chapter_href, asset.href))
            continue
        if local_name == "a":
            href = element.get("href")
            if href and href.strip().lower().startswith("javascript:"):
                raise BuildError(
                    f"Chapter {chapter_path} contains unsafe javascript link {href!r}."
                )

    if allow_inline_xhtml:
        validate_rendered_xhtml_tree(root, chapter_path=chapter_path)

    body_xhtml = "".join(
        etree.tostring(child, encoding="unicode", method="xml") for child in root
    )
    return body_xhtml, discovered_title


def markdown_parser(*, allow_inline_xhtml: bool) -> MarkdownIt:
    return MarkdownIt("commonmark", {"html": allow_inline_xhtml}).enable("table")


def validate_raw_xhtml_tokens(
    markdown_text: str, *, parser: MarkdownIt, chapter_path: Path
) -> None:
    for token in parser.parse(markdown_text):
        if token.type == "html_block":
            raise BuildError(
                f"Chapter {chapter_path} contains raw block XHTML, which is not "
                "supported. Use Markdown for blocks and --allow-inline-xhtml only "
                "for safe inline tags such as <em>, <strong>, <span>, and <a>."
            )
        if token.type != "inline" or token.children is None:
            continue
        raw_inline = "".join(
            child.content for child in token.children if child.type == "html_inline"
        )
        if not raw_inline:
            continue
        try:
            validate_safe_inline_fragment(
                raw_inline,
                context=f"Chapter {chapter_path}",
                mode="markdown_inline",
            )
        except UnsafeFragmentError as exc:
            raise BuildError(str(exc)) from exc


def validate_rendered_xhtml_tree(root: etree._Element, *, chapter_path: Path) -> None:
    allowed_structural_tags = {
        "blockquote",
        "code",
        "dd",
        "dl",
        "dt",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "img",
        "li",
        "ol",
        "p",
        "pre",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    }
    allowed_tags = allowed_structural_tags | set(ALLOWED_INLINE_TAGS)
    for element in root.iter():
        local_name = _local_name(element.tag)
        if local_name is None or local_name == "div":
            continue
        if local_name not in allowed_tags:
            raise BuildError(
                f"Chapter {chapter_path} contains unsupported XHTML tag "
                f"{local_name!r}."
            )
        for raw_attribute_name, value in element.attrib.items():
            local_attr = attribute_name(raw_attribute_name)
            if local_attr.startswith("on"):
                raise BuildError(
                    f"Chapter {chapter_path} contains unsafe event handler "
                    f"attribute {local_attr!r}."
                )
            if local_attr in {"href", "src"} and value.strip().lower().startswith(
                "javascript:"
            ):
                raise BuildError(
                    f"Chapter {chapter_path} contains unsafe javascript URL."
                )
            if is_allowed_rendered_attribute(local_name, local_attr, value):
                continue
            raise BuildError(
                f"Chapter {chapter_path} contains unsupported attribute "
                f"{local_attr!r} on <{local_name}>."
            )


def is_allowed_rendered_attribute(tag: str, attr: str, value: str) -> bool:
    if attr in {"class", "dir", "epub:type", "id", "lang", "title", "xml:lang"}:
        return True
    if tag == "a" and attr == "href":
        return True
    if tag == "img" and attr in {"alt", "src", "title"}:
        return True
    if tag == "ol" and attr == "start":
        return True
    if tag in {"td", "th"} and attr == "style":
        return (
            re.fullmatch(r"text-align\s*:\s*(left|right|center)", value)
            is not None
        )
    return False


def merge_metadata(
    explicit_metadata: EpubMetadata, front_matter: dict[str, str]
) -> EpubMetadata:
    creators = explicit_metadata.creators
    if not creators and front_matter.get("author"):
        creators = [front_matter["author"]]
    contributors = explicit_metadata.contributors
    return EpubMetadata(
        title=explicit_metadata.title or front_matter.get("title", ""),
        language=explicit_metadata.language or front_matter.get("language", "en"),
        creators=creators,
        contributors=contributors,
        publisher=explicit_metadata.publisher or front_matter.get("publisher"),
        description=explicit_metadata.description or front_matter.get("description"),
        identifier=explicit_metadata.identifier or front_matter.get("identifier"),
        rights=explicit_metadata.rights or front_matter.get("rights"),
        date=explicit_metadata.date or front_matter.get("date"),
    )


def relative_href(from_href: str, to_href: str) -> str:
    from_dir = PurePosixPath(from_href).parent.as_posix() or "."
    return posixpath.relpath(to_href, start=from_dir)


def unique_slug(text: str, counts: dict[str, int]) -> str:
    base = slugify(text)
    current = counts.get(base, 0)
    counts[base] = current + 1
    if current == 0:
        return base
    return f"{base}-{current + 1}"


def slugify(text: str) -> str:
    lowered = text.casefold()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = lowered.strip("-")
    return lowered or "section"


def is_remote_resource(value: str) -> bool:
    lowered = value.casefold()
    return lowered.startswith(("http://", "https://", "//"))


def _asset_href(asset_path: Path, index: int) -> str:
    suffix = asset_path.suffix.lower()
    return f"Images/image-{index:03d}{suffix}"


def _local_name(tag: object) -> str | None:
    if not isinstance(tag, str):
        return None
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _parse_front_matter(lines: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in lines:
        if not line.strip() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _path_title(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").title()
