"""URL normalization, prefix matching, and classification utilities."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

HTML_EXTENSIONS: frozenset[str] = frozenset(
    {'.htm', '.html', '.shtml', '.php', '.asp', '.jsp', '.cgi'}
)

# Index filenames that are equivalent to the parent directory URL.
# e.g. /cassini/index.html → /cassini/
_INDEX_FILENAMES: frozenset[str] = frozenset({'index' + ext for ext in HTML_EXTENSIONS})


def _strip_index_filename(path: str) -> str:
    """Strip a conventional directory-index filename from a URL path.

    If the final segment of *path* is a known index filename
    (``index.html``, ``index.php``, etc.) it is removed so the path
    ends with ``/``.  All other paths are returned unchanged.

    Parameters:
        path: The path component of a URL (no scheme, host, query, or
            fragment).

    Returns:
        The path with any trailing index filename removed.
    """
    if not path:
        return path
    last_segment = path.rsplit('/', 1)[-1]
    if last_segment.lower() in _INDEX_FILENAMES:
        return path[: len(path) - len(last_segment)]
    return path


def normalize_url(url: str) -> tuple[str, str | None]:
    """Normalize a URL to its canonical form.

    Transformations applied:

    - Scheme is preserved (``http`` remains ``http``, ``https`` remains ``https``).
    - Host is lowercased.
    - Fragment is stripped (returned separately).
    - Query string is preserved as part of the URL identity.
    - Directory-index filenames (``index.html``, ``index.php``, etc.)
      are stripped so ``/cassini/index.html`` → ``/cassini/``.

    Note that bare directory paths without a trailing slash (e.g.
    ``/cassini``) are left unchanged by this function.  Use
    :func:`add_trailing_slash` to add the trailing slash when you know
    the URL refers to a directory (e.g. for internal crawl targets).

    Parameters:
        url: The URL to normalize.

    Returns:
        A tuple of ``(canonical_url, fragment_or_none)``. For non-HTTP URLs
        the original string is returned unchanged with no fragment.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ('http', 'https'):
        return url, None

    fragment: str | None = parsed.fragment if parsed.fragment else None

    normalized = urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            _strip_index_filename(parsed.path),
            parsed.params,
            parsed.query,
            '',
        )
    )
    return normalized, fragment


def add_trailing_slash(url: str) -> str:
    """Ensure a URL path that has no file extension ends with ``/``.

    This should be applied to **internal** URLs (same domain as the crawl
    root) to canonicalize bare directory paths:

    - ``/cassini`` → ``/cassini/``
    - ``/cassini/`` → ``/cassini/`` (unchanged)
    - ``/cassini/page.html`` → ``/cassini/page.html`` (has extension, unchanged)
    - ``/data.csv`` → ``/data.csv`` (has extension, unchanged)

    Apply after :func:`normalize_url` so that index-file stripping has
    already run (``/cassini/index.html`` → ``/cassini/`` → unchanged here).

    Parameters:
        url: An already-normalized http/https URL.

    Returns:
        The URL with a trailing slash added to any extension-free path.
    """
    parsed = urlparse(url)
    path = parsed.path
    if not path.endswith('/'):
        last_segment = path.rsplit('/', 1)[-1]
        dot_idx = last_segment.rfind('.')
        if dot_idx <= 0:
            path = path + '/'
            url = urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, ''))
    return url


def normalize_internal_url(url: str) -> tuple[str, str | None]:
    """Normalize an internal (same-domain) URL to its canonical form.

    Applies all transformations from :func:`normalize_url` and additionally
    adds a trailing slash to directory-like paths (no file extension):

    - ``/cassini`` → ``/cassini/``
    - ``/cassini/`` → ``/cassini/`` (unchanged)
    - ``/cassini/index.html`` → ``/cassini/`` (index stripped + already slash)
    - ``/cassini/page.html`` → ``/cassini/page.html`` (has extension, unchanged)

    Use this for deduplication and request URLs of internal crawl targets.
    For external URLs use :func:`normalize_url` alone to avoid altering
    the request path in ways the server may not expect.

    Parameters:
        url: The URL to normalize.

    Returns:
        A tuple of ``(canonical_url, fragment_or_none)``.
    """
    normalized, fragment = normalize_url(url)
    if not is_http_url(normalized):
        return normalized, fragment
    return add_trailing_slash(normalized), fragment


