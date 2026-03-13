"""Tests for url_utils module."""

from __future__ import annotations

import pytest

from link_checker.url_utils import (
    get_depth,
    get_file_extension,
    is_html_extension,
    is_http_url,
    is_same_domain,
    is_under_root,
    matches_prefix,
    normalize_url,
)

# ---------------------------------------------------------------------------
# normalize_url
# ---------------------------------------------------------------------------


def test_normalize_url_strips_fragment() -> None:
    url, frag = normalize_url('https://x.com/a#sec')
    assert url == 'https://x.com/a'
    assert frag == 'sec'


def test_normalize_url_no_fragment() -> None:
    url, frag = normalize_url('https://x.com/a')
    assert url == 'https://x.com/a'
    assert frag is None


def test_normalize_url_preserves_query_params() -> None:
    url, frag = normalize_url('https://x.com/a?b=c&d=e')
    assert url == 'https://x.com/a?b=c&d=e'
    assert frag is None


def test_normalize_url_preserves_query_strips_fragment() -> None:
    url, frag = normalize_url('https://x.com/a?b=c#section')
    assert url == 'https://x.com/a?b=c'
    assert frag == 'section'


def test_normalize_url_lowercases_host() -> None:
    url, _ = normalize_url('https://X.COM/Path')
    assert url == 'https://x.com/Path'


def test_normalize_url_http_normalized_to_https() -> None:
    url_http, _ = normalize_url('http://x.com/a')
    url_https, _ = normalize_url('https://x.com/a')
    assert url_http == url_https


def test_normalize_url_empty_fragment_treated_as_none() -> None:
    url, frag = normalize_url('https://x.com/a#')
    assert url == 'https://x.com/a'
    assert frag is None


def test_normalize_url_preserves_path_case() -> None:
    url, _ = normalize_url('https://x.com/Path/To/PAGE')
    assert url == 'https://x.com/Path/To/PAGE'


# ---------------------------------------------------------------------------
# is_same_domain
# ---------------------------------------------------------------------------


def test_is_same_domain_exact_match() -> None:
    assert is_same_domain('https://x.com/page', 'https://x.com/') is True


def test_is_same_domain_subdomain_is_external() -> None:
    assert is_same_domain('https://sub.x.com/page', 'https://x.com/') is False


def test_is_same_domain_case_insensitive() -> None:
    assert is_same_domain('https://X.COM/page', 'https://x.com/') is True


def test_is_same_domain_different_host() -> None:
    assert is_same_domain('https://other.com/page', 'https://x.com/') is False


def test_is_same_domain_http_vs_https() -> None:
    assert is_same_domain('http://x.com/page', 'https://x.com/') is True


def test_is_same_domain_with_port() -> None:
    assert is_same_domain('https://x.com:8080/page', 'https://x.com:8080/') is True


def test_is_same_domain_different_port() -> None:
    assert is_same_domain('https://x.com:8080/page', 'https://x.com/') is False


# ---------------------------------------------------------------------------
# is_under_root
# ---------------------------------------------------------------------------


def test_is_under_root_exact() -> None:
    assert is_under_root('/a/b/c', '/a/b/c') is True


def test_is_under_root_subpath() -> None:
    assert is_under_root('/a/b/c/d/e', '/a/b/c') is True


def test_is_under_root_above() -> None:
    assert is_under_root('/a/b', '/a/b/c') is False


def test_is_under_root_parallel() -> None:
    assert is_under_root('/a/b/other', '/a/b/c') is False


def test_is_under_root_root_is_slash() -> None:
    assert is_under_root('/anything/here', '/') is True


def test_is_under_root_trailing_slash_root() -> None:
    assert is_under_root('/a/b/c/d', '/a/b/c/') is True


def test_is_under_root_segment_boundary() -> None:
    assert is_under_root('/a/b/cfoo', '/a/b/c') is False


# ---------------------------------------------------------------------------
# matches_prefix
# ---------------------------------------------------------------------------


def test_matches_prefix_exact_url() -> None:
    assert matches_prefix('https://example.com/dir1', 'https://example.com/dir1') is True


def test_matches_prefix_subpath() -> None:
    assert matches_prefix('https://example.com/dir1/foo/bar', 'https://example.com/dir1') is True


def test_matches_prefix_trailing_slash_candidate() -> None:
    assert matches_prefix('https://example.com/dir1/', 'https://example.com/dir1') is True


def test_matches_prefix_segment_boundary_reject() -> None:
    assert matches_prefix('https://example.com/dir1-foo', 'https://example.com/dir1') is False


def test_matches_prefix_segment_boundary_reject_dir10() -> None:
    assert matches_prefix('https://example.com/dir10', 'https://example.com/dir1') is False


def test_matches_prefix_scheme_insensitive() -> None:
    assert matches_prefix('http://example.com/dir1/foo', 'https://example.com/dir1') is True


def test_matches_prefix_different_host() -> None:
    assert matches_prefix('https://other.com/dir1/foo', 'https://example.com/dir1') is False


