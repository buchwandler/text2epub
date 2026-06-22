from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .helpers import create_manifest_for_fragment, create_test_epub, write_manifest


def test_cli_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "text2epub", "version"],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip()


def test_cli_markdown_builds_epub(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.md"
    chapter.write_text("# Hello\n\nWorld.\n", encoding="utf-8")
    output = tmp_path / "book.epub"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "text2epub",
            "markdown",
            str(chapter),
            "-o",
            str(output),
            "--title",
            "Example",
        ],
        check=True,
    )

    assert output.exists()


def test_cli_rebuild_json_report(tmp_path: Path) -> None:
    source = create_test_epub(tmp_path / "source.epub", ["<p>Original text.</p>"])
    manifest = create_manifest_for_fragment(
        source,
        "OEBPS/Text/chapter01.xhtml",
        "Original text.",
        replacement_mode="text_node_sequence",
    )
    manifest_path = write_manifest(tmp_path / "manifest.json", manifest)
    replacements_path = tmp_path / "replacements.json"
    replacements_path.write_text(
        json.dumps(
            {
                "replacements": [
                    {
                        "block_id": "spine-0001:block-000001",
                        "text": "Updated text.",
                        "allow_inline_xhtml": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "out.epub"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "text2epub",
            "rebuild",
            str(source),
            str(manifest_path),
            str(replacements_path),
            "-o",
            str(output),
            "--json",
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["changed_entries"] == ["OEBPS/Text/chapter01.xhtml"]


def test_cli_validate_detects_bad_epub(tmp_path: Path) -> None:
    broken = tmp_path / "broken.epub"
    broken.write_bytes(b"not-a-zip")

    result = subprocess.run(
        [sys.executable, "-m", "text2epub", "validate", str(broken)],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
