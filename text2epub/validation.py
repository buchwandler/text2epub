from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

from .errors import ValidationError
from .models import DEFAULT_UNRESOLVED_TOKEN_PATTERNS
from .package import coerce_path

TEXT_ENTRY_SUFFIXES = (".xhtml", ".html", ".opf", ".ncx", ".xml", ".nav")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path | str) -> str:
    return sha256_bytes(coerce_path(path).read_bytes())


def is_text_entry(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith(TEXT_ENTRY_SUFFIXES)


def scan_text_for_unresolved_tokens(
    text: str, entry_name: str, patterns: list[str] | None = None
) -> list[tuple[str, str]]:
    compiled = patterns or DEFAULT_UNRESOLVED_TOKEN_PATTERNS
    findings: list[tuple[str, str]] = []
    for pattern in compiled:
        for match in re.finditer(pattern, text):
            findings.append((entry_name, match.group(0)))
    return findings


def ensure_no_unresolved_tokens(
    text_entries: dict[str, str], patterns: list[str] | None = None
) -> int:
    findings: list[tuple[str, str]] = []
    for entry_name, text in text_entries.items():
        findings.extend(scan_text_for_unresolved_tokens(text, entry_name, patterns))
    if findings:
        entry_name, token = findings[0]
        raise ValidationError(
            f"Unresolved internal token {token!r} remains in ZIP entry "
            f"{entry_name!r}."
        )
    return len(findings)


def scan_epub_for_unresolved_tokens(
    epub_path: Path | str, patterns: list[str] | None = None
) -> list[tuple[str, str]]:
    archive_path = coerce_path(epub_path)
    findings: list[tuple[str, str]] = []
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            if not is_text_entry(name):
                continue
            text = archive.read(name).decode("utf-8")
            findings.extend(scan_text_for_unresolved_tokens(text, name, patterns))
    return findings
