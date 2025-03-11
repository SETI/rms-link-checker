"""Main link checking functionality."""

import logging
import time
import urllib.parse
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional

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
                 timeout: float = 10.0,
                 max_requests: Optional[int] = None,
                 max_depth: Optional[int] = None):
        """Initialize the link checker with a root URL.

        Args:
            root_url: The URL of the website to check.
            ignored_asset_paths: List of paths to ignore when logging internal assets.
            ignored_internal_paths: List of paths to check once but not crawl further.
            timeout: Timeout in seconds for HTTP requests.
            max_requests: Maximum number of requests to make (None for unlimited).
            max_depth: Maximum depth to crawl (None for unlimited).
        """
        self.root_url = self._normalize_url(root_url)
        self.root_domain = urllib.parse.urlparse(self.root_url).netloc

        # Store ignored paths
        self.ignored_asset_paths = ignored_asset_paths or []
        self.ignored_internal_paths = ignored_internal_paths or []

        # Store request limits
        self.timeout = timeout
        self.max_requests = max_requests
        self.max_depth = max_depth
        self.request_count = 0

        # Store visited URLs to avoid duplicates
        self.visited_urls: Set[str] = set()

        # Store URLs to visit
        self.urls_to_visit: List[str] = [self.root_url]

        # Store broken links: {url_where_found: {broken_url: status_code}}
        self.broken_links: Dict[str, Dict[str, int]] = defaultdict(dict)

        # Store internal assets: {url_where_found: {asset_url: asset_type}}
        self.internal_assets: Dict[str, Dict[str, str]] = defaultdict(dict)

        # Counters for reporting
        self.ignored_asset_urls_count = 0
        self.non_crawled_urls_count = 0

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
                logger.debug(f"Asset URL '{url}' ignored - matches "
                             f"pattern '{ignored_path}'")
                self.ignored_asset_urls_count += 1
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
                self.non_crawled_urls_count += 1
                return True

        return False

    def _extract_links(self,
                       url: str,
                       html_content: str) -> Tuple[List[str], Dict[str, str]]:
        """Extract links and assets from HTML content.

        Args:
            url: The URL of the page.
            html_content: The HTML content of the page.

        Returns:
            A tuple of (links, assets) where links is a list of URLs and
            assets is a dictionary mapping asset URLs to asset types.
        """
        soup = BeautifulSoup(html_content, 'html.parser')

        links = []
        assets = {}

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
                elif not self._should_ignore_asset(absolute_url):
                    assets[absolute_url] = self._get_asset_type(absolute_url)
                else:
                    # Log when asset is ignored
                    logger.debug(
                        f"Ignoring asset URL '{absolute_url}' (matched ignore pattern)")

        # Extract image sources
        for img_tag in soup.find_all('img', src=True):
            if not isinstance(img_tag, Tag):
                continue

            src = img_tag.get('src', '')
            if not isinstance(src, str):
                src = str(src)
            absolute_url = self._resolve_relative_url(url, src)
            if (self._is_internal_url(absolute_url) and
                    not self._should_ignore_asset(absolute_url)):
                assets[absolute_url] = 'image'

        # Extract CSS links
        for link_tag in soup.find_all('link', rel='stylesheet', href=True):
            if not isinstance(link_tag, Tag):
                continue

            href = link_tag.get('href', '')
            if not isinstance(href, str):
                href = str(href)
            absolute_url = self._resolve_relative_url(url, href)
            if (self._is_internal_url(absolute_url) and
                    not self._should_ignore_asset(absolute_url)):
                assets[absolute_url] = 'css'

        # Extract JavaScript sources
        for script_tag in soup.find_all('script', src=True):
            if not isinstance(script_tag, Tag):
                continue

            src = script_tag.get('src', '')
            if not isinstance(src, str):
                src = str(src)
            absolute_url = self._resolve_relative_url(url, src)
            if (self._is_internal_url(absolute_url) and
                    not self._should_ignore_asset(absolute_url)):
                assets[absolute_url] = 'javascript'

        return links, assets

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
        """Check all links on the website."""
        # Add counter for URLs outside allowed hierarchy
        self.urls_outside_hierarchy_count = 0
        # Track URL depths
        url_depths = {self.root_url: 0}

        while self.urls_to_visit:
            # Check if we've reached the maximum number of requests
            if self.max_requests is not None and self.request_count >= self.max_requests:
                logging.warning(f"Reached maximum number of requests ({self.max_requests}). Stopping.")
                break

            current_url = self.urls_to_visit.pop(0)
            current_depth = url_depths.get(current_url, 0)

            # Skip if we've reached the maximum depth
            if self.max_depth is not None and current_depth > self.max_depth:
                logging.debug(f"Skipping URL at depth {current_depth}: {current_url}")
                continue

            # Skip already visited URLs
            if current_url in self.visited_urls:
                continue

            # _check_url will add the URL to visited_urls
            logger.info(f"Visiting: {current_url}")
            html_content, status_code = self._check_url(current_url)
            self.request_count += 1

            if html_content is None:
                # If the URL is not accessible, record it as a broken link
                if status_code not in (200, None):
                    self.broken_links[current_url][current_url] = \
                        status_code if status_code is not None else 0
                continue

            # Extract links and assets from the HTML content
            links, assets = self._extract_links(current_url, html_content)

            # Add the extracted links to the URLs to visit (if within allowed hierarchy
            # and not in ignored_internal_paths)
            for link in links:
                if link not in self.visited_urls and link not in self.urls_to_visit:
                    # First check if the URL is within the allowed hierarchy
                    if not self._is_within_allowed_hierarchy(link):
                        logging.debug(f"Not crawling URL '{link}' - outside allowed "
                                      f"hierarchy from root '{self.root_url}'")
                        self.urls_outside_hierarchy_count += 1

                        # We still check if the URL exists to report broken links
                        check_status = self._check_url(link)
                        self.request_count += 1
                        if check_status[1] not in (200, None):
                            logging.error("Broken link outside allowed hierarchy: "
                                          f"{link} (Status: {check_status[1]})")
                            self.broken_links[current_url][link] = \
                                check_status[1] if check_status[1] is not None else 0

                        # No need to mark as visited, _check_url already did that
                        continue

                    # Only add link to urls_to_visit if it shouldn't be ignored for
                    # crawling
                    if not self._should_not_crawl(link):
                        self.urls_to_visit.append(link)
                        # Track the depth of this URL
                        url_depths[link] = current_depth + 1
                        logging.debug(f"Added to crawl queue: {link} "
                                      f"(depth: {current_depth + 1})")
                    else:
                        # For URLs in ignored_internal_paths, check them but don't crawl
                        logging.debug(f"URL '{link}' matches ignored internal path - "
                                      "checking existence only, will not crawl further")
                        # We still need to check the URL to ensure it exists
                        check_status = self._check_url(link)
                        self.request_count += 1
                        if check_status[1] not in (200, None):
                            logging.error(f"Broken link in non-crawled section: {link} "
                                          f"(Status: {check_status[1]})")
                            self.broken_links[current_url][link] = \
                                check_status[1] if check_status[1] is not None else 0
                        else:
                            logging.debug(f"Non-crawled link exists: {link}")
                        # No need to mark as visited, _check_url already did that

            # Add the extracted assets to the internal assets
            for asset_url, asset_type in assets.items():
                self.internal_assets[current_url.rstrip('/')][asset_url] = asset_type

            # Add a small delay to avoid overwhelming the server
            time.sleep(0.1)

    def check_assets(self) -> None:
        """Check if the internal assets are accessible."""
        logger.info("Checking internal assets...")

        # Collect all unique asset URLs
        all_assets: Set[str] = set()
        for assets in self.internal_assets.values():
            all_assets.update(assets.keys())

        # Check each asset
        for asset_url in all_assets:
            try:
                if asset_url in self.visited_urls:
                    continue

                self.visited_urls.add(asset_url)

                try:
                    logging.debug(f"Checking asset: {asset_url}")

                    response = self.session.head(asset_url, timeout=self.timeout)
                    status_code = response.status_code

                    if status_code != 200:
                        logging.warning(f"Asset not accessible: {asset_url} "
                                        f"(Status: {status_code})")

                        # Find all pages that reference this asset
                        for page_url, assets in self.internal_assets.items():
                            if asset_url in assets:
                                self.broken_links[page_url][asset_url] = status_code

                except requests.RequestException as e:
                    logger.error(f"Error accessing asset {asset_url}: {str(e)}")

                    # Find all pages that reference this asset
                    for page_url, assets in self.internal_assets.items():
                        if asset_url in assets:
                            self.broken_links[page_url][asset_url] = 0

                    # Add a small delay to avoid overwhelming the server
                    time.sleep(0.1)

            except requests.RequestException as e:
                logger.error(f"Error accessing asset {asset_url}: {str(e)}")

                # Find all pages that reference this asset
                for page_url, assets in self.internal_assets.items():
                    if asset_url in assets:
                        self.broken_links[page_url][asset_url] = 0

                # Add a small delay to avoid overwhelming the server
                time.sleep(0.1)

    def run(self) -> Tuple[Dict[str, Dict[str, int]], Dict[str, Dict[str, str]]]:
        """Run the link checker.

        Returns:
            A tuple of (broken_links, internal_assets).
        """
        try:
            self.link_checker()
            self.check_assets()
        except KeyboardInterrupt:
            logger.info("Link checking interrupted by user")

        return self.broken_links, self.internal_assets

    def print_report(self) -> None:
        """Print a report of the link checker results."""
        # Print configuration
        print("=== CONFIGURATION ===")
        print(f"Root URL: {self.root_url}")
        print(f"Timeout: {self.timeout} seconds")
        print(f"Max requests: {'unlimited' if self.max_requests is None else self.max_requests}")
        print(f"Max depth: {'unlimited' if self.max_depth is None else self.max_depth}")

        # Print ignored asset paths
        if self.ignored_asset_paths:
            print("\nIgnored asset paths:")
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

        # Print broken links
        if self.broken_links:
            print("\n=== BROKEN LINKS ===")
            for page_url, broken in self.broken_links.items():
                print(f"\nOn page: {page_url}")
                for link, status in broken.items():
                    status_str = str(status) if status else "Connection error"
                    print(f"  - {link} (Status: {status_str})")
        else:
            print("\n=== NO BROKEN LINKS FOUND ===")

        # Print internal assets
        print("\n=== INTERNAL ASSETS ===")

        # Group assets by type
        assets_by_type: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for page_url, assets in self.internal_assets.items():
            for asset_url, asset_type in assets.items():
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
        print(f"Internal assets found: {unique_asset_count} unique assets referenced "
              f"{asset_count} times")

        # Add requests information
        print(f"\nRequests made: {self.request_count} " +
              f"(max: {'unlimited' if self.max_requests is None else self.max_requests})")
        if (self.max_requests is not None and
            hasattr(self, 'request_count') and
            self.request_count >= self.max_requests):
            print("Request limit reached - crawl was incomplete")

        # Add summary of ignored items if applicable
        if (hasattr(self, 'ignored_asset_urls_count') and
                self.ignored_asset_urls_count > 0):
            print(f"Assets ignored due to path patterns: {self.ignored_asset_urls_count}")

        if hasattr(self, 'non_crawled_urls_count') and self.non_crawled_urls_count > 0:
            print(f"URLs checked but not crawled: {self.non_crawled_urls_count}")

        if (hasattr(self, 'urls_outside_hierarchy_count') and
                self.urls_outside_hierarchy_count > 0):
            print(f"URLs outside allowed hierarchy: {self.urls_outside_hierarchy_count}")

    def _is_within_allowed_hierarchy(self, url: str) -> bool:
        """Check if a URL is within the allowed hierarchy (not higher than the root URL).

        Args:
            url: The URL to check.

        Returns:
            True if the URL is within the allowed hierarchy, False otherwise.
        """
        # Parse both URLs
        root_parsed = urllib.parse.urlparse(self.root_url)
        url_parsed = urllib.parse.urlparse(url)

        # If it's a different domain, hierarchy doesn't matter
        if root_parsed.netloc != url_parsed.netloc:
            return True  # External URLs are handled separately

        # Clean the paths (remove trailing slashes except for root path)
        root_path = root_parsed.path
        if root_path.endswith('/') and root_path != '/':
            root_path = root_path[:-1]

        url_path = url_parsed.path
        if url_path.endswith('/') and url_path != '/':
            url_path = url_path[:-1]

        # If root is the site root (/), everything is allowed
        if root_path == '':
            return True

        # Check if the URL path starts with the root path
        if url_path == root_path:
            return True  # Same path is allowed

        if url_path.startswith(root_path + '/'):
            return True  # Subfolder or subpage is allowed

        # URL is higher in the hierarchy or in a different branch
        logger.debug(f"URL '{url}' is outside the allowed hierarchy "
                     f"(root: '{self.root_url}')")
        return False


def link_checker(url: str,
                 ignored_asset_paths: Optional[List[str]] = None,
                 ignored_internal_paths: Optional[List[str]] = None,
                 timeout: float = 10.0,
                 max_requests: Optional[int] = None,
                 max_depth: Optional[int] = None
                 ) -> Tuple[Dict[str, Dict[str, int]],
                            Dict[str, Dict[str, str]]]:
    """Check links on a website and return the results.

    Args:
        url: The URL of the website to check.
        ignored_asset_paths: List of paths to ignore when logging internal assets.
        ignored_internal_paths: List of paths to check once but not crawl further.
        timeout: Timeout in seconds for HTTP requests.
        max_requests: Maximum number of requests to make (None for unlimited).
        max_depth: Maximum depth to crawl (None for unlimited).

    Returns:
        A tuple of (broken_links, internal_assets).
    """
    checker = LinkChecker(url, ignored_asset_paths, ignored_internal_paths,
                          timeout=timeout, max_requests=max_requests, max_depth=max_depth)
    return checker.run()
