"""Tests for url_utils module."""

from __future__ import annotations

import pytest

from link_checker.url_utils import (
    add_trailing_slash,
    get_depth,
    get_file_extension,
    is_html_extension,
    is_http_to_https_redirect,
    is_http_url,
    is_same_domain,
    is_under_root,
    matches_prefix,
    normalize_internal_url,
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


def test_normalize_url_http_scheme_preserved() -> None:
    url_http, _ = normalize_url('http://x.com/a')
    url_https, _ = normalize_url('https://x.com/a')
    assert url_http == 'http://x.com/a'
    assert url_https == 'https://x.com/a'


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


# ---------------------------------------------------------------------------
# normalize_url: index-file stripping (applies to all URLs)
# ---------------------------------------------------------------------------


def test_normalize_url_index_html_stripped() -> None:
    url, _ = normalize_url('https://example.com/cassini/index.html')
    assert url == 'https://example.com/cassini/'


def test_normalize_url_index_htm_stripped() -> None:
    url, _ = normalize_url('https://example.com/cassini/index.htm')
    assert url == 'https://example.com/cassini/'


def test_normalize_url_index_php_stripped() -> None:
    url, _ = normalize_url('https://example.com/section/index.php')
    assert url == 'https://example.com/section/'


def test_normalize_url_no_extension_no_slash_unchanged() -> None:
    """normalize_url alone does NOT add trailing slashes."""
    url, _ = normalize_url('https://example.com/cassini')
    assert url == 'https://example.com/cassini'


def test_normalize_url_trailing_slash_unchanged() -> None:
    url, _ = normalize_url('https://example.com/cassini/')
    assert url == 'https://example.com/cassini/'


def test_normalize_url_html_extension_preserved() -> None:
    url, _ = normalize_url('https://example.com/about.html')
    assert url == 'https://example.com/about.html'


def test_normalize_url_non_html_extension_preserved() -> None:
    url, _ = normalize_url('https://example.com/data/report.csv')
    assert url == 'https://example.com/data/report.csv'


def test_normalize_url_index_html_with_fragment() -> None:
    url, frag = normalize_url('https://example.com/section/index.html#intro')
    assert url == 'https://example.com/section/'
    assert frag == 'intro'


def test_normalize_url_index_asp_stripped() -> None:
    url, _ = normalize_url('https://example.com/dir/index.asp')
    assert url == 'https://example.com/dir/'


def test_normalize_url_index_jsp_stripped() -> None:
    url, _ = normalize_url('https://example.com/dir/index.jsp')
    assert url == 'https://example.com/dir/'


def test_normalize_url_index_asp_with_fragment() -> None:
    url, frag = normalize_url('https://example.com/dir/index.asp#frag')
    assert url == 'https://example.com/dir/'
    assert frag == 'frag'


# ---------------------------------------------------------------------------
# add_trailing_slash
# ---------------------------------------------------------------------------


def test_add_trailing_slash_no_extension() -> None:
    assert add_trailing_slash('https://x.com/cassini') == 'https://x.com/cassini/'


def test_add_trailing_slash_already_present() -> None:
    assert add_trailing_slash('https://x.com/cassini/') == 'https://x.com/cassini/'


def test_add_trailing_slash_with_extension() -> None:
    assert add_trailing_slash('https://x.com/page.html') == 'https://x.com/page.html'


def test_add_trailing_slash_asset_url_unchanged() -> None:
    assert add_trailing_slash('https://x.com/data.csv') == 'https://x.com/data.csv'


def test_add_trailing_slash_with_query() -> None:
    assert add_trailing_slash('https://x.com/page?q=1') == 'https://x.com/page/?q=1'


def test_add_trailing_slash_fragment_stripped() -> None:
    """add_trailing_slash operates on already-normalized (fragment-free) URLs;
    any fragment present is dropped by urlunparse, consistent with the contract
    that callers pass normalized URLs."""
    assert add_trailing_slash('https://x.com/page#section') == 'https://x.com/page/'


def test_add_trailing_slash_root_with_slash_unchanged() -> None:
    """Root URL with trailing slash must be returned unchanged."""
    assert add_trailing_slash('https://x.com/') == 'https://x.com/'


def test_add_trailing_slash_bare_host_gets_slash() -> None:
    """Bare host with no path component gets a trailing slash."""
    assert add_trailing_slash('https://x.com') == 'https://x.com/'


def test_add_trailing_slash_dotfile_unchanged() -> None:
    """Leading-dot filenames are treated as files and must not gain a trailing slash."""
    assert add_trailing_slash('https://x.com/path/.htaccess') == 'https://x.com/path/.htaccess'


# ---------------------------------------------------------------------------
# normalize_internal_url: all three variants map to the same canonical
# ---------------------------------------------------------------------------


def test_normalize_internal_url_no_extension_gets_trailing_slash() -> None:
    url, _ = normalize_internal_url('https://example.com/cassini')
    assert url == 'https://example.com/cassini/'


def test_normalize_internal_url_trailing_slash_unchanged() -> None:
    url, _ = normalize_internal_url('https://example.com/cassini/')
    assert url == 'https://example.com/cassini/'


def test_normalize_internal_url_index_html_stripped() -> None:
    url, _ = normalize_internal_url('https://example.com/cassini/index.html')
    assert url == 'https://example.com/cassini/'


def test_normalize_internal_url_all_three_variants_equal() -> None:
    """The three conventional forms of a directory URL must all normalize identically."""
    a, _ = normalize_internal_url('https://example.com/cassini')
    b, _ = normalize_internal_url('https://example.com/cassini/')
    c, _ = normalize_internal_url('https://example.com/cassini/index.html')
    assert a == b == c == 'https://example.com/cassini/'


def test_normalize_internal_url_html_extension_preserved() -> None:
    """Non-index HTML pages must not have their paths altered."""
    url, _ = normalize_internal_url('https://example.com/about.html')
    assert url == 'https://example.com/about.html'


def test_normalize_internal_url_non_html_extension_preserved() -> None:
    """Asset URLs must not have their paths altered."""
    url, _ = normalize_internal_url('https://example.com/data/report.csv')
    assert url == 'https://example.com/data/report.csv'


def test_normalize_internal_url_root_path_unchanged() -> None:
    """The root path '/' must not be modified."""
    url, _ = normalize_internal_url('https://example.com/')
    assert url == 'https://example.com/'


def test_normalize_internal_url_index_html_with_fragment() -> None:
    """Index stripping must still extract the fragment correctly."""
    url, frag = normalize_internal_url('https://example.com/section/index.html#intro')
    assert url == 'https://example.com/section/'
    assert frag == 'intro'


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


# ---------------------------------------------------------------------------
# is_http_to_https_redirect
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('original', 'final', 'expected'),
    [
        # Pure scheme upgrade — should return True
        ('http://example.com/path', 'https://example.com/path', True),
        ('http://example.com/', 'https://example.com/', True),
        ('http://example.com/a/b?q=1', 'https://example.com/a/b?q=1', True),
        # Host case-insensitive
        ('http://EXAMPLE.COM/path', 'https://example.com/path', True),
        # Path differs — not a pure upgrade
        ('http://example.com/old', 'https://example.com/new', False),
        # Query differs
        ('http://example.com/page?a=1', 'https://example.com/page?a=2', False),
        # Host differs
        ('http://example.com/path', 'https://other.com/path', False),
        # Already https original — not an upgrade
        ('https://example.com/path', 'https://example.com/path', False),
        # https → http (downgrade) — not an upgrade
        ('https://example.com/path', 'http://example.com/path', False),
        # https → http with same path
        ('https://example.com/', 'http://example.com/', False),
    ],
)
def test_is_http_to_https_redirect(original: str, final: str, expected: bool) -> None:
    assert is_http_to_https_redirect(original, final) is expected
