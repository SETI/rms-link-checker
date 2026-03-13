"""URL decision tree and asset type classification."""

from __future__ import annotations

from enum import Enum
from urllib.parse import urlparse

from link_checker.config import CrawlConfig
from link_checker.url_utils import (
    get_file_extension,
    is_html_extension,
    is_http_url,
    is_same_domain,
    is_under_root,
    matches_prefix,
    normalize_url,
)

# ---------------------------------------------------------------------------
# Asset type classification
# ---------------------------------------------------------------------------

_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.bmp', '.tiff', '.tif', '.avif'}
)
_DOCUMENT_EXTENSIONS: frozenset[str] = frozenset(
    {
        '.pdf',
        '.doc',
        '.docx',
        '.xls',
        '.xlsx',
        '.ppt',
        '.pptx',
        '.txt',
        '.csv',
        '.rtf',
        '.odt',
        '.ods',
        '.odp',
    }
)
_DATA_EXTENSIONS: frozenset[str] = frozenset({'.tab', '.xml', '.lbl', '.lblx', '.img'})
_INFRASTRUCTURE_EXTENSIONS: frozenset[str] = frozenset(
    {'.js', '.mjs', '.css', '.woff', '.woff2', '.ttf', '.eot', '.otf', '.map', '.json'}
)


class AssetType(Enum):
    """Category of a non-HTML asset URL."""

    IMAGE = 'Image'
    DOCUMENT = 'Document'
    DATA = 'Data'
    INFRASTRUCTURE = 'Infrastructure'
    OTHER = 'Other'


class UrlDisposition(Enum):
    """How the crawler should handle a given URL (spec §6 decision tree)."""

    NON_HTTP = 'non_http'
    IGNORED = 'ignored'
    ALREADY_VISITED = 'already_visited'
    NO_CRAWL = 'no_crawl'
    EXTERNAL = 'external'
    DEPTH_LIMITED = 'depth_limited'
    INTERNAL_CRAWL = 'internal_crawl'
    INTERNAL_ASSET = 'internal_asset'


def classify_asset(extension: str) -> AssetType:
    """Return the :class:`AssetType` for a file extension.

    Args:
        extension: Lowercase file extension including leading dot (e.g. ``'.jpg'``).

    Returns:
        The :class:`AssetType` for the extension.
    """
    ext = extension.lower()
    if ext in _IMAGE_EXTENSIONS:
        return AssetType.IMAGE
    if ext in _DOCUMENT_EXTENSIONS:
        return AssetType.DOCUMENT
    if ext in _DATA_EXTENSIONS:
        return AssetType.DATA
    if ext in _INFRASTRUCTURE_EXTENSIONS:
        return AssetType.INFRASTRUCTURE
    return AssetType.OTHER


def classify_url(
    url: str,
    *,
    config: CrawlConfig,
    root_url: str,
    root_path: str,
    visited_set: set[str],
    depth: int,
) -> UrlDisposition:
    """Classify a URL per the spec §6 decision tree.

    Steps (in order):
    1. Non-HTTP scheme → :attr:`UrlDisposition.NON_HTTP`
    2. Matches ``ignore_urls`` → :attr:`UrlDisposition.IGNORED`
    3. Already visited → :attr:`UrlDisposition.ALREADY_VISITED`
    4. Matches ``no_crawl_urls`` → :attr:`UrlDisposition.NO_CRAWL`
    5. External (different domain or above root path) → :attr:`UrlDisposition.EXTERNAL`
    6. Exceeds depth limit → :attr:`UrlDisposition.DEPTH_LIMITED`
    7. Internal HTML/no-extension → :attr:`UrlDisposition.INTERNAL_CRAWL`
    8. Internal asset → :attr:`UrlDisposition.INTERNAL_ASSET`

    Args:
        url: The URL to classify (absolute, not yet normalized for query/fragment).
        config: Current crawl configuration.
        root_url: Normalized root URL.
        root_path: Path component of the root URL.
        visited_set: Set of already-visited canonical URLs.
        depth: Directory depth of *url* relative to root.

    Returns:
        The :class:`UrlDisposition` for the URL.
    """
    if not is_http_url(url):
        return UrlDisposition.NON_HTTP

    for prefix in config.ignore_urls:
        if matches_prefix(url, prefix):
            return UrlDisposition.IGNORED

    canonical, _ = normalize_url(url)
    if canonical in visited_set:
        return UrlDisposition.ALREADY_VISITED

    for prefix in config.no_crawl_urls:
        if matches_prefix(url, prefix):
            return UrlDisposition.NO_CRAWL

    parsed_url = urlparse(url)
    if not is_same_domain(url, root_url) or not is_under_root(parsed_url.path, root_path):
        return UrlDisposition.EXTERNAL

    if config.max_depth is not None and depth > config.max_depth:
        return UrlDisposition.DEPTH_LIMITED

    ext = get_file_extension(url)
    if is_html_extension(ext):
        return UrlDisposition.INTERNAL_CRAWL

    return UrlDisposition.INTERNAL_ASSET


def is_misplaced_asset(
    url: str,
    *,
    config: CrawlConfig,
    root_url: str,
    root_path: str,
) -> bool:
    """Return True if *url* is a misplaced asset per spec §8.6.

    An asset is misplaced when **all** of the following hold:
    1. ``asset_urls`` is defined and non-empty.
    2. The asset does not fall under any ``asset_urls`` prefix.
    3. The asset is not external (is on the same domain and under root).
    4. The asset is not matched by an ``ignore_urls`` prefix.
    5. The asset is not matched by a ``no_crawl_urls`` prefix.

    Args:
        url: The asset URL to test.
        config: Current crawl configuration.
        root_url: Normalized root URL.
        root_path: Path component of the root URL.

    Returns:
        True if the asset is misplaced.
    """
    if not config.asset_urls:
        return False

    for prefix in config.asset_urls:
        if matches_prefix(url, prefix):
            return False

    parsed_url = urlparse(url)
    if not is_same_domain(url, root_url) or not is_under_root(parsed_url.path, root_path):
        return False

    if any(matches_prefix(url, prefix) for prefix in config.ignore_urls):
        return False

    return not any(matches_prefix(url, prefix) for prefix in config.no_crawl_urls)
