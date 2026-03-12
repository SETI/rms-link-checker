"""HTML link extraction, anchor collection, and base-href handling."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

# Each entry: (element_name, attribute, is_asset)
_LINK_SPEC: list[tuple[str, str, bool]] = [
    ('a', 'href', False),
    ('img', 'src', True),
    ('img', 'srcset', True),
    ('link', 'href', True),
    ('script', 'src', True),
    ('iframe', 'src', False),
    ('source', 'src', True),
    ('source', 'srcset', True),
    ('video', 'src', True),
    ('video', 'poster', True),
    ('audio', 'src', True),
    ('object', 'data', True),
    ('embed', 'src', True),
    ('form', 'action', True),
]


@dataclass(frozen=True)
class ExtractedLink:
    """A link extracted from an HTML page.

    Attributes:
        url: Absolute URL of the link.
        source_element: HTML element name (e.g. ``"a"``, ``"img"``).
        source_attribute: HTML attribute name (e.g. ``"href"``, ``"src"``).
        is_asset: True if from an asset-only element (never crawled).
    """

    url: str
    source_element: str
    source_attribute: str
    is_asset: bool


def extract_links(
    html: str,
    page_url: str,
    *,
    base_url: str | None = None,
) -> list[ExtractedLink]:
    """Extract all links from *html* and return them as :class:`ExtractedLink` objects.

    Relative URLs are resolved against *base_url* (if given) or the
    ``<base href>`` tag in the document, falling back to *page_url*.

    Args:
        html: Raw HTML string to parse.
        page_url: URL of the page (used for relative URL resolution).
        base_url: Override for relative URL resolution. Supersedes any
            ``<base href>`` found in the document.

    Returns:
        List of :class:`ExtractedLink` with absolute URLs.
    """
    soup = BeautifulSoup(html, 'html.parser')

    effective_base = base_url or find_base_href(html) or page_url

    results: list[ExtractedLink] = []
    seen: set[tuple[str, str, str]] = set()

    for element_name, attr, is_asset in _LINK_SPEC:
        for tag in soup.find_all(element_name):
            if not isinstance(tag, Tag):
                continue
            raw_val = tag.get(attr)
            if not raw_val:
                continue

            if attr == 'srcset':
                urls = _parse_srcset(str(raw_val))
            else:
                urls = [str(raw_val).strip()]

            for raw_url in urls:
                if not raw_url or raw_url == '#':
                    continue
                absolute = urljoin(effective_base, raw_url)
                key = (absolute, element_name, attr)
                if key in seen:
                    continue
                seen.add(key)
                results.append(
                    ExtractedLink(
                        url=absolute,
                        source_element=element_name,
                        source_attribute=attr,
                        is_asset=is_asset,
                    )
                )

    return results


def extract_anchors(html: str) -> frozenset[str]:
    """Extract all anchor IDs from *html* (``id`` attributes and ``<a name>``)

    Args:
        html: Raw HTML string.

    Returns:
        Frozen set of anchor identifier strings.
    """
    soup = BeautifulSoup(html, 'html.parser')
    anchors: set[str] = set()

    for tag in soup.find_all(id=True):
        if not isinstance(tag, Tag):
            continue
        id_val = tag.get('id')
        if id_val:
            anchors.add(str(id_val))

    for tag in soup.find_all('a', attrs={'name': True}):
        if not isinstance(tag, Tag):
            continue
        name_val = tag.get('name')
        if name_val:
            anchors.add(str(name_val))

    return frozenset(anchors)


def find_base_href(html: str) -> str | None:
    """Return the first ``<base href>`` value from the document ``<head>``.

    Args:
        html: Raw HTML string.

    Returns:
        The href value, or None if no ``<base href>`` is found.
    """
    soup = BeautifulSoup(html, 'html.parser')
    base_tag = soup.find('base')
    if not isinstance(base_tag, Tag):
        return None
    href = base_tag.get('href')
    return str(href) if href else None


def _parse_srcset(value: str) -> list[str]:
    """Parse a ``srcset`` attribute value into individual URLs.

    Handles both bare URLs and ``url descriptor`` pairs.

    Args:
        value: Raw ``srcset`` attribute string.

    Returns:
        List of URL strings (descriptors stripped).
    """
    urls: list[str] = []
    for part in value.split(','):
        tokens = part.strip().split()
        if tokens:
            urls.append(tokens[0])
    return urls
