"""Main link checking functionality."""

import logging
import time
import urllib.parse
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional
import concurrent.futures
import threading
import queue

import requests
from bs4 import BeautifulSoup
from bs4 import Tag

logger = logging.getLogger(__name__)


class LinkChecker:
    """Class to check links on a website and collect information about them."""

    def __init__(self,
                 root_url: str,
                 ignored_asset_paths: Optional[List[str]] = None,
                 ignored_internal_paths: Optional[List[str]] = None,
                 ignored_external_links: Optional[List[str]] = None,
                 timeout: float = 10.0,
                 max_requests: Optional[int] = None,
                 max_depth: Optional[int] = None,
                 max_threads: int = 10):
        """Initialize the link checker with a root URL.

        Args:
            root_url: The URL of the website to check.
            ignored_asset_paths: List of paths to ignore when logging internal assets.
            ignored_internal_paths: List of paths to check once but not crawl further.
            ignored_external_links: List of external URLs or URL roots to ignore in reporting.
            timeout: Timeout in seconds for HTTP requests.
            max_requests: Maximum number of requests to make (None for unlimited).
            max_depth: Maximum depth to crawl (None for unlimited).
            max_threads: Maximum number of concurrent threads for requests.
        """
        self.root_url = self._normalize_url(root_url)
        self.root_domain = urllib.parse.urlparse(self.root_url).netloc

        # Store ignored paths
        self.ignored_asset_paths = ignored_asset_paths or []
        self.ignored_internal_paths = ignored_internal_paths or []
        self.ignored_external_links = ignored_external_links or []

        # Store request limits
        self.timeout = timeout
        self.max_requests = max_requests
        self.max_depth = max_depth
        self.max_threads = max_threads
        self.request_count = 0

        # Store visited URLs to avoid duplicates
        self.visited_urls: Set[str] = set()

        # Thread safety locks
        self.visited_urls_lock = threading.Lock()
        self.request_count_lock = threading.Lock()
        self.broken_links_lock = threading.Lock()
        self.internal_assets_lock = threading.Lock()
        self.ignored_internal_assets_lock = threading.Lock()
        self.external_links_lock = threading.Lock()
        self.ignored_external_links_lock = threading.Lock()
        self.counter_lock = threading.Lock()

        # Store URLs to visit
        self.urls_to_visit: List[str] = [self.root_url]
        self.urls_to_visit_queue: queue.Queue = queue.Queue()
        self.urls_to_visit_queue.put((self.root_url, 0))  # URL and depth

        # Store broken links: {url_where_found: {broken_url: status_code}}
        self.broken_links: Dict[str, Dict[str, int]] = defaultdict(dict)

        # Store internal assets: {url_where_found: {asset_url: asset_type}}
        self.internal_assets: Dict[str, Dict[str, str]] = defaultdict(dict)

        # Store ignored internal assets: {url_where_found: {asset_url: asset_type}}
        self.ignored_internal_assets_found: Dict[str, Dict[str, str]] = defaultdict(dict)

        # Store external links: {url_where_found: set(external_urls)}
        self.external_links: Dict[str, Set[str]] = defaultdict(set)

        # Store ignored external links found:
        # {url_where_found: set(ignored_external_urls)}
        self.ignored_external_links_found: Dict[str, Set[str]] = defaultdict(set)

        # Counters for reporting
        self.non_crawled_urls_count = 0
        self.above_root_urls_count = 0
        self.internal_assets_count = 0
        self.ignored_internal_assets_count = 0
        self.external_urls_count = 0
        self.ignored_external_urls_count = 0

        # Session for making requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent':
                'link_checker/0.1.0 (+https://github.com/yourusername/link_checker)'
        })

    def _normalize_url(self, url: str) -> str:
        """Normalize the URL to avoid duplicates.

        Args:
            url: The URL to normalize.

        Returns:
            The normalized URL.
        """
        parsed = urllib.parse.urlparse(url)

        # Remove trailing slashes
        path = parsed.path
        if path.endswith('/') and path != '/':
            path = path[:-1]

        # Treat URLs without extensions as if they were pointing to /index.html
        # But only if they don't already end with a slash (which would indicate a
        # directory)
        last_segment = path.split('/')[-1] if path else ""
        if last_segment and '.' not in last_segment:
            # This is a URL like .../voyager - treat it as .../voyager/index.html for
            # deduplication
            canonical_path = path + '/index.html'

            # Check if we've seen the /index.html version and mark this as a duplicate if
            # so
            canonical_url = urllib.parse.urlunparse((
                parsed.scheme,
                parsed.netloc,
                canonical_path,
                parsed.params,
                parsed.query,
                ""  # Remove fragments
            ))

            if hasattr(self, 'visited_urls') and canonical_url in self.visited_urls:
                logger.debug(f"URL '{url}' is a duplicate of '{canonical_url}' which "
                             "has already been visited")
                return canonical_url

            # For test purposes, if we're normalizing a URL that's already been marked as
            # equivalent to index.html
            if (hasattr(self, 'visited_urls') and
                    url in self.visited_urls and
                    canonical_url in self.visited_urls):
                logger.debug(f"Both URL '{url}' and equivalent '{canonical_url}' are "
                             "already visited")
                return canonical_url

        # Remove fragments
        fragment = ''

        # Reconstruct the URL without fragments and with normalized path
        normalized = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            path,
            parsed.params,
            parsed.query,
            fragment
        ))

        return normalized

    def _is_internal_url(self, url: str) -> bool:
        """Check if the URL is internal to the website being checked.

        Args:
            url: The URL to check.

        Returns:
            True if the URL is internal, False otherwise.
        """
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc == self.root_domain or not parsed.netloc

    def _is_html_url(self, url: str) -> bool:
        """Check if the URL points to an HTML resource.

        Args:
            url: The URL to check.

        Returns:
            True if the URL points to an HTML resource, False otherwise.
        """
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.lower()

        # If no extension, assume HTML
        if '.' not in path.split('/')[-1]:
            return True

        # Check for common HTML extensions
        html_extensions = {'.html', '.htm', '.xhtml', '.php', '.asp', '.aspx', '.jsp'}
        for ext in html_extensions:
            if path.endswith(ext):
                return True

        return False

    def _get_asset_type(self, url: str) -> str:
        """Get the type of asset based on the URL.

        Args:
            url: The URL to check.

        Returns:
            The type of asset.
        """
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.lower()

        if '.' not in path.split('/')[-1]:
            return "unknown"

        extension = path.split('.')[-1]

        if extension in {'jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'ico'}:
            return "image"
        elif extension in {'css', 'js', 'json'}:
            return "web_asset"
        elif extension in {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx'}:
            return "document"
        elif extension in {'txt', 'csv', 'xml', 'tab', 'lbl'}:
            return "text"
        else:
            return extension

    def _resolve_relative_url(self, base_url: str, relative_url: str) -> str:
        """Resolve a relative URL against a base URL.

        Args:
            base_url: The base URL.
            relative_url: The relative URL.

        Returns:
            The resolved URL.
        """
        # Extract the base directory from base_url
        parsed_base = urllib.parse.urlparse(base_url)

        # Add scheme and domain to base_url if it's missing
        if not parsed_base.scheme and not parsed_base.netloc:
            if base_url.startswith('/'):
                # It's an absolute path relative to the root
                base_url = urllib.parse.urljoin(
                    f"{self.root_url.split('://', 1)[0]}://{self.root_domain}", base_url)
            else:
                # It's a relative path, so add the scheme and domain
                base_url = urllib.parse.urljoin(self.root_url, base_url)

        # Handle the case where relative_url is actually a full URL
        if '://' in relative_url:
            return self._normalize_url(relative_url)

        # If relative_url starts with '/', it's relative to the domain root
        if relative_url.startswith('/'):
            # Join with just the scheme and domain
            domain_root = (f"{parsed_base.scheme}://{parsed_base.netloc}"
                           if parsed_base.scheme else self.root_url)
            return self._normalize_url(urllib.parse.urljoin(domain_root, relative_url))

        # CRITICAL FIX: For page-relative URLs, ensure the base URL ends with a slash
        # This forces urllib.parse.urljoin to treat it as a directory
        if not relative_url.startswith('/') and not base_url.endswith('/'):
            # Check if the base_url path ends with a filename pattern
            # (contains '.' in last segment)
            path_parts = parsed_base.path.split('/')
            last_part = path_parts[-1] if path_parts else ""

            if '.' in last_part:  # It's likely a file, not a directory
                # Remove the file part to get the directory
                directory_path = '/'.join(path_parts[:-1]) + '/'
                base_url = urllib.parse.urlunparse((
                    parsed_base.scheme,
                    parsed_base.netloc,
                    directory_path,
                    parsed_base.params,
                    parsed_base.query,
                    parsed_base.fragment
                ))
            else:
                # It's a directory without a trailing slash, add one
                base_url = base_url + '/'

        # Now resolve the relative URL against the properly formatted base URL
        result = urllib.parse.urljoin(base_url, relative_url)
        # logger.debug(f"Resolved relative URL: '{relative_url}' with base
        # '{base_url}' -> '{result}'")

        return self._normalize_url(result)

    def _should_ignore_asset(self, url: str) -> bool:
        """Check if an asset URL should be ignored based on its path.

        Args:
            url: The URL to check.

        Returns:
            True if the URL should be ignored, False otherwise.
        """
        if not self.ignored_asset_paths:
            return False

        parsed = urllib.parse.urlparse(url)
        path = parsed.path

        # Ensure path starts with / for consistent matching
        if not path.startswith('/'):
            path = '/' + path

        for ignored_path in self.ignored_asset_paths:
            # Make leading slash optional in the pattern
            pattern = ignored_path
            if not pattern.startswith('/'):
                pattern = '/' + pattern

            if path.startswith(pattern):
                logger.debug(f"Asset URL '{url}' ignored for reports - matches "
                             f"pattern '{ignored_path}'")
                return True

        return False

    def _should_not_crawl(self, url: str) -> bool:
        """Check if a URL should be checked but not crawled further.

        Args:
            url: The URL to check.

        Returns:
            True if the URL should not be crawled, False otherwise.
        """
        if not self.ignored_internal_paths:
            return False

        parsed = urllib.parse.urlparse(url)
        path = parsed.path

        # Ensure path starts with / for consistent matching
        if not path.startswith('/'):
            path = '/' + path

        for ignored_path in self.ignored_internal_paths:
            # Make leading slash optional in the pattern
            pattern = ignored_path
            if not pattern.startswith('/'):
                pattern = '/' + pattern

            if path.startswith(pattern):
                logger.debug(f"URL '{url}' will not be crawled - matches pattern "
                             f"'{ignored_path}'")
                with self.counter_lock:
                    self.non_crawled_urls_count += 1
                return True

        return False

    def _should_ignore_external_link(self, url: str) -> bool:
        """Check if an external URL should be ignored based on configured patterns.

        Args:
            url: The URL to check.

        Returns:
            True if the URL should be ignored, False otherwise.
        """
        if not self.ignored_external_links:
            return False

        for ignored_link in self.ignored_external_links:
            # Full URL match
            if url == ignored_link:
                logger.debug(f"External URL '{url}' ignored - exact match with '{ignored_link}'")
                return True

            # Root match (URL starts with the ignored pattern)
            if url.startswith(ignored_link):
                logger.debug(f"External URL '{url}' ignored - starts with '{ignored_link}'")
                return True

        return False

    def _extract_links(self,
                       url: str,
                       html_content: str) -> List[str]:
        """Extract links and assets from HTML content.

        Args:
            url: The URL of the page.
            html_content: The HTML content of the page.

        Returns:
            A list of links found in the HTML content.
        """
        soup = BeautifulSoup(html_content, 'html.parser')

        links = []

        # Extract links from <a> tags
        for a_tag in soup.find_all('a', href=True):
            # Cast to Tag type to satisfy mypy
            if not isinstance(a_tag, Tag):
                continue

            href = a_tag.get('href', '')
            if not isinstance(href, str):
                href = str(href)

            # Skip anchors, javascript, and mailto links
            if (href.startswith('#') or
                    href.startswith('javascript:') or
                    href.startswith('mailto:')):
                continue

            absolute_url = self._resolve_relative_url(url, href)

            if self._is_internal_url(absolute_url):
                if self._is_html_url(absolute_url):
                    links.append(absolute_url)
                else:
                    asset_type = self._get_asset_type(absolute_url)
                    # This is an internal asset
                    if self._should_ignore_asset(absolute_url):
                        # Track ignored internal assets separately
                        with self.ignored_internal_assets_lock:
                            self.ignored_internal_assets_found[url.rstrip('/')][
                                absolute_url] = asset_type
                        with self.counter_lock:
                            self.ignored_internal_assets_count += 1
                    else:
                        # Add to internal_assets for reporting
                        with self.internal_assets_lock:
                            self.internal_assets[url.rstrip('/')][absolute_url] = asset_type
                        with self.counter_lock:
                            self.internal_assets_count += 1
            else:
                # This is an external link
                if self._should_ignore_external_link(absolute_url):
                    # Track ignored external links separately
                    with self.ignored_external_links_lock:
                        self.ignored_external_links_found[url.rstrip('/')].add(absolute_url)
                    with self.counter_lock:
                        self.ignored_external_urls_count += 1
                else:
                    # Add to external_links for reporting
                    with self.external_links_lock:
                        self.external_links[url.rstrip('/')].add(absolute_url)
                    with self.counter_lock:
                        self.external_urls_count += 1

        # Extract image sources
        for img_tag in soup.find_all('img', src=True):
            if not isinstance(img_tag, Tag):
                continue

            src = img_tag.get('src', '')
            if not isinstance(src, str):
                src = str(src)
            absolute_url = self._resolve_relative_url(url, src)
            if self._is_internal_url(absolute_url):
                if self._should_ignore_asset(absolute_url):
                    # Track ignored internal assets separately
                    with self.ignored_internal_assets_lock:
                        self.ignored_internal_assets_found[url.rstrip('/')][
                            absolute_url] = 'image'
                    with self.counter_lock:
                        self.ignored_internal_assets_count += 1
                else:
                    # Add to internal_assets for reporting
                    with self.internal_assets_lock:
                        self.internal_assets[url.rstrip('/')][absolute_url] = 'image'
                    with self.counter_lock:
                        self.internal_assets_count += 1

        # Extract CSS links
        for link_tag in soup.find_all('link', rel='stylesheet', href=True):
            if not isinstance(link_tag, Tag):
                continue

            href = link_tag.get('href', '')
            if not isinstance(href, str):
                href = str(href)
            absolute_url = self._resolve_relative_url(url, href)
            if self._is_internal_url(absolute_url):
                if self._should_ignore_asset(absolute_url):
                    # Track ignored internal assets separately
                    with self.ignored_internal_assets_lock:
                        self.ignored_internal_assets_found[url.rstrip('/')][
                            absolute_url] = 'css'
                    with self.counter_lock:
                        self.ignored_internal_assets_count += 1
                else:
                    # Add to internal_assets for reporting
                    with self.internal_assets_lock:
                        self.internal_assets[url.rstrip('/')][absolute_url] = 'css'
                    with self.counter_lock:
                        self.internal_assets_count += 1

        # Extract JavaScript sources
        for script_tag in soup.find_all('script', src=True):
            if not isinstance(script_tag, Tag):
                continue

            src = script_tag.get('src', '')
            if not isinstance(src, str):
                src = str(src)
            absolute_url = self._resolve_relative_url(url, src)
            if self._is_internal_url(absolute_url):
                if self._should_ignore_asset(absolute_url):
                    # Track ignored internal assets separately
                    with self.ignored_internal_assets_lock:
                        self.ignored_internal_assets_found[url.rstrip('/')][
                            absolute_url] = 'javascript'
                    with self.counter_lock:
                        self.ignored_internal_assets_count += 1
                else:
                    # Add to internal_assets for reporting
                    with self.internal_assets_lock:
                        self.internal_assets[url.rstrip('/')][absolute_url] = 'javascript'
                    with self.counter_lock:
                        self.internal_assets_count += 1

        return links

    def _check_url(self, url: str) -> Tuple[Optional[str], Optional[int]]:
        """Check if a URL is accessible.

        Args:
            url: The URL to check.

        Returns:
            A tuple of (content, status_code) where content is the HTML content
            of the page and status_code is the HTTP status code.
        """
        try:
            logger.debug(f"Checking URL: {url}")

            # Always add the URL being checked to the visited set
            with self.visited_urls_lock:
                self.visited_urls.add(url)

            # Use a timeout to avoid getting stuck
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            status_code = response.status_code

            # If this is a URL without an extension that redirects to index.html or has
            # a 200 status code, mark both URLs as the same for deduplication purposes
            if status_code in (200, 301, 302, 303, 307, 308):
                parsed = urllib.parse.urlparse(url)
                path = parsed.path
                last_segment = path.split('/')[-1] if path else ""

                # If this is a URL without an extension or file part
                if last_segment and '.' not in last_segment:
                    # Also mark the /index.html version as visited
                    index_url = urllib.parse.urlunparse((
                        parsed.scheme,
                        parsed.netloc,
                        path + '/index.html',
                        parsed.params,
                        parsed.query,
                        parsed.fragment
                    ))
                    with self.visited_urls_lock:
                        self.visited_urls.add(index_url)
                    logger.debug(f"Also marking {index_url} as visited")

                # If this is an index.html URL
                elif path.endswith('/index.html'):
                    # Also mark the directory version as visited
                    dir_url = urllib.parse.urlunparse((
                        parsed.scheme,
                        parsed.netloc,
                        path[:-11],  # Remove /index.html
                        parsed.params,
                        parsed.query,
                        parsed.fragment
                    ))
                    with self.visited_urls_lock:
                        self.visited_urls.add(dir_url)
                    logger.debug(f"Also marking {dir_url} as visited")

            # Check if the request was successful (status code 200)
            if status_code == 200:
                # Check if the content is HTML
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' in content_type:
                    return response.text, status_code
                else:
                    logger.debug(f"URL {url} is not HTML: {content_type}")
                    return None, status_code
            else:
                logger.error(f"Error accessing URL {url}: {status_code}")
                return None, status_code

        except requests.RequestException as e:
            logger.error(f"Error accessing URL {url}: {str(e)}")
            return None, None

    def link_checker(self) -> None:
        """Check all links on the website using multiple threads."""
        logger.info(f"Starting link checking with {self.max_threads} threads")

        # Create a semaphore to limit the number of concurrent requests
        # This ensures we don't exceed max_requests
        if self.max_requests is not None:
            request_semaphore = threading.Semaphore(self.max_requests)
        else:
            request_semaphore = threading.Semaphore(10000)  # Large value if unlimited

        # Create a thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            futures = []

            # Function to process a URL
            def process_url(url_depth_tuple):
                nonlocal futures

                # Check if we've reached the maximum number of requests
                with self.request_count_lock:
                    if self.max_requests is not None and self.request_count >= self.max_requests:
                        logger.warning(f"Reached maximum number of requests ({self.max_requests}). Stopping.")
                        return

                current_url, current_depth = url_depth_tuple
                current_url_ = current_url.rstrip('/')

                # Skip if we've reached the maximum depth
                if self.max_depth is not None and current_depth > self.max_depth:
                    logger.debug(f"Skipping URL at depth {current_depth}: {current_url}")
                    return

                # Skip already visited URLs
                with self.visited_urls_lock:
                    if current_url in self.visited_urls:
                        return

                # _check_url will add the URL to visited_urls
                logger.info(f"Visiting: {current_url}")

                # Log progress every 100 requests (at WARNING level which corresponds to verbosity 1)
                with self.request_count_lock:
                    if self.request_count % 100 == 0:
                        logging.info(f"Request #{self.request_count}: Checking URL {current_url}")

                # Acquire semaphore before making the request
                with request_semaphore:
                    html_content, status_code = self._check_url(current_url)
                    with self.request_count_lock:
                        self.request_count += 1

                if html_content is None:
                    # If the URL is not accessible, record it as a broken link
                    if status_code not in (200, None):
                        with self.broken_links_lock:
                            self.broken_links[current_url_][current_url] = \
                                status_code if status_code is not None else 0
                    return

                # Extract links and assets from the HTML content
                links = self._extract_links(current_url, html_content)

                # Add the extracted links to the URLs to visit (if within allowed hierarchy
                # and not in ignored_internal_paths)
                for link in links:
                    with self.visited_urls_lock:
                        if link in self.visited_urls:
                            continue

                    # Check what type of URL this is
                    url_category = self._categorize_url(link)

                    if url_category == 'external':
                        # External URLs are already added to external_links in _extract_links
                        pass
                    elif url_category == 'above_root':
                        # It's above the root on the same host - check it but don't crawl
                        logging.debug(f"URL '{link}' is above the root - checking existence only")
                        with self.counter_lock:
                            self.above_root_urls_count += 1

                        # Check if the URL exists to report broken links
                        with self.request_count_lock:
                            if self.request_count % 100 == 0:
                                logging.info(f"Request #{self.request_count}: Checking URL {link}")

                        # Submit a task to check this URL
                        check_future = executor.submit(self._check_url_and_record_broken,
                                                       link, current_url_, request_semaphore)
                        futures.append(check_future)
                    elif url_category == 'allowed':
                        # Only add link to urls_to_visit if it shouldn't be ignored for crawling
                        if not self._should_not_crawl(link):
                            # Add to queue with depth increased by 1
                            self.urls_to_visit_queue.put((link, current_depth + 1))
                            logging.debug(f"Added to crawl queue: {link} "
                                          f"(depth: {current_depth + 1})")
                        else:
                            # For URLs in ignored_internal_paths, check them but don't crawl
                            logging.debug(f"URL '{link}' matches ignored internal path - "
                                          "checking existence only, will not crawl further")

                            # Submit a task to check this URL
                            check_future = executor.submit(self._check_url_and_record_broken,
                                                           link, current_url_, request_semaphore)
                            futures.append(check_future)

            # Submit initial URL
            initial_future = executor.submit(process_url, (self.root_url, 0))
            futures.append(initial_future)

            # Process URLs as they are added to the queue
            while futures or not self.urls_to_visit_queue.empty():
                # Check for completed futures to free up threads
                done_futures = []
                for future in futures:
                    if future.done():
                        done_futures.append(future)
                        # Handle any exceptions
                        try:
                            future.result()  # This will re-raise any exceptions
                        except Exception as e:
                            logger.error(f"Error in thread: {str(e)}")

                # Remove completed futures
                for future in done_futures:
                    futures.remove(future)

                # Submit more tasks if queue is not empty and we haven't reached max_requests
                with self.request_count_lock:
                    requests_available = self.max_requests is None or self.request_count < self.max_requests

                if requests_available and not self.urls_to_visit_queue.empty():
                    try:
                        # Get next URL from queue (non-blocking)
                        url_depth = self.urls_to_visit_queue.get_nowait()
                        # Submit new task
                        new_future = executor.submit(process_url, url_depth)
                        futures.append(new_future)
                    except queue.Empty:
                        # Queue was empty, just continue
                        pass

                # Short sleep to avoid busy waiting
                time.sleep(0.01)

            # Wait for all futures to complete
            concurrent.futures.wait(futures)

    def _check_url_and_record_broken(self, url: str, referring_url: str, semaphore) -> None:
        """Check a URL and record it as broken if necessary.

        This is a helper method for the threaded link_checker to check URLs
        that shouldn't be crawled further.

        Args:
            url: The URL to check.
            referring_url: The URL that referred to this URL.
            semaphore: Semaphore to limit concurrent requests.
        """
        with semaphore:
            check_status = self._check_url(url)
            with self.request_count_lock:
                self.request_count += 1
                if self.request_count % 100 == 0:
                    logging.info(f"Request #{self.request_count}: Checking URL {url}")

        if check_status[1] not in (200, None):
            logging.error(f"Broken link: {url} (Status: {check_status[1]})")
            with self.broken_links_lock:
                self.broken_links[referring_url][url] = \
                    check_status[1] if check_status[1] is not None else 0
        else:
            logging.debug(f"Link exists: {url}")

    def _categorize_url(self, url: str) -> str:
        """Categorize a URL as 'allowed', 'above_root', or 'external'.

        Args:
            url: The URL to categorize.

        Returns:
            'allowed': URL is within the allowed hierarchy
            'above_root': URL is on the same host but above the root
            'external': URL is on a different host
        """
        # Parse both URLs
        root_parsed = urllib.parse.urlparse(self.root_url)
        url_parsed = urllib.parse.urlparse(url)

        # Check if it's an external URL (different domain)
        if root_parsed.netloc != url_parsed.netloc:
            return 'external'

        # Clean the paths (remove trailing slashes except for root path)
        root_path = root_parsed.path
        if root_path.endswith('/') and root_path != '/':
            root_path = root_path[:-1]

        url_path = url_parsed.path
        if url_path.endswith('/') and url_path != '/':
            url_path = url_path[:-1]

        # If root is the site root (/), everything is allowed
        if root_path == '' or root_path == '/':
            return 'allowed'

        # Check if the URL path starts with the root path
        if url_path == root_path:
            return 'allowed'  # Same path is allowed

        if url_path.startswith(root_path + '/'):
            return 'allowed'  # Subfolder or subpage is allowed

        # URL is higher in the hierarchy or in a different branch
        return 'above_root'

    def check_assets(self) -> None:
        """Check if the internal assets are accessible using multiple threads."""
        logger.info("Checking internal assets...")

        # Collect all unique asset URLs
        all_assets: Set[str] = set()

        # Regular internal assets
        for assets in self.internal_assets.values():
            all_assets.update(assets.keys())

        # Ignored internal assets
        for assets in self.ignored_internal_assets_found.values():
            all_assets.update(assets.keys())

        logger.info(f"Found {len(all_assets)} unique assets to check")

        # Create a semaphore to limit the number of concurrent requests
        # This ensures we don't exceed max_requests
        if self.max_requests is not None:
            request_semaphore = threading.Semaphore(self.max_requests)
        else:
            request_semaphore = threading.Semaphore(10000)  # Large value if unlimited

        # Create a thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            # Function to check a single asset
            def check_asset(asset_url):
                try:
                    with self.visited_urls_lock:
                        if asset_url in self.visited_urls:
                            return
                        self.visited_urls.add(asset_url)

                    try:
                        logging.debug(f"Checking asset: {asset_url}")

                        # Log progress every 100 requests (at WARNING level which corresponds to verbosity 1)
                        with self.request_count_lock:
                            if self.request_count % 100 == 0:
                                logging.info(f"Request #{self.request_count}: Checking asset {asset_url}")

                        # Use semaphore to limit concurrent requests
                        with request_semaphore:
                            response = self.session.head(asset_url, timeout=self.timeout)
                            status_code = response.status_code
                            with self.request_count_lock:
                                self.request_count += 1

                        if status_code != 200:
                            logging.warning(f"Asset not accessible: {asset_url} "
                                            f"(Status: {status_code})")

                            # Find all pages that reference this asset
                            with self.broken_links_lock:
                                # Regular assets
                                for page_url, assets in self.internal_assets.items():
                                    if asset_url in assets:
                                        self.broken_links[page_url.rstrip('/')][asset_url] = status_code

                                # Ignored assets
                                for page_url, assets in self.ignored_internal_assets_found.items():
                                    if asset_url in assets:
                                        self.broken_links[page_url.rstrip('/')][asset_url] = status_code

                    except requests.RequestException as e:
                        logger.error(f"Error accessing asset {asset_url}: {str(e)}")

                        with self.broken_links_lock:
                            # Find all pages that reference this asset
                            # Regular assets
                            for page_url, assets in self.internal_assets.items():
                                if asset_url in assets:
                                    self.broken_links[page_url.rstrip('/')][asset_url] = 0

                            # Ignored assets
                            for page_url, assets in self.ignored_internal_assets_found.items():
                                if asset_url in assets:
                                    self.broken_links[page_url.rstrip('/')][asset_url] = 0

                except Exception as e:
                    logger.error(f"Unexpected error checking asset {asset_url}: {str(e)}")

            # Submit all assets to the thread pool
            futures = [executor.submit(check_asset, asset_url) for asset_url in all_assets]

            # Wait for all futures to complete
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()  # This will re-raise any exceptions
                except Exception as e:
                    logger.error(f"Error in asset checking thread: {str(e)}")

                # Add a small delay to avoid overwhelming the server
                time.sleep(0.01)

    def check_external_links(self) -> None:
        """Check if the external links are accessible using multiple threads.

        Both regular external links and ignored external links are checked,
        though ignored ones won't appear in reports.
        """
        logger.info("Checking external links...")

        # Collect all unique external URLs to check
        all_external_urls: Set[str] = set()

        # Regular external links
        for links in self.external_links.values():
            all_external_urls.update(links)

        # Ignored external links
        for links in self.ignored_external_links_found.values():
            all_external_urls.update(links)

        logger.info(f"Found {len(all_external_urls)} unique external URLs to check")

        # Create a semaphore to limit the number of concurrent requests
        # This ensures we don't exceed max_requests
        if self.max_requests is not None:
            request_semaphore = threading.Semaphore(self.max_requests)
        else:
            request_semaphore = threading.Semaphore(10000)  # Large value if unlimited

        # Create a thread pool with a lower number of workers for external links
        # to avoid overwhelming external servers
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(self.max_threads, 5)) as executor:
            # Function to check a single external URL
            def check_external_url(ext_url):
                try:
                    with self.visited_urls_lock:
                        if ext_url in self.visited_urls:
                            return
                        self.visited_urls.add(ext_url)

                    try:
                        logging.debug(f"Checking external URL: {ext_url}")

                        # Log progress every 100 requests (at WARNING level which corresponds to verbosity 1)
                        with self.request_count_lock:
                            if self.request_count % 100 == 0:
                                logging.info(f"Request #{self.request_count}: Checking external "
                                             f"URL {ext_url}")

                        # Use semaphore to limit concurrent requests
                        with request_semaphore:
                            # Use a HEAD request first for efficiency
                            response = self.session.head(ext_url, timeout=self.timeout, allow_redirects=True)
                            status_code = response.status_code
                            with self.request_count_lock:
                                self.request_count += 1

                        # If we get a method not allowed error, try with GET instead
                        if status_code == 405:
                            logging.debug(f"HEAD request not allowed for {ext_url}, trying GET")

                            # Log progress again if needed for the GET request
                            with self.request_count_lock:
                                if self.request_count % 100 == 0:
                                    logging.info(f"Request #{self.request_count}: Checking external "
                                                 f"URL {ext_url} (GET)")

                            # Use semaphore for GET request too
                            with request_semaphore:
                                response = self.session.get(ext_url, timeout=self.timeout,
                                                            allow_redirects=True, stream=True)
                                # Close the connection to avoid reading the whole content
                                response.close()
                                status_code = response.status_code
                                with self.request_count_lock:
                                    self.request_count += 1

                        if status_code >= 400:
                            logging.warning(f"External link not accessible: {ext_url} "
                                            f"(Status: {status_code})")

                            # Find all pages that reference this external URL and record the broken link
                            with self.broken_links_lock:
                                # Regular external links
                                for page_url, links in self.external_links.items():
                                    if ext_url in links:
                                        self.broken_links[page_url][ext_url] = status_code

                                # Ignored external links
                                for page_url, links in self.ignored_external_links_found.items():
                                    if ext_url in links:
                                        self.broken_links[page_url][ext_url] = status_code

                    except requests.RequestException as e:
                        logger.error(f"Error accessing external URL {ext_url}: {str(e)}")

                        with self.broken_links_lock:
                            # Record the error for regular external links
                            for page_url, links in self.external_links.items():
                                if ext_url in links:
                                    self.broken_links[page_url][ext_url] = 0

                            # Record the error for ignored external links
                            for page_url, links in self.ignored_external_links_found.items():
                                if ext_url in links:
                                    self.broken_links[page_url][ext_url] = 0

                    # Add a small delay to avoid overwhelming external servers
                    time.sleep(0.2)

                except Exception as e:
                    logger.error(f"Unexpected error checking external URL {ext_url}: {str(e)}")

            # Submit all external URLs to the thread pool
            futures = [executor.submit(check_external_url, ext_url) for ext_url in all_external_urls]

            # Wait for all futures to complete
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()  # This will re-raise any exceptions
                except Exception as e:
                    logger.error(f"Error in external link checking thread: {str(e)}")

        logger.info(f"Finished checking {len(all_external_urls)} external URLs")

    def print_report(self) -> None:
        """Print a report of the link checker results."""
        # Print configuration
        print("=== CONFIGURATION ===")
        print(f"Root URL: {self.root_url}")
        print(f"Timeout: {self.timeout} seconds")
        print("Max requests: "
              f"{'unlimited' if self.max_requests is None else self.max_requests}")
        print(f"Max depth: {'unlimited' if self.max_depth is None else self.max_depth}")
        print(f"Max threads: {self.max_threads}")

        # Print ignored asset paths
        if self.ignored_asset_paths:
            print("\nIgnored asset paths (checked but not reported):")
            for path in sorted(self.ignored_asset_paths):
                print(f"  - {path}")
        else:
            print("\nNo asset paths ignored")

        # Print ignored internal paths
        if self.ignored_internal_paths:
            print("\nIgnored internal paths (checked but not crawled):")
            for path in sorted(self.ignored_internal_paths):
                print(f"  - {path}")
        else:
            print("\nNo internal paths excluded from crawling")

        # Print ignored external links configuration (keep this as it's useful configuration info)
        if self.ignored_external_links:
            print("\nIgnored external links (checked but not reported):")
            for link in sorted(self.ignored_external_links):
                print(f"  - {link}")
        else:
            print("\nNo external links ignored")

        # Print broken links
        if self.broken_links:
            print("\n=== BROKEN LINKS/ASSETS ===")
            for page_url, broken in self.broken_links.items():
                print(f"\nOn page: {page_url}")
                for link, status in sorted(broken.items()):
                    status_str = str(status) if status else "Connection error"
                    print(f"  - {link} (Status: {status_str})")
        else:
            print("\n=== NO BROKEN LINKS/ASSETS FOUND ===")

        # Print external links
        if self.external_links:
            print("\n=== EXTERNAL LINKS ===")
            unique_external_links = set()

            for page_url, links in sorted(self.external_links.items()):
                print(f"\nOn page: {page_url}")
                for link in sorted(links):
                    print(f"  - {link}")
                    unique_external_links.add(link)

            print(f"\nTotal unique external links: {len(unique_external_links)}")
        else:
            print("\n=== NO EXTERNAL LINKS FOUND ===")

        # Print internal assets
        print("\n=== INTERNAL ASSETS ===")

        # Group assets by type
        assets_by_type: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for page_url, assets in self.internal_assets.items():
            for asset_url, asset_type in sorted(assets.items()):
                assets_by_type[asset_type].append((asset_url, page_url))

        # Print assets grouped by type
        for asset_type, asset_list in sorted(assets_by_type.items()):
            print(f"\n{asset_type.upper()} ({len(asset_list)})")
            for asset_url, page_url in sorted(asset_list):
                print(f"  - {asset_url} (Referenced on: {page_url})")

        # Print summary
        print("\n=== SUMMARY ===")
        print(f"Total pages visited: {len(self.visited_urls)}")
        print("Broken links found: "
              f"{sum(len(links) for links in self.broken_links.values())}")

        asset_count = sum(len(assets) for assets in self.internal_assets.values())
        unique_asset_count = len({url for assets in self.internal_assets.values()
                                 for url in assets})
        print(f"Non-ignored internal assets found: {unique_asset_count} unique assets "
              f"referenced {asset_count} times")
        print(f"Ignored assets found: {self.ignored_internal_assets_count}")

        # Add external links summary
        total_external_links = sum(len(links) for links in self.external_links.values())
        num_unique_external_links = len(set(link for links in self.external_links.values()
                                            for link in links))
        print(f"External links found: {num_unique_external_links} unique links referenced "
              f"{total_external_links} times")

        # Add requests information
        print(f"\nRequests made: {self.request_count} " +
              f"(max: {'unlimited' if self.max_requests is None else self.max_requests})")
        if (self.max_requests is not None and self.request_count >= self.max_requests):
            print("Request limit reached - crawl was incomplete")

        if hasattr(self, 'above_root_urls_count') and self.above_root_urls_count > 0:
            print(f"URLs above root on same host: {self.above_root_urls_count}")

    def _is_within_allowed_hierarchy(self, url: str) -> bool:
        """Check if a URL is within the allowed hierarchy (not higher than the root URL).

        Args:
            url: The URL to check.

        Returns:
            True if the URL is within the allowed hierarchy, False otherwise.
        """
        url_category = self._categorize_url(url)
        # Both 'allowed' and 'external' URLs are considered within the allowed hierarchy
        # External URLs are handled separately in link_checker method
        return url_category == 'allowed' or url_category == 'external'

    def run(self) -> Tuple[Dict[str, Dict[str, int]], Dict[str, Dict[str, str]]]:
        """Run the link checker.

        Returns:
            A tuple of (broken_links, internal_assets).
        """
        try:
            self.link_checker()
            self.check_assets()
            self.check_external_links()
        except KeyboardInterrupt:
            logger.info("Link checking interrupted by user")

        return self.broken_links, self.internal_assets


def link_checker(url: str,
                 ignored_asset_paths: Optional[List[str]] = None,
                 ignored_internal_paths: Optional[List[str]] = None,
                 ignored_external_links: Optional[List[str]] = None,
                 timeout: float = 10.0,
                 max_requests: Optional[int] = None,
                 max_depth: Optional[int] = None,
                 max_threads: int = 10
                 ) -> Tuple[Dict[str, Dict[str, int]],
                            Dict[str, Dict[str, str]]]:
    """Check links on a website and return the results.

    Args:
        url: The URL of the website to check.
        ignored_asset_paths: List of paths to ignore when logging internal assets.
        ignored_internal_paths: List of paths to check once but not crawl further.
        ignored_external_links: List of external URLs or URL roots to ignore in reporting.
        timeout: Timeout in seconds for HTTP requests.
        max_requests: Maximum number of requests to make (None for unlimited).
        max_depth: Maximum depth to crawl (None for unlimited).
        max_threads: Maximum number of concurrent threads for requests (default: 10).

    Returns:
        A tuple of (broken_links, internal_assets).
    """
    checker = LinkChecker(url, ignored_asset_paths, ignored_internal_paths,
                          ignored_external_links, timeout=timeout,
                          max_requests=max_requests, max_depth=max_depth,
                          max_threads=max_threads)
    return checker.run()
