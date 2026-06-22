from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .builder import create_epub_from_markdown
from .errors import Text2EpubError, ValidationError
from .markdown import is_remote_resource
from .models import (
    BuildOptions,
    EpubMetadata,
    MarkdownBook,
    MarkdownChapter,
    Replacement,
    ReplacementPlan,
)
from .package import validate_epub_package
from .replacement import rebuild_epub
from .validation import scan_epub_for_unresolved_tokens

try:
    from ._version import version as PACKAGE_VERSION
except Exception:  # pragma: no cover
    PACKAGE_VERSION = "0.0.0+unknown"


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except Text2EpubError as exc:
        parser.exit(1, f"{exc}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="text2epub")
    subparsers = parser.add_subparsers(dest="command", required=True)

    markdown_parser = subparsers.add_parser("markdown")
    markdown_parser.add_argument("input")
    markdown_parser.add_argument("-o", "--output", required=True)
    markdown_parser.add_argument("--title")
    markdown_parser.add_argument("--language")
    markdown_parser.add_argument("--creator")
    markdown_parser.add_argument("--identifier")
    markdown_parser.add_argument("--publisher")
    markdown_parser.add_argument("--description")
    markdown_parser.add_argument("--rights")
    markdown_parser.add_argument("--date")
    markdown_parser.add_argument("--no-ncx", action="store_true")
    markdown_parser.add_argument("--non-deterministic", action="store_true")
    markdown_parser.add_argument(
        "--allow-remote-resources", action="store_true"
    )
    markdown_parser.add_argument("--json", action="store_true")
    markdown_parser.set_defaults(handler=handle_markdown)

    rebuild_parser = subparsers.add_parser("rebuild")
    rebuild_parser.add_argument("source_epub")
    rebuild_parser.add_argument("manifest")
    rebuild_parser.add_argument("replacements")
    rebuild_parser.add_argument("-o", "--output", required=True)
    rebuild_parser.add_argument("--allow-unresolved-tokens", action="store_true")
    rebuild_parser.add_argument("--json", action="store_true")
    rebuild_parser.set_defaults(handler=handle_rebuild)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("epub")
    validate_parser.add_argument("--json", action="store_true")
    validate_parser.set_defaults(handler=handle_validate)

    version_parser = subparsers.add_parser("version")
    version_parser.set_defaults(handler=handle_version)
    return parser


def handle_markdown(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    chapter_paths = discover_markdown_inputs(input_path)
    metadata = EpubMetadata(
        title=args.title or "",
        language=args.language or "",
        creators=[args.creator] if args.creator else [],
        publisher=args.publisher,
        description=args.description,
        identifier=args.identifier,
        rights=args.rights,
        date=args.date,
    )
    options = BuildOptions(
        include_ncx=not args.no_ncx,
        deterministic=not args.non_deterministic,
        allow_remote_resources=args.allow_remote_resources,
    )
    book = MarkdownBook(
        metadata=metadata,
        chapters=[MarkdownChapter(path=path) for path in chapter_paths],
        options=options,
    )
    output_path = create_epub_from_markdown(book, Path(args.output))
    if args.json:
        print(json.dumps({"output_path": str(output_path)}))
    else:
        print(output_path)
    return 0


def handle_rebuild(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.replacements).read_text(encoding="utf-8"))
    replacements = [
        Replacement(
            block_id=item["block_id"],
            text=item["text"],
            expected_source=item.get("expected_source"),
            allow_inline_xhtml=item.get("allow_inline_xhtml", True),
        )
        for item in payload.get("replacements", [])
    ]
    plan = ReplacementPlan(
        source_epub=Path(args.source_epub),
        extraction_manifest=Path(args.manifest),
        replacements=replacements,
        options=BuildOptions(
            fail_on_unresolved_tokens=not args.allow_unresolved_tokens
        ),
    )
    report = rebuild_epub(plan, Path(args.output))
    if args.json:
        print(
            json.dumps(
                {
                    "output_path": str(report.output_path),
                    "changed_entries": report.changed_entries,
                    "unchanged_entries": report.unchanged_entries,
                    "replacement_count": report.replacement_count,
                    "unresolved_token_count": report.unresolved_token_count,
                    "warnings": report.warnings,
                }
            )
        )
    else:
        print(report.output_path)
    return 0


def handle_validate(args: argparse.Namespace) -> int:
    epub_path = Path(args.epub)
    validate_epub_package(epub_path)
    findings = scan_epub_for_unresolved_tokens(epub_path)
    if findings:
        entry_name, token = findings[0]
        raise ValidationError(
            f"Unresolved internal token {token!r} remains in ZIP entry "
            f"{entry_name!r}."
        )
    if args.json:
        print(
            json.dumps(
                {
                    "epub": str(epub_path),
                    "valid": True,
                    "unresolved_token_count": 0,
                }
            )
        )
    else:
        print(f"{epub_path}: valid")
    return 0


def handle_version(_: argparse.Namespace) -> int:
    print(PACKAGE_VERSION)
    return 0


def discover_markdown_inputs(input_path: Path) -> list[Path]:
    if input_path.is_dir():
        chapter_paths = sorted(input_path.glob("*.md"))
        if not chapter_paths:
            raise Text2EpubError(
                f"Markdown directory {input_path} does not contain any .md files."
            )
        return chapter_paths
    if input_path.is_file():
        return [input_path]
    if is_remote_resource(str(input_path)):
        raise Text2EpubError(
            f"Markdown input {input_path} must be a local file or directory."
        )
    raise Text2EpubError(f"Markdown input {input_path} does not exist.")