def is_same_domain(url: str, root_url: str) -> bool:
    """Return True if *url* has the same host (including port) as *root_url*.

    Comparison is case-insensitive. Scheme is ignored. Subdomains are
    considered different domains.

    Parameters:
        url: The URL to check.
        root_url: The reference URL whose host to compare against.

    Returns:
        True if both URLs share the same host.
    """
    return urlparse(url).netloc.lower() == urlparse(root_url).netloc.lower()


def is_under_root(url_path: str, root_path: str) -> bool:
    """Return True if *url_path* is at or under *root_path* on a segment boundary.

    Parameters:
        url_path: The path component of the URL to test.
        root_path: The root path to test containment against.

    Returns:
        True if *url_path* is the same as or under *root_path*.
    """
    root = root_path.rstrip('/')
    candidate = url_path.rstrip('/')

    if root == '':
        return True

    return candidate == root or candidate.startswith(root + '/')


def matches_prefix(candidate_url: str, prefix_url: str) -> bool:
    """Return True if *candidate_url* matches *prefix_url* per spec §5.7 rules.

    Matching rules:

    - Scheme is ignored (http and https are equivalent).
    - Host comparison is case-insensitive (and must be equal).
    - Path of candidate must equal path of prefix, or start with prefix path
      followed by ``/`` (segment-boundary matching).

    Parameters:
        candidate_url: The URL to test.
        prefix_url: The prefix URL to match against.

    Returns:
        True if *candidate_url* matches *prefix_url*.
    """
    c = urlparse(candidate_url)
    p = urlparse(prefix_url)

    if c.netloc.lower() != p.netloc.lower():
        return False

    prefix_path = p.path.rstrip('/')
    candidate_path = c.path.rstrip('/')

    return candidate_path == prefix_path or candidate_path.startswith(prefix_path + '/')


def get_file_extension(url: str) -> str | None:
    """Return the lowercase file extension from the URL path, or None.

    Only inspects the path component (ignores query string and fragment).
    Returns None for paths ending in ``/`` or having no dot in the last
    segment.

    Parameters:
        url: The URL to inspect.

    Returns:
        Lowercase extension including the leading dot (e.g. ``'.pdf'``),
        or None if there is no extension.
    """
    path = urlparse(url).path
    if path.endswith('/'):
        return None

    last_segment = path.rsplit('/', 1)[-1]
    dot_idx = last_segment.rfind('.')
    if dot_idx <= 0:
        return None

    return last_segment[dot_idx:].lower()


def is_html_extension(ext: str | None) -> bool:
    """Return True if *ext* indicates an HTML-like page (or no extension at all).

    Parameters:
        ext: Lowercase file extension including leading dot, or None.

    Returns:
        True for extensions in :data:`HTML_EXTENSIONS` and for None.
    """
    if ext is None:
        return True
    return ext.lower() in HTML_EXTENSIONS


def get_depth(url_path: str, root_path: str) -> int:
    """Return the directory depth of *url_path* relative to *root_path*.

    Depth 0 is the root page itself (or its trailing-slash variant).
    Each additional directory segment adds 1.

    Parameters:
        url_path: The path to measure.
        root_path: The root path to measure from.

    Returns:
        Integer depth >= 0.
    """
    root = root_path.rstrip('/')
    candidate = url_path.rstrip('/')

    if candidate == root:
        return 0

    relative = candidate[len(root) :]
    relative = relative.lstrip('/')

    if not relative:
        return 0

    return len(relative.split('/'))


def is_http_url(url: str) -> bool:
    """Return True if *url* uses the ``http`` or ``https`` scheme.

    Parameters:
        url: The URL string to test.

    Returns:
        True for HTTP/HTTPS URLs, False for everything else.
    """
    return urlparse(url).scheme in ('http', 'https')
