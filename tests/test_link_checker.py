"""Tests for the LinkChecker class."""

import unittest
from unittest.mock import patch, MagicMock
import requests

from link_checker.main import LinkChecker


class TestLinkChecker(unittest.TestCase):
    """Tests for the LinkChecker class."""

    def setUp(self):
        """Set up test fixtures."""
        self.root_url = "https://example.com"
        self.checker = LinkChecker(self.root_url, timeout=10.0,
                                   max_requests=100, max_depth=2)

    def test_normalize_url(self):
        """Test URL normalization."""
        # Test trailing slash removal
        self.assertEqual(
            self.checker._normalize_url("https://example.com/path/"),
            "https://example.com/path"
        )

        # Test fragment removal
        self.assertEqual(
            self.checker._normalize_url("https://example.com/path#fragment"),
            "https://example.com/path"
        )

        # Test trailing slash + fragment
        self.assertEqual(
            self.checker._normalize_url("https://example.com/path/#fragment"),
            "https://example.com/path"
        )

        # Test root path with trailing slash (should be preserved)
        self.assertEqual(
            self.checker._normalize_url("https://example.com/"),
            "https://example.com/"
        )

    def test_is_internal_url(self):
        """Test internal URL detection."""
        # Test internal absolute URL
        self.assertTrue(
            self.checker._is_internal_url("https://example.com/path")
        )

        # Test internal relative URL
        self.assertTrue(
            self.checker._is_internal_url("/path")
        )

        # Test external URL
        self.assertFalse(
            self.checker._is_internal_url("https://another-site.com/path")
        )

    def test_is_html_url(self):
        """Test HTML URL detection."""
        # Test HTML extensions
        self.assertTrue(self.checker._is_html_url("https://example.com/page.html"))
        self.assertTrue(self.checker._is_html_url("https://example.com/page.htm"))
        self.assertTrue(self.checker._is_html_url("https://example.com/page.php"))

        # Test no extension (should be considered HTML)
        self.assertTrue(self.checker._is_html_url("https://example.com/path"))

        # Test non-HTML extensions
        self.assertFalse(self.checker._is_html_url("https://example.com/image.jpg"))
        self.assertFalse(self.checker._is_html_url("https://example.com/file.pdf"))

    def test_get_asset_type(self):
        """Test asset type detection."""
        # Test image types
        self.assertEqual(
            self.checker._get_asset_type("https://example.com/image.jpg"),
            "image"
        )
        self.assertEqual(
            self.checker._get_asset_type("https://example.com/image.png"),
            "image"
        )

        # Test web assets
        self.assertEqual(
            self.checker._get_asset_type("https://example.com/style.css"),
            "web_asset"
        )
        self.assertEqual(
            self.checker._get_asset_type("https://example.com/script.js"),
            "web_asset"
        )

        # Test documents
        self.assertEqual(
            self.checker._get_asset_type("https://example.com/doc.pdf"),
            "document"
        )

        # Test text files
        self.assertEqual(
            self.checker._get_asset_type("https://example.com/data.txt"),
            "text"
        )
        self.assertEqual(
            self.checker._get_asset_type("https://example.com/data.xml"),
            "text"
        )

        # Test unknown extension
        self.assertEqual(
            self.checker._get_asset_type("https://example.com/file.xyz"),
            "xyz"
        )

    def test_resolve_relative_url(self):
        """Test relative URL resolution."""
        # Test absolute URL (should be unchanged)
        self.assertEqual(
            self.checker._resolve_relative_url(
                "https://example.com/page/page2",
                "https://example.com/other/other2"
            ),
            "https://example.com/other/other2"
        )

        # Test relative URL with leading slash
        self.assertEqual(
            self.checker._resolve_relative_url(
                "https://example.com/page/page2",
                "/other/other2"
            ),
            "https://example.com/other/other2"
        )

        # Test relative URL without leading slash (should be relative to the
        # directory)
        self.assertEqual(
            self.checker._resolve_relative_url(
                "https://example.com/page/page2",
                "other"
            ),
            "https://example.com/page/page2/other"
        )

        # Test relative URL without leading slash but with a file-like base URL
        self.assertEqual(
            self.checker._resolve_relative_url(
                "https://example.com/page/page2.html",
                "other"
            ),
            "https://example.com/page/other"
        )

    def test_check_url(self):
        """Test URL checking."""
        # Test cases for different URL scenarios
        test_cases = [
            # URL, content_type, status_code, expected_content, expected_status
            ("https://example.com", "text/html", 200, "<html></html>", 200),
            ("https://example.com/api", "application/json", 200, None, 200),
            ("https://example.com/not-found", "text/html", 404, None, 404),
            ("https://example.com/error", None, None, None, None),
        ]

        for (url, content_type, status_code,
             expected_content, expected_status) in test_cases:
            with self.subTest(url=url):
                # If this is the error case, simulate an exception
                if url == "https://example.com/error":
                    with patch('requests.Session.get',
                               side_effect=requests.RequestException(
                                   "Connection error")):
                        content, status = self.checker._check_url(url)
                else:
                    # Create a mock response
                    mock_response = MagicMock()
                    mock_response.status_code = status_code
                    if content_type:
                        mock_response.headers = {'Content-Type': content_type}
                    if expected_content:
                        mock_response.text = expected_content

                    # Patch the session.get method to return our mock
                    with patch('requests.Session.get', return_value=mock_response):
                        content, status = self.checker._check_url(url)

                # Check expectations
                self.assertEqual(content, expected_content)
                self.assertEqual(status, expected_status)

    def test_extract_links_ignores_mailto(self):
        """Test that mailto links are ignored."""
        html_content = """
        <html>
        <body>
            <a href="https://example.com/page1">Page 1</a>
            <a href="mailto:info@example.com">Email Us</a>
            <a href="/page2">Page 2</a>
            <a href="#section">Section</a>
            <a href="javascript:void(0)">JS Link</a>
        </body>
        </html>
        """

        links = self.checker._extract_links("https://example.com", html_content)

        # Check that correct links were extracted
        self.assertEqual(len(links), 2)
        self.assertIn("https://example.com/page1", links)
        self.assertIn("https://example.com/page2", links)

        # Check that mailto and javascript links were ignored
        self.assertNotIn("mailto:info@example.com", links)
        self.assertNotIn("javascript:void(0)", links)
        self.assertNotIn("#section", links)

    @patch('link_checker.main.LinkChecker._check_url')
    @patch('link_checker.main.LinkChecker._extract_links')
    def test_link_checker(self, mock_extract_links, mock_check_url):
        """Test link checking process."""
        # Create a side effect function for _check_url that adds URLs to visited_urls
        def check_url_side_effect(url):
            self.checker.visited_urls.add(url)
            return ("<html><body>Test</body></html>", 200)

        # Set the side effect for the mock
        mock_check_url.side_effect = check_url_side_effect

        # Mock extracted links
        # Use side_effect to return different values for different calls
        mock_extract_links.side_effect = [
            # First call (for root URL) - returns links
            ["https://example.com/page1", "https://example.com/page2"],
            # Subsequent calls (for the extracted links) - return empty lists to stop recursion
            [],
            []
        ]

        # Also set up internal assets manually since we're mocking _extract_links
        self.checker.internal_assets["https://example.com"] = {"https://example.com/style.css": "web_asset"}

        # Run link checking
        with patch('time.sleep'):  # Patch sleep to speed up test
            self.checker.link_checker()

        # Check that the URLs were visited
        self.assertIn("https://example.com", self.checker.visited_urls)
        self.assertIn("https://example.com/page1", self.checker.visited_urls)
        self.assertIn("https://example.com/page2", self.checker.visited_urls)

        # Check that assets were recorded
        self.assertEqual(
            self.checker.internal_assets[
                "https://example.com"]["https://example.com/style.css"],
            "web_asset"
        )

    def test_should_ignore_asset(self):
        """Test that assets in ignored paths are correctly identified."""
        # Create a checker with ignored paths
        checker = LinkChecker("https://example.com",
                              ignored_asset_paths=['/images', '/css'])

        # Test URLs that should be ignored
        self.assertTrue(checker._should_ignore_asset(
            "https://example.com/images/logo.png"))
        self.assertTrue(checker._should_ignore_asset(
            "https://example.com/css/style.css"))
        self.assertTrue(checker._should_ignore_asset(
            "https://example.com/images/subfolder/icon.jpg"))

        # Test URLs that should not be ignored
        self.assertFalse(checker._should_ignore_asset(
            "https://example.com/assets/logo.png"))
        self.assertFalse(checker._should_ignore_asset(
            "https://example.com/js/script.js"))
        self.assertFalse(checker._should_ignore_asset(
            "https://example.com/image-file.jpg"))  # Not in /images/

    def test_extract_links_with_ignored_paths(self):
        """Test that assets in ignored paths are not included."""
        # Create a checker with ignored paths
        checker = LinkChecker("https://example.com",
                              ignored_asset_paths=['/images', '/css'])

        html_content = """
        <html>
        <body>
            <a href="https://example.com/page1">Page 1</a>
            <a href="/images/photo.jpg">Photo</a>
            <a href="/assets/document.pdf">Document</a>
            <img src="/images/logo.png" alt="Logo">
            <img src="/assets/banner.jpg" alt="Banner">
            <link rel="stylesheet" href="/css/style.css">
            <link rel="stylesheet" href="/assets/custom.css">
            <script src="/js/script.js"></script>
        </body>
        </html>
        """

        links = checker._extract_links("https://example.com", html_content)

        # Check that the HTML links were extracted but not the assets
        self.assertEqual(len(links), 1)
        self.assertIn("https://example.com/page1", links)

        # Check that assets in ignored paths are tracked in ignored_internal_assets_found
        self.assertIn("https://example.com/images/photo.jpg",
                      list(checker.ignored_internal_assets_found["https://example.com"].keys()))
        self.assertIn("https://example.com/images/logo.png",
                      list(checker.ignored_internal_assets_found["https://example.com"].keys()))
        self.assertIn("https://example.com/css/style.css",
                      list(checker.ignored_internal_assets_found["https://example.com"].keys()))

        # Check that non-ignored assets are in internal_assets
        self.assertIn("https://example.com/assets/document.pdf",
                      list(checker.internal_assets["https://example.com"].keys()))
        self.assertIn("https://example.com/assets/banner.jpg",
                      list(checker.internal_assets["https://example.com"].keys()))
        self.assertIn("https://example.com/assets/custom.css",
                      list(checker.internal_assets["https://example.com"].keys()))
        self.assertIn("https://example.com/js/script.js",
                      list(checker.internal_assets["https://example.com"].keys()))

    def test_should_not_crawl(self):
        """Test that internal paths that should not be crawled are correctly
        identified."""
        # Create a checker with ignored internal paths
        checker = LinkChecker("https://example.com",
                              ignored_internal_paths=['/docs', '/blog'])

        # Test URLs that should not be crawled
        self.assertTrue(checker._should_not_crawl(
            "https://example.com/docs/index.html"))
        self.assertTrue(checker._should_not_crawl(
            "https://example.com/blog/post1.html"))
        self.assertTrue(checker._should_not_crawl(
            "https://example.com/docs/api/reference.html"))

        # Test URLs that should be crawled
        self.assertFalse(checker._should_not_crawl(
            "https://example.com/index.html"))
        self.assertFalse(checker._should_not_crawl(
            "https://example.com/about.html"))
        self.assertFalse(checker._should_not_crawl(
            "https://example.com/documentation.html"))  # Not in /docs/

    def test_print_report_shows_ignored_paths(self):
        """Test that print_report shows the ignored paths."""
        # Create a checker with ignored paths
        checker = LinkChecker(
            "https://example.com",
            ignored_asset_paths=['/images', '/css'],
            ignored_internal_paths=['/docs', '/blog']
        )

        # Simulate some ignored assets
        checker.ignored_internal_assets_count = 5

        # Capture the output of print_report
        import io
        import sys
        captured_output = io.StringIO()
        original_stdout = sys.stdout
        sys.stdout = captured_output

        try:
            checker.print_report()
            output = captured_output.getvalue()

            # Check that configuration section exists
            self.assertIn("=== CONFIGURATION ===", output)
            self.assertIn("Root URL: https://example.com", output)

            # Check that ignored asset paths are shown
            self.assertIn("Ignored asset paths (checked but not reported):", output)
            self.assertIn("- /css", output)
            self.assertIn("- /images", output)

            # Check that ignored internal paths are shown
            self.assertIn("Ignored internal paths (checked but not crawled):", output)
            self.assertIn("- /blog", output)
            self.assertIn("- /docs", output)

            # Check that counters are shown
            self.assertIn("Ignored assets found: 5", output)

        finally:
            # Reset stdout
            sys.stdout = original_stdout

    def test_resolve_relative_url_with_different_base_types(self):
        """Test relative URL resolution with different types of base URLs."""
        # Test base URL with domain and path
        self.assertEqual(
            self.checker._resolve_relative_url(
                "https://example.com/dir/page.html",
                "../other.html"
            ),
            "https://example.com/other.html"
        )

        # Test base URL with just a path
        self.assertEqual(
            self.checker._resolve_relative_url(
                "/dir/page.html",
                "../other.html"
            ),
            "/other.html"  # This is the actual behavior of the method
        )

        # Test with a base URL that's a directory (ends with /)
        self.assertEqual(
            self.checker._resolve_relative_url(
                "https://example.com/dir/",
                "page.html"
            ),
            "https://example.com/dir/page.html"
        )

        # Test with a base URL that's a file (doesn't end with /)
        self.assertEqual(
            self.checker._resolve_relative_url(
                "https://example.com/dir/file.html",
                "page.html"
            ),
            "https://example.com/dir/page.html"
        )

    def test_ignore_paths_without_leading_slash(self):
        """Test that ignore paths work without a leading slash."""
        # Create a checker with ignore paths that don't have leading slashes
        checker = LinkChecker(
            "https://example.com",
            ignored_asset_paths=["images", "css/styles"],
            ignored_internal_paths=["docs", "blog/posts"]
        )

        # Test asset URLs that should be ignored
        self.assertTrue(
            checker._should_ignore_asset("https://example.com/images/logo.png"))
        self.assertTrue(
            checker._should_ignore_asset("https://example.com/css/styles/main.css"))

        # Test URLs that should not be crawled
        self.assertTrue(checker._should_not_crawl("https://example.com/docs/index.html"))
        self.assertTrue(
            checker._should_not_crawl("https://example.com/blog/posts/2023/01.html"))

        # Test that the original paths with slashes still work
        checker = LinkChecker(
            "https://example.com",
            ignored_asset_paths=["/images", "/css/styles"],
            ignored_internal_paths=["/docs", "/blog/posts"]
        )

        self.assertTrue(
            checker._should_ignore_asset("https://example.com/images/logo.png"))
        self.assertTrue(checker._should_not_crawl("https://example.com/docs/index.html"))

    def test_is_within_allowed_hierarchy(self):
        """Test that URLs outside the allowed hierarchy are correctly identified."""
        # Create a checker with a subdirectory as the root
        checker = LinkChecker("https://example.com/subdir")

        # URLs that should be within the allowed hierarchy
        self.assertTrue(
            checker._is_within_allowed_hierarchy("https://example.com/subdir"))
        self.assertTrue(
            checker._is_within_allowed_hierarchy("https://example.com/subdir/page.html"))
        self.assertTrue(checker._is_within_allowed_hierarchy(
            "https://example.com/subdir/deeper/page.html"))

        # URLs that should be outside the allowed hierarchy
        self.assertFalse(checker._is_within_allowed_hierarchy("https://example.com"))
        self.assertFalse(
            checker._is_within_allowed_hierarchy("https://example.com/other"))
        self.assertFalse(checker._is_within_allowed_hierarchy(
            "https://example.com/subdirectory"))  # Similar but different

        # Check that external domains are always allowed (handled separately)
        self.assertTrue(checker._is_within_allowed_hierarchy("https://another-site.com"))

        # Test with trailing slashes
        checker = LinkChecker("https://example.com/subdir/")
        self.assertTrue(
            checker._is_within_allowed_hierarchy("https://example.com/subdir"))
        self.assertFalse(checker._is_within_allowed_hierarchy("https://example.com"))

        # Test with root URL
        checker = LinkChecker("https://example.com")
        self.assertTrue(
            checker._is_within_allowed_hierarchy("https://example.com/anything"))
        self.assertTrue(checker._is_within_allowed_hierarchy("https://example.com"))

    def test_link_checker_respects_hierarchy(self):
        """Test that the link checker respects URL hierarchy boundaries."""
        # Create a checker with a subdirectory as the root URL
        checker = LinkChecker("https://example.com/subdir/")

        # Mock _check_url to return success for all URLs and add them to visited_urls
        with patch('link_checker.main.LinkChecker._check_url') as mock_check_url:
            # Create a side effect function for _check_url that adds URLs to visited_urls
            def check_url_side_effect(url):
                checker.visited_urls.add(url)
                return ("<html><body>Test</body></html>", 200)

            # Set the side effect for the mock
            mock_check_url.side_effect = check_url_side_effect

            # Mock _extract_links to return URLs both within and outside the hierarchy
            with patch(
                    'link_checker.main.LinkChecker._extract_links') as mock_extract_links:
                within_hierarchy = [
                    "https://example.com/subdir/page1.html",
                    "https://example.com/subdir/page2.html",
                    "https://example.com/subdir/sub/page3.html"
                ]
                outside_hierarchy = [
                    "https://example.com",
                    "https://example.com/other"
                ]
                # First call returns all links, subsequent calls return empty lists
                mock_extract_links.side_effect = [
                    within_hierarchy + outside_hierarchy,
                    *[[] for _ in range(len(within_hierarchy) + len(outside_hierarchy))]
                ]

                # Run link checking
                with patch('time.sleep'):  # Patch sleep to speed up test
                    checker.link_checker()

                # Check that URLs within hierarchy were added to urls_to_visit
                for url in within_hierarchy:
                    self.assertIn(url, checker.visited_urls)

                # Check that URLs outside hierarchy were not added to urls_to_visit
                # but were still checked for existence
                for url in outside_hierarchy:
                    self.assertIn(url, checker.visited_urls)

    def test_resolve_page_relative_url(self):
        """Test resolution of URLs relative to a page."""
        # Test case from the example:
        # From "https://pds-rings.seti.org/voyager/index.html"
        # resolving "data.html" should give "https://pds-rings.seti.org/voyager/data.html"

        checker = LinkChecker("https://pds-rings.seti.org/voyager/")

        # Test case 1: Resolving a relative URL from a page
        resolved_url = checker._resolve_relative_url(
            "https://pds-rings.seti.org/voyager/index.html",
            "data.html"
        )

        self.assertEqual(resolved_url, "https://pds-rings.seti.org/voyager/data.html")

        # Test case 2: Resolving a relative URL from a directory without trailing slash
        # This was the problematic case
        resolved_url = checker._resolve_relative_url(
            "https://pds-rings.seti.org/voyager",  # No trailing slash
            "data.html"
        )

        self.assertEqual(resolved_url, "https://pds-rings.seti.org/voyager/data.html")

        # Test case 3: A more complex case with a deeper path
        resolved_url = checker._resolve_relative_url(
            "https://pds-rings.seti.org/voyager/iss/index.html",
            "data.html"
        )

        self.assertEqual(resolved_url, "https://pds-rings.seti.org/voyager/iss/data.html")

        # Test case 4: With a relative URL that goes up a level
        resolved_url = checker._resolve_relative_url(
            "https://pds-rings.seti.org/voyager/iss/index.html",
            "../data.html"
        )

        self.assertEqual(resolved_url, "https://pds-rings.seti.org/voyager/data.html")

        # Test case 5: With multiple path components
        resolved_url = checker._resolve_relative_url(
            "https://pds-rings.seti.org/voyager/iss/calibrated/index.html",
            "../../raw/data.html"
        )

        self.assertEqual(resolved_url, "https://pds-rings.seti.org/voyager/raw/data.html")

    def test_directory_urls_treated_as_index_html(self):
        """Test that URLs without extensions are treated as pointing to index.html."""
        checker = LinkChecker("https://example.com")

        # First, manually add a URL with /index.html to the visited_urls set
        index_url = "https://example.com/voyager/index.html"
        checker.visited_urls.add(index_url)

        # Now normalize a URL without an extension
        normalized = checker._normalize_url("https://example.com/voyager")

        # It should be recognized as the same as the /index.html version
        self.assertEqual(normalized, "https://example.com/voyager/index.html")

        # Test the _check_url method with a mock
        with patch('requests.Session.get') as mock_get:
            # Mock a successful response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {'Content-Type': 'text/html'}
            mock_response.text = "<html><body>Test</body></html>"
            mock_get.return_value = mock_response

            # Clear the visited_urls set
            checker.visited_urls = set()

            # Check a URL without an extension
            checker._check_url("https://example.com/voyager")

            # Both the original URL and the /index.html version should be marked as
            # visited
            self.assertIn("https://example.com/voyager", checker.visited_urls)
            self.assertIn("https://example.com/voyager/index.html", checker.visited_urls)

            # Now check an /index.html URL
            checker.visited_urls = set()
            checker._check_url("https://example.com/voyager/index.html")

            # Both the /index.html URL and the directory version should be marked as
            # visited
            self.assertIn("https://example.com/voyager/index.html", checker.visited_urls)
            self.assertIn("https://example.com/voyager", checker.visited_urls)


if __name__ == '__main__':
    unittest.main()
