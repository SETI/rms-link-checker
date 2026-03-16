"""Main crawl engine with thread pool, visit-once logic, and result aggregation."""

from __future__ import annotations

import importlib.metadata
import logging
import queue
import threading
import time as _time_module
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from urllib.parse import urlparse

from link_checker.classifier import (
    UrlDisposition,
    classify_asset,
    classify_url,
    is_misplaced_asset,
)
from link_checker.config import CrawlConfig
from link_checker.html_parser import extract_anchors, extract_links
from link_checker.http_client import HttpClient, RequestResult
from link_checker.progress import ProgressReporter
from link_checker.results import CrawlResults
from link_checker.url_utils import (
    get_depth,
    get_file_extension,
    is_html_extension,
    is_http_url,
    is_same_domain,
    normalize_internal_url,
    normalize_url,
)

logger = logging.getLogger('link_checker')

_FALLBACK_VERSION = '0.0.0'
_POLL_INTERVAL = 0.01
_FUTURES_TIMEOUT = 5.0


@dataclass
class _WorkItem:
    """A URL to process, along with crawl context.

    Attributes:
        url: The URL to process (may include fragment).
        referrer: The page that linked to this URL.
        depth: Directory depth relative to root.
    """

    url: str
    referrer: str
    depth: int


class Crawler:
    """Main crawl engine.

    Uses a :class:`~concurrent.futures.ThreadPoolExecutor` to process URLs
    concurrently. Enforces visit-once semantics, depth limits, and all other
    spec 5-9 rules.

    Parameters:
        config: Crawl configuration.
        progress: Optional progress reporter to update during the crawl.
        sleep: Callable used for inter-retry pauses inside the HTTP client.
            Defaults to :func:`time.sleep`.  Pass ``lambda _: None`` in tests
            to make retries instantaneous.
    """

    def __init__(
        self,
        config: CrawlConfig,
        progress: ProgressReporter | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """Initialise the crawler.

        Parameters:
            config: Crawl configuration to use.
            progress: Optional :class:`~link_checker.progress.ProgressReporter` to call
                during the crawl.
            sleep: Optional callable for inter-retry pauses.  Defaults to
                :func:`time.sleep`.
        """
        self._config = config
        self._progress = progress
        self._root_url, _ = normalize_internal_url(config.root_url)
        self._root_path = urlparse(self._root_url).path

        try:
            version = importlib.metadata.version('rms-link-checker')
        except importlib.metadata.PackageNotFoundError:
            version = _FALLBACK_VERSION

        _sleep = sleep if sleep is not None else _time_module.sleep
        self._http = HttpClient(
            timeout=config.timeout,
            retries=config.retries,
            user_agent=f'rms-link-checker/{version}',
            sleep=_sleep,
        )

        self._results = CrawlResults()
        self._visited: set[str] = set()
        self._visited_lock = threading.Lock()
        self._anchor_registry: dict[str, frozenset[str]] = {}
        self._anchor_lock = threading.Lock()
        self._request_count = 0
        self._request_count_lock = threading.Lock()
        self._start_time = 0.0
        self._active_threads = 0
        self._active_threads_lock = threading.Lock()
        self._abort_event = threading.Event()

    def abort(self) -> None:
        """Signal the crawl to stop after in-flight requests complete.

        Safe to call from any thread (e.g. a signal handler). Already-submitted
        workers finish naturally; no new URLs are dequeued or requested.
        """
        self._abort_event.set()

    @property
    def results(self) -> CrawlResults:
        """Return the accumulated crawl results.

        May be partial if called after :meth:`abort` before :meth:`crawl`
        has returned.
        """
        return self._results

    def crawl(self) -> CrawlResults:
        """Run the full crawl starting from ``config.root_url``.

        Returns:
            :class:`~link_checker.results.CrawlResults` with all findings.
        """
        self._start_time = _time_module.time()
        root_canonical, _ = normalize_url(self._config.root_url)
        logger.debug('Crawl started: root=%s', root_canonical)
        work_queue: queue.Queue[_WorkItem] = queue.Queue()
        work_queue.put(_WorkItem(url=root_canonical, referrer='', depth=0))

        with ThreadPoolExecutor(max_workers=self._config.max_threads) as executor:
            futures_map = {}

            while True:
                while not work_queue.empty() and not self._abort_event.is_set():
                    try:
                        item = work_queue.get_nowait()
                    except queue.Empty:
                        break
                    fut = executor.submit(self._process_url, item, work_queue)
                    futures_map[fut] = item

                if not futures_map and work_queue.empty():
                    with self._active_threads_lock:
                        active = self._active_threads
                    if active == 0:
                        break

                if not futures_map:
                    # In-flight workers may still enqueue new items; wait briefly.
                    _time_module.sleep(_POLL_INTERVAL)
                    continue
                done_set, _ = wait(
                    list(futures_map), timeout=_FUTURES_TIMEOUT, return_when=FIRST_COMPLETED
                )

                if self._progress is not None:
                    with self._request_count_lock:
                        checked = self._request_count
                    with self._active_threads_lock:
                        active = self._active_threads
                    self._progress.update(
                        checked=checked,
                        queued=work_queue.qsize(),
                        active_threads=active,
                        elapsed=_time_module.time() - self._start_time,
                    )

                if not done_set:
                    continue

                for fut in done_set:
                    del futures_map[fut]
                    try:
                        fut.result()
                    except Exception:
                        logger.exception('Unhandled exception in worker')

        logger.debug(
            'Crawl finished: %d requests in %.1fs',
            self._request_count,
            _time_module.time() - self._start_time,
        )
        return self._results

    def _increment_request_count(self) -> bool:
        """Atomically increment request count. Returns False if max reached or aborted."""
        if self._abort_event.is_set():
            return False
        if self._config.max_requests is None:
            with self._request_count_lock:
                self._request_count += 1
            return True
        with self._request_count_lock:
            if self._request_count >= self._config.max_requests:
                return False
            self._request_count += 1
            return True

    def _mark_visited(self, canonical: str) -> bool:
        """Mark *canonical* as visited. Returns False if already visited."""
        with self._visited_lock:
            if canonical in self._visited:
                return False
            self._visited.add(canonical)
            return True

    def _merge_referrer(self, canonical: str, referrer: str) -> None:
        """Associate *referrer* with any existing result entry for *canonical*.

        Called when a URL is encountered again after its first fetch has
        already completed (or is in-flight).  All result buckets that
        track *canonical* receive the new referrer so reports show every
        page that links to a broken/redirecting/etc. URL.

        Parameters:
            canonical: Normalised URL whose existing result to update.
            referrer: Page that contained the link to *canonical*.
        """
        if not referrer:
            return
        self._results.merge_referrer(canonical, referrer)

    def _process_url(
        self,
        item: _WorkItem,
        work_queue: queue.Queue[_WorkItem],
    ) -> None:
        """Process a single work item.

        Classifies the URL, issues the appropriate HTTP request, and enqueues
        newly discovered links.

        Parameters:
            item: The work item to process.
            work_queue: Queue to add newly discovered URLs to.
        """
        try:
            with self._active_threads_lock:
                self._active_threads += 1
            self._process_url_inner(item, work_queue)
        finally:
            with self._active_threads_lock:
                self._active_threads -= 1

    def _process_url_inner(
        self,
        item: _WorkItem,
        work_queue: queue.Queue[_WorkItem],
    ) -> None:
        """Inner body of :meth:`_process_url`."""
        raw_url = item.url
        referrer = item.referrer
        depth = item.depth

        parsed = urlparse(raw_url)
        fragment = parsed.fragment or None
        url_no_frag = raw_url.split('#')[0] if '#' in raw_url else raw_url

        canonical, _ = normalize_url(url_no_frag)
        if is_same_domain(canonical, self._root_url):
            canonical, _ = normalize_internal_url(url_no_frag)

        with self._visited_lock:
            already = canonical in self._visited

        if already:
            self._merge_referrer(canonical, referrer)
            if fragment:
                logger.debug('Already visited %s; validating anchor #%s', canonical, fragment)
                self._validate_anchor(
                    page_url=canonical,
                    fragment=fragment,
                    full_url=url_no_frag + '#' + fragment,
                    referrer=referrer,
                )
            else:
                logger.debug('Already visited %s; skipping', canonical)
            return

        disposition = classify_url(
            url_no_frag,
            config=self._config,
            root_url=self._root_url,
            root_path=self._root_path,
            visited_set=self._visited,
            depth=depth,
        )
        logger.debug(
            'Disposition %s → %s (depth=%d, ref=%s)',
            url_no_frag,
            disposition.name,
            depth,
            referrer or '<root>',
        )

        if disposition == UrlDisposition.NON_HTTP:
            scheme = urlparse(raw_url).scheme
            logger.debug('Non-HTTP link %s (scheme: %s)', raw_url, scheme)
            self._results.add_non_http_link(raw_url, scheme, referrer)
            return

        if disposition == UrlDisposition.IGNORED:
            logger.debug('Ignored %s', url_no_frag)
            self._results.add_ignore_match(url_no_frag, referrer)
            return

        if not self._mark_visited(canonical):
            self._merge_referrer(canonical, referrer)
            if fragment:
                self._validate_anchor(
                    page_url=canonical,
                    fragment=fragment,
                    full_url=url_no_frag + '#' + fragment,
                    referrer=referrer,
                )
            return

        if not self._increment_request_count():
            logger.debug('Max requests reached; skipping %s', canonical)
            return

        if disposition == UrlDisposition.INTERNAL_CRAWL:
            self._handle_internal_crawl(
                url=canonical,
                referrer=referrer,
                depth=depth,
                fragment=fragment,
                work_queue=work_queue,
            )
        elif disposition == UrlDisposition.INTERNAL_ASSET:
            self._handle_asset(canonical, referrer)
        elif disposition == UrlDisposition.NO_CRAWL:
            logger.debug('No-crawl HEAD %s', canonical)
            result = self._http.request(canonical, method='HEAD')
            self._record_result(result, canonical, referrer, is_external=False)
            self._results.record_request(canonical)
            self._results.add_no_crawl_match(canonical, referrer)
            if fragment:
                self._results.add_unvalidated_anchor(
                    canonical + '#' + fragment, 'no-crawl', referrer
                )
        elif disposition in (UrlDisposition.EXTERNAL, UrlDisposition.DEPTH_LIMITED):
            reason = 'external' if disposition == UrlDisposition.EXTERNAL else 'depth-limited'
            logger.debug('%s HEAD %s', reason.capitalize(), canonical)
            result = self._http.request(canonical, method='HEAD')
            self._record_result(result, canonical, referrer, is_external=True)
            self._results.record_request(canonical, external=True)
            if fragment:
                self._results.add_unvalidated_anchor(canonical + '#' + fragment, reason, referrer)

    def _handle_internal_crawl(
        self,
        *,
        url: str,
        referrer: str,
        depth: int,
        fragment: str | None,
        work_queue: queue.Queue[_WorkItem],
    ) -> None:
        """Fetch and parse an internal HTML page, enqueue discovered links.

        Issues a GET request for *url*, records the result, extracts all links
        and anchors, and adds newly discovered URLs to *work_queue*.

        Parameters:
            url: Canonical URL of the internal page to crawl.
            referrer: Page that linked to this URL.
            depth: Directory depth of this page relative to the crawl root.
            fragment: Fragment identifier from the original link, if any.
            work_queue: Queue to push newly discovered work items onto.
        """
        result = self._http.request(url, method='GET')
        logger.debug(
            'Response %s → %d (%d bytes)',
            url,
            result.status_code,
            result.bytes_downloaded,
        )
        self._record_result(result, url, referrer, is_external=False)
        self._results.record_request(url, bytes_downloaded=result.bytes_downloaded, crawled=True)

        if result.error or result.status_code not in range(200, 300) or result.body is None:
            if fragment:
                self._results.add_unvalidated_anchor(url + '#' + fragment, 'error', referrer)
            return

        anchors = extract_anchors(result.body)
        logger.debug('Found %d anchors on %s', len(anchors), url)
        with self._anchor_lock:
            self._anchor_registry[url] = anchors

        if fragment:
            self._validate_anchor(
                page_url=url,
                fragment=fragment,
                full_url=url + '#' + fragment,
                referrer=referrer,
            )

        links = extract_links(result.body, result.final_url)
        logger.debug('Found %d links on %s', len(links), url)

        for link in links:
            link_url = link.url
            if not is_http_url(link_url):
                scheme = urlparse(link_url).scheme
                self._results.add_non_http_link(link_url, scheme, url)
                continue

            link_no_frag = link_url.split('#')[0] if '#' in link_url else link_url
            link_canonical, _ = normalize_url(link_no_frag)
            link_depth = get_depth(urlparse(link_canonical).path, self._root_path)

            work_queue.put(
                _WorkItem(
                    url=link_url,
                    referrer=url,
                    depth=link_depth,
                )
            )

            ext = get_file_extension(link_canonical)
            if ext and not is_html_extension(ext) and is_misplaced_asset(
                link_canonical,
                config=self._config,
                root_url=self._root_url,
                root_path=self._root_path,
            ):
                asset_type = classify_asset(ext)
                self._results.add_misplaced_asset(link_canonical, asset_type.value, url)

    def _handle_asset(self, url: str, referrer: str) -> None:
        """Issue a HEAD request for an internal asset and record the result.

        Parameters:
            url: Canonical URL of the internal asset.
            referrer: Page that referenced this asset.
        """
        logger.debug('Checking internal asset HEAD %s', url)
        result = self._http.request(url, method='HEAD')
        logger.debug('Response %s → %d', url, result.status_code)
        self._record_result(result, url, referrer, is_external=False)
        self._results.record_request(url)

    def _record_result(
        self,
        result: RequestResult,
        url: str,
        referrer: str,
        *,
        is_external: bool,
    ) -> None:
        """Classify a completed HTTP result and store it in :attr:`_results`.

        Handles network errors, SSL errors, redirects, HTTP 4xx/5xx errors,
        and non-200 responses — each goes into the appropriate result bucket.

        Parameters:
            result: The completed HTTP request result.
            url: Canonical URL that was requested.
            referrer: Page that linked to *url*.
            is_external: Whether the URL is on a different domain.
        """
        if result.error and result.status_code == 0:
            domain = urlparse(url).netloc
            if domain in self._http.ssl_warned_domains:
                logger.debug('SSL error %s: %s', url, result.error)
                self._results.add_ssl_warning(
                    url=url, domain=domain, error=result.error, referrer=referrer
                )
            else:
                logger.debug('Network error %s: %s', url, result.error)
                self._results.add_broken_link(
                    url=url, status_code=0, error=result.error, referrer=referrer
                )
            return

        if result.redirect_chain:
            final_canonical, _ = normalize_url(result.final_url)
            if url != final_canonical:
                redirect_status = result.redirect_chain[0].status_code
                logger.debug('Redirect %s → %s (%d)', url, result.final_url, redirect_status)
                self._results.add_redirect(
                    original_url=url,
                    final_url=result.final_url,
                    status_code=redirect_status,
                    referrer=referrer,
                )

        if result.error:
            domain = urlparse(url).netloc
            if domain in self._http.ssl_warned_domains:
                logger.debug('SSL error %s: %s', url, result.error)
                self._results.add_ssl_warning(
                    url=url, domain=domain, error=result.error, referrer=referrer
                )
            else:
                logger.debug('Error %s: %s', url, result.error)
                self._results.add_broken_link(
                    url=url,
                    status_code=result.status_code,
                    error=result.error,
                    referrer=referrer,
                )
        elif result.status_code >= 400:
            logger.debug('Broken link %s status=%d', url, result.status_code)
            self._results.add_broken_link(
                url=url,
                status_code=result.status_code,
                error=f'{result.status_code}',
                referrer=referrer,
            )

        if result.status_code != 200 and result.status_code != 0:
            self._results.add_non200(url, result.status_code, referrer)

    def _validate_anchor(
        self,
        *,
        page_url: str,
        fragment: str,
        full_url: str,
        referrer: str,
    ) -> None:
        """Check whether *fragment* exists as an anchor on *page_url*.

        Records a broken anchor if the fragment is absent.  If the page's
        anchors are not yet in :attr:`_anchor_registry` (e.g. it was not
        crawled), the check is silently skipped.

        Parameters:
            page_url: Canonical URL of the page that should define the anchor.
            fragment: Fragment identifier to look up (without the ``#``).
            full_url: Original URL including the fragment, used in reports.
            referrer: Page that contained the link with the fragment.
        """
        with self._anchor_lock:
            anchors = self._anchor_registry.get(page_url)
        if anchors is not None:
            if fragment not in anchors:
                logger.debug('Broken anchor #%s on %s', fragment, page_url)
                self._results.add_broken_anchor(full_url, referrer)
            else:
                logger.debug('Anchor #%s on %s OK', fragment, page_url)
        else:
            logger.debug(
                'Anchor %s on %s cannot be validated (page not crawled)', fragment, page_url
            )