def test_matches_prefix_host_case_insensitive() -> None:
    assert matches_prefix('https://EXAMPLE.COM/dir1/foo', 'https://example.com/dir1') is True


def test_matches_prefix_with_trailing_slash_in_prefix() -> None:
    assert matches_prefix('https://example.com/dir1/foo', 'https://example.com/dir1/') is True


# ---------------------------------------------------------------------------
# get_file_extension
# ---------------------------------------------------------------------------


def test_get_file_extension_html() -> None:
    assert get_file_extension('https://x.com/page.html') == '.html'


def test_get_file_extension_jpg() -> None:
    assert get_file_extension('https://x.com/img/pic.JPG') == '.jpg'


def test_get_file_extension_no_extension() -> None:
    assert get_file_extension('https://x.com/about') is None


def test_get_file_extension_trailing_slash() -> None:
    assert get_file_extension('https://x.com/about/') is None


def test_get_file_extension_query_ignored() -> None:
    assert get_file_extension('https://x.com/file.pdf?v=1') == '.pdf'


def test_get_file_extension_fragment_ignored() -> None:
    assert get_file_extension('https://x.com/file.txt#section') == '.txt'


def test_get_file_extension_dot_in_path() -> None:
    assert get_file_extension('https://x.com/v1.2/about') is None


# ---------------------------------------------------------------------------
# is_html_extension
# ---------------------------------------------------------------------------


def test_is_html_extension_html() -> None:
    assert is_html_extension('.html') is True


def test_is_html_extension_htm() -> None:
    assert is_html_extension('.htm') is True


def test_is_html_extension_shtml() -> None:
    assert is_html_extension('.shtml') is True


def test_is_html_extension_php() -> None:
    assert is_html_extension('.php') is True


def test_is_html_extension_asp() -> None:
    assert is_html_extension('.asp') is True


def test_is_html_extension_jsp() -> None:
    assert is_html_extension('.jsp') is True


def test_is_html_extension_cgi() -> None:
    assert is_html_extension('.cgi') is True


def test_is_html_extension_none() -> None:
    assert is_html_extension(None) is True


def test_is_html_extension_jpg_is_false() -> None:
    assert is_html_extension('.jpg') is False


def test_is_html_extension_pdf_is_false() -> None:
    assert is_html_extension('.pdf') is False


def test_is_html_extension_case_insensitive() -> None:
    assert is_html_extension('.HTML') is True


# ---------------------------------------------------------------------------
# get_depth
# ---------------------------------------------------------------------------


def test_get_depth_root_is_zero() -> None:
    assert get_depth('/a/b/c', '/a/b/c') == 0


def test_get_depth_one_level_below() -> None:
    assert get_depth('/a/b/c/page.html', '/a/b/c') == 1


def test_get_depth_two_levels_below() -> None:
    assert get_depth('/a/b/c/d/e', '/a/b/c') == 2


def test_get_depth_root_trailing_slash() -> None:
    assert get_depth('/a/b/c/', '/a/b/c') == 0


def test_get_depth_root_index_html() -> None:
    assert get_depth('/a/b/c/index.html', '/a/b/c') == 1


# ---------------------------------------------------------------------------
# is_http_url
# ---------------------------------------------------------------------------


def test_is_http_url_https() -> None:
    assert is_http_url('https://x.com') is True


def test_is_http_url_http() -> None:
    assert is_http_url('http://x.com') is True


def test_is_http_url_mailto() -> None:
    assert is_http_url('mailto:user@x.com') is False


def test_is_http_url_tel() -> None:
    assert is_http_url('tel:+1-555-0100') is False


def test_is_http_url_ftp() -> None:
    assert is_http_url('ftp://files.x.com') is False


def test_is_http_url_javascript() -> None:
    assert is_http_url('javascript:void(0)') is False


def test_is_http_url_data() -> None:
    assert is_http_url('data:text/plain;base64,abc') is False


def test_is_http_url_relative() -> None:
    assert is_http_url('/relative/path') is False


def test_is_http_url_empty() -> None:
    assert is_http_url('') is False


# ---------------------------------------------------------------------------
# Edge cases and integration
# ---------------------------------------------------------------------------


def test_normalize_then_is_same_domain() -> None:
    url1, _ = normalize_url('http://Example.COM/page')
    url2, _ = normalize_url('https://example.com/other')
    assert is_same_domain(url1, url2) is True


def test_normalize_url_non_http_passthrough() -> None:
    url, frag = normalize_url('mailto:user@example.com')
    assert url == 'mailto:user@example.com'
    assert frag is None


@pytest.mark.parametrize(
    ('path', 'root', 'expected'),
    [
        ('/docs', '/docs', True),
        ('/docs/api', '/docs', True),
        ('/docs/api/v2/endpoint', '/docs', True),
        ('/docs-extra', '/docs', False),
        ('/other', '/docs', False),
        ('/doc', '/docs', False),
    ],
)
def test_is_under_root_parametrized(path: str, root: str, expected: bool) -> None:
    assert is_under_root(path, root) is expected
