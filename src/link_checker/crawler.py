"""Main crawl engine with thread pool, visit-once logic, and result aggregation."""

from __future__ import annotations

import importlib.metadata
import logging
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlparse

from link_checker.classifier import (
    UrlDisposition,
    classify_asset,
    classify_url,
    is_misplaced_asset,
)
from link_checker.config import CrawlConfig
from link_checker.html_parser import extract_anchors, extract_links, find_base_href
from link_checker.http_client import HttpClient, RequestResult
from link_checker.results import CrawlResults
from link_checker.url_utils import (
    get_depth,
    get_file_extension,
    is_http_url,
    normalize_url,
)

logger = logging.getLogger('link_checker')


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

    Args:
        config: Crawl configuration.
    """

    def __init__(self, config: CrawlConfig) -> None:
        """Initialise the crawler.

        Args:
            config: Crawl configuration to use.
        """
        self._config = config
        self._root_url, _ = normalize_url(config.root_url)
        self._root_path = urlparse(self._root_url).path

        try:
            version = importlib.metadata.version('rms-link-checker')
        except importlib.metadata.PackageNotFoundError:
            version = '0.0.0'

        self._http = HttpClient(
            timeout=config.timeout,
            retries=config.retries,
            user_agent=f'rms-link-checker/{version}',
        )

        self._results = CrawlResults()
        self._visited: set[str] = set()
        self._visited_lock = threading.Lock()
        self._anchor_registry: dict[str, frozenset[str]] = {}
        self._anchor_lock = threading.Lock()
        self._request_count = 0
        self._request_count_lock = threading.Lock()

    def crawl(self) -> CrawlResults:
        """Run the full crawl starting from ``config.root_url``.

        Returns:
            :class:`~link_checker.results.CrawlResults` with all findings.
        """
        root_canonical, _ = normalize_url(self._config.root_url)
        work_queue: queue.Queue[_WorkItem] = queue.Queue()
        work_queue.put(_WorkItem(url=root_canonical, referrer='', depth=0))

        with ThreadPoolExecutor(max_workers=self._config.max_threads) as executor:
            futures_map = {}
            submitted: set[str] = set()

            while True:
                while not work_queue.empty():
                    try:
                        item = work_queue.get_nowait()
                    except queue.Empty:
                        break
                    canonical, _ = normalize_url(item.url)
                    if canonical in submitted:
                        continue
                    submitted.add(canonical)
                    fut = executor.submit(self._process_url, item, work_queue)
                    futures_map[fut] = item

                if not futures_map:
                    break

                done = []
                for fut in list(futures_map):
                    if fut.done():
                        done.append(fut)

                if not done:
                    time.sleep(0.01)
                    continue

                for fut in done:
                    del futures_map[fut]
                    try:
                        fut.result()
                    except Exception as exc:
                        logger.error('Unhandled exception in worker: %s', exc)

        return self._results

    def _increment_request_count(self) -> bool:
        """Atomically increment request count. Returns False if max reached."""
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

    def _process_url(
        self,
        item: _WorkItem,
        work_queue: queue.Queue[_WorkItem],
    ) -> None:
        """Process a single work item.

        Classifies the URL, issues the appropriate HTTP request, and enqueues
        newly discovered links.

        Args:
            item: The work item to process.
            work_queue: Queue to add newly discovered URLs to.
        """
        raw_url = item.url
        referrer = item.referrer
        depth = item.depth

        parsed = urlparse(raw_url)
        fragment = parsed.fragment or None
        url_no_frag = raw_url.split('#')[0] if '#' in raw_url else raw_url

        canonical, _ = normalize_url(url_no_frag)

        with self._visited_lock:
            already = canonical in self._visited

        if already:
            if fragment:
                self._validate_anchor(canonical, fragment, url_no_frag + '#' + fragment, referrer)
            return

        disposition = classify_url(
            url_no_frag,
            config=self._config,
            root_url=self._root_url,
            root_path=self._root_path,
            visited_set=self._visited,
            depth=depth,
        )

        if disposition == UrlDisposition.NON_HTTP:
            scheme = urlparse(raw_url).scheme
            self._results.add_non_http_link(raw_url, scheme, referrer)
            return

        if disposition == UrlDisposition.IGNORED:
            self._results.add_ignore_match(url_no_frag, referrer)
            return

        if not self._mark_visited(canonical):
            if fragment:
                self._validate_anchor(canonical, fragment, url_no_frag + '#' + fragment, referrer)
            return

        if not self._increment_request_count():
            return

        if disposition == UrlDisposition.INTERNAL_CRAWL:
            self._handle_internal_crawl(canonical, referrer, depth, fragment, work_queue)
        elif disposition == UrlDisposition.INTERNAL_ASSET:
            self._handle_asset(canonical, referrer)
        elif disposition == UrlDisposition.NO_CRAWL:
            result = self._http.request(canonical, method='HEAD')
            self._record_result(result, canonical, referrer, is_external=False)
            self._results.add_no_crawl_match(canonical, referrer)
            if fragment:
                self._results.add_unvalidated_anchor(
                    canonical + '#' + fragment, 'no-crawl', referrer
                )
        elif disposition in (UrlDisposition.EXTERNAL, UrlDisposition.DEPTH_LIMITED):
            reason = 'external' if disposition == UrlDisposition.EXTERNAL else 'depth-limited'
            result = self._http.request(canonical, method='HEAD')
            self._record_result(result, canonical, referrer, is_external=True)
            self._results.record_request(canonical, external=True)
            if fragment:
                self._results.add_unvalidated_anchor(canonical + '#' + fragment, reason, referrer)

    def _handle_internal_crawl(
        self,
        url: str,
        referrer: str,
        depth: int,
        fragment: str | None,
        work_queue: queue.Queue[_WorkItem],
    ) -> None:
        result = self._http.request(url, method='GET')
        self._record_result(result, url, referrer, is_external=False)
        self._results.record_request(url, bytes_downloaded=result.bytes_downloaded, crawled=True)

        if result.error or result.status_code not in range(200, 300) or result.body is None:
            if fragment:
                self._results.add_unvalidated_anchor(url + '#' + fragment, 'error', referrer)
            return

        anchors = extract_anchors(result.body)
        with self._anchor_lock:
            self._anchor_registry[url] = anchors

        if fragment:
            self._validate_anchor(url, fragment, url + '#' + fragment, referrer)

        base_href = find_base_href(result.body)
        links = extract_links(result.body, url, base_url=base_href)

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

            if link.is_asset and is_misplaced_asset(
                link_canonical,
                config=self._config,
                root_url=self._root_url,
                root_path=self._root_path,
            ):
                ext = get_file_extension(link_canonical)
                if ext:
                    asset_type = classify_asset(ext)
                    self._results.add_misplaced_asset(link_canonical, asset_type.value, url)

    def _handle_asset(self, url: str, referrer: str) -> None:
        result = self._http.request(url, method='HEAD')
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
        if result.error and not result.status_code:
            domain = urlparse(url).netloc
            if domain in self._http.ssl_warned_domains:
                self._results.add_ssl_warning(url, domain, result.error, referrer)
            else:
                self._results.add_broken_link(url, 0, result.error, referrer)
                self._results.add_non200(url, 0, referrer)
            return

        if result.redirect_chain:
            self._results.add_redirect(url, result.final_url, result.status_code, referrer)

        if result.status_code >= 400:
            self._results.add_broken_link(
                url, result.status_code, f'{result.status_code}', referrer
            )

        if result.status_code != 200 and result.status_code != 0:
            self._results.add_non200(url, result.status_code, referrer)

        if result.error:
            domain = urlparse(url).netloc
            if domain in self._http.ssl_warned_domains:
                self._results.add_ssl_warning(url, domain, result.error, referrer)
            else:
                self._results.add_broken_link(url, result.status_code, result.error, referrer)

    def _validate_anchor(
        self,
        page_url: str,
        fragment: str,
        full_url: str,
        referrer: str,
    ) -> None:
        with self._anchor_lock:
            anchors = self._anchor_registry.get(page_url)
        if anchors is not None:
            if fragment not in anchors:
                self._results.add_broken_anchor(full_url, referrer)
        else:
            logger.debug(
                'Anchor %s on %s cannot be validated (page not crawled)', fragment, page_url
            )


def _is_html_content_type(content_type: str) -> bool:
    """Return True if *content_type* indicates HTML.

    Args:
        content_type: Value of the Content-Type header.

    Returns:
        True for text/html content types.
    """
    return 'text/html' in content_type.lower()
