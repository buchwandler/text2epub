from __future__ import annotations

import os
import posixpath
import shutil
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

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
    if source.resolve() == destination.resolve():
        raise PackageError(
            "Refusing to overwrite the source EPUB in place; choose a different "
            "output path."
        )
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
    """Rewrite an EPUB by overlaying changed entries onto the source archive.

    The destination is produced atomically: a uniquely named sibling temporary
    file is written in the destination directory, validated as an EPUB package,
    and only then atomically moved into place. On any failure the temporary
    file is removed and an existing destination is left untouched.
    """
    source = coerce_path(source_epub)
    destination = coerce_path(output_path)
    if source.resolve() == destination.resolve():
        raise PackageError(
            "Refusing to overwrite the source EPUB in place; choose a different "
            "output path."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_name = f".{destination.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    temp_path = destination.parent / temp_name
    try:
        try:
            with (
                zipfile.ZipFile(source) as source_archive,
                zipfile.ZipFile(temp_path, "w") as target_archive,
            ):
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
        validate_epub_package(temp_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    os.replace(temp_path, destination)
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


# ---------------------------------------------------------------------------
# Package discovery (container.xml + OPF) for rebuild output rewriting
# ---------------------------------------------------------------------------

CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
XHTML_NS = "http://www.w3.org/1999/xhtml"
XML_NS = "http://www.w3.org/XML/1998/namespace"
RENDITION_NS = "http://www.idpf.org/2007/ops#rendition"
OPF_PACKAGE_MEDIA_TYPE = "application/oebps-package+xml"
XHTML_MEDIA_TYPES = frozenset({"application/xhtml+xml", "text/html"})


def _xml_parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        remove_blank_text=False,
        strip_cdata=False,
    )


def _parse_xml(data: bytes, *, context: str) -> etree._ElementTree:
    try:
        return etree.fromstring(data, parser=_xml_parser()).getroottree()
    except etree.XMLSyntaxError as exc:
        raise PackageError(f"Malformed XML in {context}: {exc.msg}") from exc


@dataclass(slots=True)
class OpfManifestItem:
    """A single OPF manifest item resolved to an archive member name."""

    id: str
    href: str
    archive_name: str
    media_type: str
    properties: frozenset[str]
    fallback: str | None


@dataclass(slots=True)
class PackageModel:
    """Structured view of a rebuilt EPUB's package document and manifest."""

    opf_archive_name: str
    opf_dir: str
    manifest: dict[str, OpfManifestItem]
    spine_item_ids: list[str]
    nav_item: OpfManifestItem | None
    primary_language: str | None
    is_fixed_layout: bool
    warnings: list[str] = field(default_factory=list)
    _opf_bytes: bytes = b""
    _archive_names: tuple[str, ...] = ()

    def archive_order(self, name: str) -> int:
        try:
            return self._archive_names.index(name)
        except ValueError:
            return len(self._archive_names)

    def item_by_archive_name(self, name: str) -> OpfManifestItem | None:
        for item in self.manifest.values():
            if item.archive_name == name:
                return item
        return None

    def opf_bytes(self) -> bytes:
        return self._opf_bytes


def select_opf_rootfile(container_bytes: bytes) -> tuple[str, list[str]]:
    """Select the OPF rootfile from ``META-INF/container.xml``.

    Returns the selected ``full-path`` plus the list of all matching rootfiles.
    Raises :class:`PackageError` when no matching rootfile exists and records a
    warning (in the caller) when more than one matches.
    """
    tree = _parse_xml(container_bytes, context=CONTAINER_ENTRY)
    rootfiles = tree.findall(f".//{{{CONTAINER_NS}}}rootfile")
    matching: list[str] = []
    for rootfile in rootfiles:
        media_type = rootfile.get("media-type")
        full_path = rootfile.get("full-path")
        if media_type == OPF_PACKAGE_MEDIA_TYPE and full_path:
            matching.append(full_path)
    if not matching:
        raise PackageError(
            f"{CONTAINER_ENTRY!r} has no rootfile with media type "
            f"{OPF_PACKAGE_MEDIA_TYPE!r}."
        )
    return matching[0], matching


def is_xhtml_media_type(media_type: str) -> bool:
    return media_type.strip().lower() in XHTML_MEDIA_TYPES


def resolve_opf_href(opf_dir: str, href: str) -> str:
    """Resolve an OPF-relative href into an archive member name.

    Backslashes are normalised to forward slashes and ``.``/``..`` segments are
    collapsed. A result that escapes the OPF directory (starts with ``..``) is a
    traversal and is reported as such by callers.
    """
    cleaned = href.strip().replace("\\", "/")
    base = opf_dir
    if base:
        joined = posixpath.normpath(posixpath.join(base, cleaned))
    else:
        joined = posixpath.normpath(cleaned)
    return joined


def href_is_traversal(resolved: str) -> bool:
    return resolved == ".." or resolved.startswith("../") or posixpath.isabs(resolved)


def detect_publication_fixed_layout(package_element: etree._Element) -> bool:
    metadata = package_element.find(f"{{{OPF_NS}}}metadata")
    if metadata is None:
        return False
    for meta in metadata.iterfind(f"{{{OPF_NS}}}meta"):
        if (
            meta.get("property") == "rendition:layout"
            and (meta.text or "").strip() == "pre-paginated"
        ):
            return True
    return False


def load_package_model(archive: zipfile.ZipFile) -> PackageModel:
    """Discover and parse the package document of a rebuilt source EPUB."""
    try:
        container_bytes = archive.read(CONTAINER_ENTRY)
    except KeyError as exc:
        raise PackageError(f"EPUB is missing {CONTAINER_ENTRY!r}.") from exc

    opf_path, all_matches = select_opf_rootfile(container_bytes)
    warnings: list[str] = []
    if len(all_matches) > 1:
        warnings.append(
            f"{CONTAINER_ENTRY!r} declares multiple OPF rootfiles "
            f"{all_matches!r}; selected {opf_path!r}."
        )
    try:
        opf_bytes = archive.read(opf_path)
    except KeyError as exc:
        raise PackageError(
            f"OPF rootfile {opf_path!r} is not present in the archive."
        ) from exc

    tree = _parse_xml(opf_bytes, context=opf_path)
    package_element = tree.getroot()
    opf_dir = posixpath.dirname(opf_path)
    archive_names = tuple(archive.namelist())

    manifest: dict[str, OpfManifestItem] = {}
    for item in package_element.iterfind(f"{{{OPF_NS}}}manifest/{{{OPF_NS}}}item"):
        item_id = item.get("id")
        if not item_id:
            raise PackageError(f"OPF manifest item without id in {opf_path!r}.")
        href = item.get("href", "")
        media_type = item.get("media-type", "")
        properties = frozenset(item.get("properties", "").split())
        fallback = item.get("fallback")
        archive_name = resolve_opf_href(opf_dir, href)
        manifest[item_id] = OpfManifestItem(
            id=item_id,
            href=href,
            archive_name=archive_name,
            media_type=media_type,
            properties=properties,
            fallback=fallback,
        )

    spine_item_ids: list[str] = []
    for itemref in package_element.iterfind(f"{{{OPF_NS}}}spine/{{{OPF_NS}}}itemref"):
        idref = itemref.get("idref")
        if idref:
            spine_item_ids.append(idref)

    nav_item = next(
        (item for item in manifest.values() if "nav" in item.properties),
        None,
    )

    metadata = package_element.find(f"{{{OPF_NS}}}metadata")
    primary_language: str | None = None
    if metadata is not None:
        for lang_el in metadata.iterfind(f"{{{DC_NS}}}language"):
            if lang_el.text and lang_el.text.strip():
                primary_language = lang_el.text.strip()
                break

    is_fixed_layout = detect_publication_fixed_layout(package_element)

    return PackageModel(
        opf_archive_name=opf_path,
        opf_dir=opf_dir,
        manifest=manifest,
        spine_item_ids=spine_item_ids,
        nav_item=nav_item,
        primary_language=primary_language,
        is_fixed_layout=is_fixed_layout,
        warnings=warnings,
        _opf_bytes=opf_bytes,
        _archive_names=archive_names,
    )
