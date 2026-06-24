from __future__ import annotations

from typing import cast

from lxml import etree

from .errors import UnsafeFragmentError

ALLOWED_INLINE_TAGS = frozenset(
    {
        "a",
        "abbr",
        "b",
        "bdi",
        "bdo",
        "br",
        "cite",
        "code",
        "data",
        "dfn",
        "em",
        "i",
        "kbd",
        "mark",
        "q",
        "rb",
        "rp",
        "rt",
        "ruby",
        "s",
        "samp",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "time",
        "u",
        "var",
        "wbr",
    }
)

ALLOWED_INLINE_ATTRIBUTES = frozenset(
    {
        "class",
        "dir",
        "epub:type",
        "href",
        "id",
        "lang",
        "title",
        "xml:lang",
    }
)


def attribute_name(name: str) -> str:
    if name == "{http://www.w3.org/XML/1998/namespace}lang":
        return "xml:lang"
    if name == "{http://www.idpf.org/2007/ops}type":
        return "epub:type"
    if name.startswith("{"):
        return etree.QName(name).localname
    return name


def validate_inline_fragment(fragment: str, *, context: str, mode: str) -> None:
    wrapper = (
        '<root xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">'
        f"{fragment}</root>"
    )
    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(wrapper.encode("utf-8"), parser=parser)
    except etree.XMLSyntaxError as exc:
        raise UnsafeFragmentError(
            f"{context} contains malformed inline XHTML."
        ) from exc
    for element in root.iter():
        if element is root:
            continue
        validate_inline_element(element, context=context, mode=mode)


def validate_inline_element(
    element: etree._Element, *, context: str, mode: str
) -> None:
    local_name = etree.QName(element.tag).localname
    if local_name not in ALLOWED_INLINE_TAGS:
        raise UnsafeFragmentError(
            f"{context} contains forbidden tag {local_name!r} for mode {mode!r}."
        )
    for attribute_name_raw, value in element.attrib.items():
        name = cast("str", attribute_name_raw)
        text_value = cast("str", value)
        local_attr = attribute_name(name)
        if local_attr.startswith("on"):
            raise UnsafeFragmentError(
                f"{context} contains forbidden event handler attribute {local_attr!r}."
            )
        if local_attr not in ALLOWED_INLINE_ATTRIBUTES:
            raise UnsafeFragmentError(
                f"{context} contains forbidden attribute {local_attr!r}."
            )
        if local_attr == "href" and text_value.strip().lower().startswith(
            "javascript:"
        ):
            raise UnsafeFragmentError(f"{context} contains forbidden javascript href.")
