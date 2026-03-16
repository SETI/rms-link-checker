"""Thread-safe crawl results aggregation."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, replace
from urllib.parse import urlparse


@dataclass
class BrokenLink:
    """A link that returned an error or non-success status.

    Attributes:
        url: The broken URL.
        status_code: HTTP status code (0 = network error).
        error: Error description string.
        referencing_pages: Pages that contained this broken link.
    """

    url: str
    status_code: int
    error: str
    referencing_pages: list[str] = field(default_factory=list)


@dataclass
class RedirectInfo:
    """A URL that redirected to another location.

    Attributes:
        original_url: The URL that redirected.
        final_url: The URL after all redirects.
        status_code: The HTTP status code of the first redirect hop (e.g. 301, 302).
        referencing_pages: Pages that contained the original URL.
    """

    original_url: str
    final_url: str
    status_code: int
    referencing_pages: list[str] = field(default_factory=list)


@dataclass
class BrokenAnchor:
    """A fragment reference that could not be resolved.

    Attributes:
        target_url: The full URL including fragment.
        referencing_pages: Pages containing the broken anchor link.
    """

    target_url: str
    referencing_pages: list[str] = field(default_factory=list)


@dataclass
class UnvalidatedAnchor:
    """A fragment reference that could not be validated (no HTML was parsed).

    Attributes:
        target_url: The full URL including fragment.
        reason: Why validation was skipped (``'no-crawl'``, ``'external'``,
            ``'depth-limited'``).
        referencing_pages: Pages containing this anchor link.
    """

    target_url: str
    reason: str
    referencing_pages: list[str] = field(default_factory=list)


@dataclass
class Non200Response:
    """A URL that returned a non-200 final status.

    Attributes:
        url: The URL.
        status_code: HTTP status code.
        referencing_pages: Pages that contained this link.
    """

    url: str
    status_code: int
    referencing_pages: list[str] = field(default_factory=list)


@dataclass
class MisplacedAsset:
    """An asset found outside its expected ``asset_urls`` prefixes.

    Attributes:
        url: The asset URL.
        asset_type: String name of the asset type category.
        referencing_pages: Pages that linked to this asset.
    """

    url: str
    asset_type: str
    referencing_pages: list[str] = field(default_factory=list)


@dataclass
class SslWarning:
    """An SSL error recorded for a domain.

    Attributes:
        domain: The domain that produced the SSL error.
        error: Error message.
        affected_urls: List of (url, referencing_pages) tuples.
    """

    domain: str
    error: str
    affected_urls: list[tuple[str, list[str]]] = field(default_factory=list)


@dataclass
class NonHttpLink:
    """A non-HTTP scheme link encountered during crawl.

    Attributes:
        url: The non-HTTP URL.
        scheme: The scheme (e.g. ``'mailto'``, ``'tel'``).
        referencing_pages: Pages that contained this link.
    """

    url: str
    scheme: str
    referencing_pages: list[str] = field(default_factory=list)


@dataclass
class IgnoreMatch:
    """A URL that was ignored due to matching an ``ignore_urls`` prefix.

    Attributes:
        url: The ignored URL.
        referencing_pages: Pages containing this URL.
    """

    url: str
    referencing_pages: list[str] = field(default_factory=list)


@dataclass
class NoCrawlMatch:
    """A URL that matched a ``no_crawl_urls`` prefix.

    Attributes:
        url: The URL.
        referencing_pages: Pages containing this URL.
    """

    url: str
    referencing_pages: list[str] = field(default_factory=list)


@dataclass
class CrawlStatistics:
    """Aggregated crawl statistics.

    Attributes:
        start_time: UNIX timestamp when the crawl started.
        total_requests: Total HTTP requests issued.
        bytes_downloaded: Total bytes received.
        pages_crawled: Internal pages fetched with GET and parsed.
        pages_checked: Internal pages checked without parsing.
        external_checked: External URLs checked.
        per_domain_requests: Dict mapping domain → request count.
    """

    start_time: float = field(default_factory=time.time)
    total_requests: int = 0
    bytes_downloaded: int = 0
    pages_crawled: int = 0
    pages_checked: int = 0
    external_checked: int = 0
    per_domain_requests: dict[str, int] = field(default_factory=dict)


class CrawlResults:
    """Thread-safe container for all crawl results.

    All ``add_*`` and ``record_*`` methods are safe to call from multiple
    threads simultaneously.
    """

    def __init__(self) -> None:
        """Initialise an empty results container."""
        self._lock = threading.Lock()
        self._broken_links: dict[str, BrokenLink] = {}
        self._redirects: dict[str, RedirectInfo] = {}
        self._broken_anchors: dict[str, BrokenAnchor] = {}
        self._unvalidated_anchors: dict[str, UnvalidatedAnchor] = {}
        self._non200: dict[str, Non200Response] = {}
        self._misplaced_assets: dict[str, MisplacedAsset] = {}
        self._ssl_warnings: dict[str, SslWarning] = {}
        self._non_http_links: dict[str, NonHttpLink] = {}
        self._ignore_matches: dict[str, IgnoreMatch] = {}
        self._no_crawl_matches: dict[str, NoCrawlMatch] = {}
        self._statistics = CrawlStatistics()
        # Referrers registered before the corresponding result entry exists.
        # Drained into the entry when it is first created by an add_* method.
        self._pending_referrers: dict[str, list[str]] = {}

    def _drain_pending(self, url: str) -> list[str]:
        """Return and remove any referrers queued before *url*'s entry existed.

        Must be called inside ``self._lock``.

        Parameters:
            url: The URL whose pending referrers to drain.

        Returns:
            List of pending referrers (may be empty).
        """
        return self._pending_referrers.pop(url, [])

    def _append_referrer(self, referencing_pages: list[str], referrer: str) -> None:
        """Append *referrer* to *referencing_pages* unless it is empty or a duplicate.

        Must be called inside ``self._lock``.

        Parameters:
            referencing_pages: The list to append to.
            referrer: The referrer string to add.
        """
        if referrer != '' and referrer not in referencing_pages:
            referencing_pages.append(referrer)

    def merge_referrer(self, url: str, referrer: str) -> None:
        """Add *referrer* to every existing result entry that tracks *url*.

        If no entry for *url* exists yet (the fetch is still in-flight),
        the referrer is queued and will be applied automatically when the
        entry is created by the corresponding ``add_*`` call.

        Parameters:
            url: Canonical URL to look up.
            referrer: Page that linked to *url*.
        """
        if referrer == '':
            return
        with self._lock:
            found = False
            for mapping in (
                self._broken_links,
                self._redirects,
                self._non200,
                self._misplaced_assets,
                self._non_http_links,
                self._ignore_matches,
                self._no_crawl_matches,
            ):
                entry = mapping.get(url)
                if entry is not None:
                    if referrer not in entry.referencing_pages:
                        entry.referencing_pages.append(referrer)
                    found = True

            # SSL warnings are indexed by domain, not URL; search affected_urls.
            domain = urlparse(url).netloc
            sw = self._ssl_warnings.get(domain)
            if sw is not None:
                for url_entry, refs in sw.affected_urls:
                    if url_entry == url:
                        if referrer not in refs:
                            refs.append(referrer)
                        found = True
                        break

            if not found:
                # Entry not created yet (fetch still in-flight); queue for later.
                pending = self._pending_referrers.setdefault(url, [])
                if referrer not in pending:
                    pending.append(referrer)

    # ------------------------------------------------------------------
    # Broken links
    # ------------------------------------------------------------------

    def add_broken_link(self, *, url: str, status_code: int, error: str, referrer: str) -> None:
        """Record a broken link.

        Parameters:
            url: The broken URL.
            status_code: HTTP status code.
            error: Error or status description.
            referrer: Page that linked to this URL.
        """
        with self._lock:
            if url not in self._broken_links:
                self._broken_links[url] = BrokenLink(url=url, status_code=status_code, error=error)
                for pending in self._drain_pending(url):
                    self._append_referrer(self._broken_links[url].referencing_pages, pending)
            self._append_referrer(self._broken_links[url].referencing_pages, referrer)

    @property
    def broken_links(self) -> list[BrokenLink]:
        """List of broken links sorted by URL."""
        with self._lock:
            return sorted(
                (
                    replace(b, referencing_pages=list(b.referencing_pages))
                    for b in self._broken_links.values()
                ),
                key=lambda b: b.url,
            )

    # ------------------------------------------------------------------
    # Redirects
    # ------------------------------------------------------------------

    def add_redirect(
        self,
        *,
        original_url: str,
        final_url: str,
        status_code: int,
        referrer: str,
    ) -> None:
        """Record a redirect.

        Parameters:
            original_url: The URL that redirected.
            final_url: Destination URL after all redirects.
            status_code: Final HTTP status code.
            referrer: Page that linked to *original_url*.
        """
        with self._lock:
            if original_url not in self._redirects:
                self._redirects[original_url] = RedirectInfo(
                    original_url=original_url,
                    final_url=final_url,
                    status_code=status_code,
                )
                for pending in self._drain_pending(original_url):
                    self._append_referrer(self._redirects[original_url].referencing_pages, pending)
            self._append_referrer(self._redirects[original_url].referencing_pages, referrer)

    @property
    def redirects(self) -> list[RedirectInfo]:
        """List of redirects sorted by original URL."""
        with self._lock:
            return sorted(
                (
                    replace(r, referencing_pages=list(r.referencing_pages))
                    for r in self._redirects.values()
                ),
                key=lambda r: r.original_url,
            )

    # ------------------------------------------------------------------
    # Broken anchors
    # ------------------------------------------------------------------

    def add_broken_anchor(self, *, target_url: str, referrer: str) -> None:
        """Record a broken anchor (fragment not found in target page).

        Parameters:
            target_url: Full URL including the missing fragment.
            referrer: Page that contained the link.
        """
        with self._lock:
            if target_url not in self._broken_anchors:
                self._broken_anchors[target_url] = BrokenAnchor(target_url=target_url)
            self._append_referrer(self._broken_anchors[target_url].referencing_pages, referrer)

    @property
    def broken_anchors(self) -> list[BrokenAnchor]:
        """List of broken anchors sorted by target URL."""
        with self._lock:
            return sorted(
                (
                    replace(a, referencing_pages=list(a.referencing_pages))
                    for a in self._broken_anchors.values()
                ),
                key=lambda a: a.target_url,
            )

    # ------------------------------------------------------------------
    # Unvalidated anchors
    # ------------------------------------------------------------------

    def add_unvalidated_anchor(self, *, target_url: str, reason: str, referrer: str) -> None:
        """Record an anchor that could not be validated.

        Parameters:
            target_url: Full URL including fragment.
            reason: Why validation was skipped (``'no-crawl'``, ``'external'``,
                ``'depth-limited'``).
            referrer: Page containing the link.
        """
        with self._lock:
            if target_url not in self._unvalidated_anchors:
                self._unvalidated_anchors[target_url] = UnvalidatedAnchor(
                    target_url=target_url, reason=reason
                )
            self._append_referrer(self._unvalidated_anchors[target_url].referencing_pages, referrer)

    @property
    def unvalidated_anchors(self) -> list[UnvalidatedAnchor]:
        """List of unvalidated anchors sorted by target URL."""
        with self._lock:
            return sorted(
                (
                    replace(a, referencing_pages=list(a.referencing_pages))
                    for a in self._unvalidated_anchors.values()
                ),
                key=lambda a: a.target_url,
            )

    # ------------------------------------------------------------------
    # Non-200 responses
    # ------------------------------------------------------------------

    def add_non200(self, *, url: str, status_code: int, referrer: str) -> None:
        """Record a URL that returned a non-200 final status.

        Parameters:
            url: The URL.
            status_code: HTTP status code.
            referrer: Page that linked to the URL.
        """
        with self._lock:
            if url not in self._non200:
                self._non200[url] = Non200Response(url=url, status_code=status_code)
                for pending in self._drain_pending(url):
                    self._append_referrer(self._non200[url].referencing_pages, pending)
            self._append_referrer(self._non200[url].referencing_pages, referrer)

    @property
    def non200_responses(self) -> list[Non200Response]:
        """List of non-200 responses sorted by status code then URL."""
        with self._lock:
            return sorted(
                (
                    replace(r, referencing_pages=list(r.referencing_pages))
                    for r in self._non200.values()
                ),
                key=lambda r: (r.status_code, r.url),
            )

    # ------------------------------------------------------------------
    # Misplaced assets
    # ------------------------------------------------------------------

    def add_misplaced_asset(self, *, url: str, asset_type: str, referrer: str) -> None:
        """Record a misplaced asset.

        Parameters:
            url: The asset URL.
            asset_type: String label of the asset type.
            referrer: Page that referenced the asset.
        """
        with self._lock:
            if url not in self._misplaced_assets:
                self._misplaced_assets[url] = MisplacedAsset(url=url, asset_type=asset_type)
                for pending in self._drain_pending(url):
                    self._append_referrer(self._misplaced_assets[url].referencing_pages, pending)
            self._append_referrer(self._misplaced_assets[url].referencing_pages, referrer)

    @property
    def misplaced_assets(self) -> list[MisplacedAsset]:
        """List of misplaced assets sorted by asset type then URL."""
        with self._lock:
            return sorted(
                (
                    replace(a, referencing_pages=list(a.referencing_pages))
                    for a in self._misplaced_assets.values()
                ),
                key=lambda a: (a.asset_type, a.url),
            )

    # ------------------------------------------------------------------
    # SSL warnings
    # ------------------------------------------------------------------

    def add_ssl_warning(self, *, url: str, domain: str, error: str, referrer: str) -> None:
        """Record an SSL certificate error.

        Parameters:
            url: The URL that triggered the SSL error.
            domain: The domain of the URL.
            error: SSL error description.
            referrer: Page that referenced the URL.
        """
        with self._lock:
            if domain not in self._ssl_warnings:
                self._ssl_warnings[domain] = SslWarning(domain=domain, error=error)
            sw = self._ssl_warnings[domain]
            existing = next((t for t in sw.affected_urls if t[0] == url), None)
            if existing is None:
                pending = self._drain_pending(url)
                refs: list[str] = []
                for p in pending:
                    self._append_referrer(refs, p)
                self._append_referrer(refs, referrer)
                sw.affected_urls.append((url, refs))
            else:
                self._append_referrer(existing[1], referrer)

    @property
    def ssl_warnings(self) -> list[SslWarning]:
        """List of SSL warnings sorted by domain."""
        with self._lock:
            return sorted(
                (
                    replace(
                        s,
                        affected_urls=[(url, list(refs)) for url, refs in s.affected_urls],
                    )
                    for s in self._ssl_warnings.values()
                ),
                key=lambda s: s.domain,
            )

    # ------------------------------------------------------------------
    # Non-HTTP links
    # ------------------------------------------------------------------

    def add_non_http_link(self, *, url: str, scheme: str, referrer: str) -> None:
        """Record a non-HTTP scheme link.

        Parameters:
            url: The full non-HTTP URL.
            scheme: The URL scheme (e.g. ``'mailto'``).
            referrer: Page containing the link.
        """
        with self._lock:
            if url not in self._non_http_links:
                self._non_http_links[url] = NonHttpLink(url=url, scheme=scheme)
                for pending in self._drain_pending(url):
                    self._append_referrer(self._non_http_links[url].referencing_pages, pending)
            self._append_referrer(self._non_http_links[url].referencing_pages, referrer)

    @property
    def non_http_links(self) -> list[NonHttpLink]:
        """List of non-HTTP scheme links sorted by URL."""
        with self._lock:
            return sorted(
                (
                    replace(lk, referencing_pages=list(lk.referencing_pages))
                    for lk in self._non_http_links.values()
                ),
                key=lambda lk: lk.url,
            )

    # ------------------------------------------------------------------
    # Ignore matches
    # ------------------------------------------------------------------

    def add_ignore_match(self, *, url: str, referrer: str) -> None:
        """Record a URL that was ignored.

        Parameters:
            url: The ignored URL.
            referrer: Page containing the link.
        """
        with self._lock:
            if url not in self._ignore_matches:
                self._ignore_matches[url] = IgnoreMatch(url=url)
                for pending in self._drain_pending(url):
                    self._append_referrer(self._ignore_matches[url].referencing_pages, pending)
            self._append_referrer(self._ignore_matches[url].referencing_pages, referrer)

    @property
    def ignore_matches(self) -> list[IgnoreMatch]:
        """List of ignore matches sorted by URL."""
        with self._lock:
            return sorted(
                (
                    replace(m, referencing_pages=list(m.referencing_pages))
                    for m in self._ignore_matches.values()
                ),
                key=lambda m: m.url,
            )

    # ------------------------------------------------------------------
    # No-crawl matches
    # ------------------------------------------------------------------

    def add_no_crawl_match(self, *, url: str, referrer: str) -> None:
        """Record a URL that matched a no-crawl prefix.

        Parameters:
            url: The URL.
            referrer: Page containing the link.
        """
        with self._lock:
            if url not in self._no_crawl_matches:
                self._no_crawl_matches[url] = NoCrawlMatch(url=url)
                for pending in self._drain_pending(url):
                    self._append_referrer(self._no_crawl_matches[url].referencing_pages, pending)
            self._append_referrer(self._no_crawl_matches[url].referencing_pages, referrer)

    @property
    def no_crawl_matches(self) -> list[NoCrawlMatch]:
        """List of no-crawl matches sorted by URL."""
        with self._lock:
            return sorted(
                (
                    replace(m, referencing_pages=list(m.referencing_pages))
                    for m in self._no_crawl_matches.values()
                ),
                key=lambda m: m.url,
            )

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def record_request(
        self,
        url: str,
        *,
        bytes_downloaded: int = 0,
        crawled: bool = False,
        external: bool = False,
    ) -> None:
        """Update statistics for a completed HTTP request.

        Parameters:
            url: The URL that was requested.
            bytes_downloaded: Bytes received.
            crawled: True if the page was crawled (GET + parsed).
            external: True if the URL was external.
        """
        domain = urlparse(url).netloc
        with self._lock:
            self._statistics.total_requests += 1
            self._statistics.bytes_downloaded += bytes_downloaded
            if crawled:
                self._statistics.pages_crawled += 1
            elif not external:
                self._statistics.pages_checked += 1
            if external:
                self._statistics.external_checked += 1
            if domain:
                self._statistics.per_domain_requests[domain] = (
                    self._statistics.per_domain_requests.get(domain, 0) + 1
                )

    @property
    def statistics(self) -> CrawlStatistics:
        """Snapshot of the crawl statistics."""
        with self._lock:
            return CrawlStatistics(
                start_time=self._statistics.start_time,
                total_requests=self._statistics.total_requests,
                bytes_downloaded=self._statistics.bytes_downloaded,
                pages_crawled=self._statistics.pages_crawled,
                pages_checked=self._statistics.pages_checked,
                external_checked=self._statistics.external_checked,
                per_domain_requests=dict(self._statistics.per_domain_requests),
            )

    def has_problems(self) -> bool:
        """Return True if any crawl problems were found (exit code 1).

        Returns:
            True if there are broken links, non-200 responses, broken anchors,
            misplaced assets, or SSL warnings.
        """
        with self._lock:
            return bool(
                self._broken_links
                or self._non200
                or self._broken_anchors
                or self._misplaced_assets
                or self._ssl_warnings
            )
