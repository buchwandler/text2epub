from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .errors import PackageError, ValidationError

MIMETYPE_ENTRY = "mimetype"
MIMETYPE_VALUE = b"application/epub+zip"
CONTAINER_ENTRY = "META-INF/container.xml"
CONTENT_OPF_ENTRY = "OEBPS/content.opf"
NAV_ENTRY = "OEBPS/nav.xhtml"
DETERMINISTIC_ZIP_DT = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class PackageEntry:
    name: str
    data: bytes
    compress_type: int = zipfile.ZIP_DEFLATED


def coerce_path(path: Path | str) -> Path:
    return path if isinstance(path, Path) else Path(path)


def clone_zip_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    cloned = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    cloned.compress_type = info.compress_type
    cloned.comment = info.comment
    cloned.extra = info.extra
    cloned.create_system = info.create_system
    cloned.create_version = info.create_version
    cloned.extract_version = info.extract_version
    cloned.flag_bits = info.flag_bits
    cloned.internal_attr = info.internal_attr
    cloned.external_attr = info.external_attr
    try:
        cloned.volume = info.volume
    except AttributeError:  # pragma: no cover
        pass
    return cloned


def deterministic_zip_info(
    name: str, *, compress_type: int = zipfile.ZIP_DEFLATED
) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=DETERMINISTIC_ZIP_DT)
    info.compress_type = compress_type
    return info


def copy_epub(source_epub: Path | str, output_path: Path | str) -> Path:
    source = coerce_path(source_epub)
    destination = coerce_path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination


def validate_epub_package(path: Path | str) -> None:
    archive_path = coerce_path(path)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if not infos:
                raise ValidationError(
                    f"EPUB package {archive_path} is empty and has no ZIP entries."
                )
            first = infos[0]
            if first.filename != MIMETYPE_ENTRY:
                raise ValidationError(
                    f"EPUB package {archive_path} must start with {MIMETYPE_ENTRY!r}, "
                    f"but found {first.filename!r}."
                )
            if first.compress_type != zipfile.ZIP_STORED:
                raise ValidationError(
                    f"EPUB package {archive_path} must store {MIMETYPE_ENTRY!r} "
                    "without compression."
                )
            mimetype_bytes = archive.read(MIMETYPE_ENTRY)
            if mimetype_bytes != MIMETYPE_VALUE:
                raise ValidationError(
                    f"EPUB package {archive_path} has invalid {MIMETYPE_ENTRY!r} "
                    f"content: {mimetype_bytes!r}."
                )
            if CONTAINER_ENTRY not in archive.namelist():
                raise ValidationError(
                    f"EPUB package {archive_path} is missing {CONTAINER_ENTRY!r}."
                )
    except zipfile.BadZipFile as exc:
        raise PackageError(f"{archive_path} is not a valid ZIP archive.") from exc


def rewrite_epub(
    source_epub: Path | str,
    output_path: Path | str,
    changed_entries: dict[str, bytes],
) -> Path:
    source = coerce_path(source_epub)
    destination = coerce_path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(source) as source_archive:
            with zipfile.ZipFile(destination, "w") as target_archive:
                target_archive.comment = source_archive.comment
                for info in source_archive.infolist():
                    payload = changed_entries.get(
                        info.filename, source_archive.read(info.filename)
                    )
                    target_archive.writestr(clone_zip_info(info), payload)
    except OSError as exc:
        raise PackageError(
            f"Failed to rewrite EPUB package from {source} to {destination}."
        ) from exc
    return destination


def write_generated_epub(
    entries: list[PackageEntry],
    output_path: Path | str,
    *,
    deterministic: bool = True,
) -> Path:
    destination = coerce_path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(destination, "w") as archive:
            for entry in entries:
                compress_type = entry.compress_type
                if entry.name == MIMETYPE_ENTRY:
                    compress_type = zipfile.ZIP_STORED
                if deterministic:
                    info = deterministic_zip_info(
                        entry.name, compress_type=compress_type
                    )
                else:
                    info = zipfile.ZipInfo(entry.name)
                    info.compress_type = compress_type
                archive.writestr(info, entry.data)
    except OSError as exc:
        raise PackageError(f"Failed to write generated EPUB {destination}.") from exc
    return destination
