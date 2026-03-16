"""Tests for crawler module."""

from __future__ import annotations

import argparse
from dataclasses import replace

import requests.exceptions
import responses as resp_lib

from link_checker.config import CrawlConfig, load_config
from link_checker.crawler import Crawler
from link_checker.results import CrawlResults

# Disable inter-retry sleeps for all crawler tests so they run fast.
_NO_SLEEP: object = staticmethod(lambda _: None)


def _cfg(**kwargs: object) -> CrawlConfig:
    defaults: dict[str, object] = {
        'root_url': 'https://example.com/docs/',
        'timeout': None,
        'retries': None,
        'max_requests': None,
        'max_depth': None,
        'max_threads': None,
        'max_referencing_pages': None,
        'log_level': None,
        'output': None,
        'log_file': None,
        'config_file': None,
    }
    defaults.update(kwargs)
    return load_config(argparse.Namespace(**defaults))


def _cfg_with(**kwargs: object) -> CrawlConfig:
    """Build config with explicit keyword params, including URL lists."""
    base = _cfg(root_url=kwargs.pop('root_url', 'https://example.com/docs/'))
    return replace(base, **kwargs)  # type: ignore[arg-type]


def _crawl(cfg: CrawlConfig) -> CrawlResults:
    """Run a crawl with sleep disabled so tests never wait on retries."""
    return Crawler(cfg, sleep=_NO_SLEEP).crawl()  # type: ignore[arg-type]


def _make_crawler(cfg: CrawlConfig) -> Crawler:
    """Construct a Crawler with sleep disabled."""
    return Crawler(cfg, sleep=_NO_SLEEP)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Basic crawling
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_single_page_no_links() -> None:
    resp_lib.add(
        resp_lib.GET, 'https://example.com/docs/', body='<html><body></body></html>', status=200
    )
    cfg = _cfg()
    results = _crawl(cfg)
    assert results.statistics.total_requests == 1
    assert not results.broken_links


@resp_lib.activate
def test_two_pages_linked() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="/docs/page2.html">link</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/page2.html', body='<html/>', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    assert results.statistics.total_requests == 2
    assert not results.broken_links


# ---------------------------------------------------------------------------
# External links
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_external_link_head_checked() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="https://external.com/page">ext</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://external.com/page', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    assert results.statistics.external_checked == 1
    assert not results.broken_links


@resp_lib.activate
def test_external_link_head_405_falls_back() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="https://external.com/page">ext</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://external.com/page', status=405)
    resp_lib.add(resp_lib.GET, 'https://external.com/page', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    assert not results.broken_links


# ---------------------------------------------------------------------------
# Broken links
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_broken_link_recorded() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="/docs/missing.html">m</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/missing.html', status=404)
    cfg = _cfg()
    results = _crawl(cfg)
    broken_urls = [bl.url for bl in results.broken_links]
    assert 'https://example.com/docs/missing.html' in broken_urls


# ---------------------------------------------------------------------------
# Redirects
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_relative_links_resolved_against_final_url_after_redirect() -> None:
    """Relative links must be resolved against the final URL after redirects.

    e.g. GET /docs/section → 301 → /docs/section/ and the page has
    href="rss/index.html" should resolve to /docs/section/rss/index.html,
    not /docs/rss/index.html.
    """
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="section">s</a></body></html>',
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/section/',
        body='<html><body><a href="sub/page.html">sub</a></body></html>',
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/section/sub/page.html',
        body='<html/>',
        status=200,
    )
    cfg = _cfg()
    results = _crawl(cfg)
    broken_urls = [b.url for b in results.broken_links]
    assert 'https://example.com/docs/sub/page.html' not in broken_urls


@resp_lib.activate
def test_redirect_followed_and_recorded() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="/docs/old.html">link</a></body></html>',
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/old.html',
        status=301,
        headers={'Location': 'https://example.com/docs/new.html'},
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/new.html', body='<html/>', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    redirect_originals = [r.original_url for r in results.redirects]
    assert 'https://example.com/docs/old.html' in redirect_originals
    redirect = next(
        r for r in results.redirects if r.original_url == 'https://example.com/docs/old.html'
    )
    assert redirect.status_code == 301


@resp_lib.activate
def test_redirect_not_recorded_when_urls_are_identical_after_normalization() -> None:
    """http→https normalization must not produce spurious redirect entries."""
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="/docs/page.html">link</a></body></html>',
        status=200,
    )
    # Server responds with a 301 whose Location is the same URL (normalized)
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/page.html',
        status=301,
        headers={'Location': 'https://example.com/docs/page.html'},
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/page.html', body='<html/>', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    redirect_originals = [r.original_url for r in results.redirects]
    assert 'https://example.com/docs/page.html' not in redirect_originals


# ---------------------------------------------------------------------------
# Fragment validation
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_fragment_valid_anchor() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="/docs/page.html#section1">link</a></body></html>',
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/page.html',
        body='<html><body><div id="section1">content</div></body></html>',
        status=200,
    )
    cfg = _cfg()
    results = _crawl(cfg)
    assert not results.broken_anchors


@resp_lib.activate
def test_fragment_missing_anchor() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="/docs/page.html#bad">link</a></body></html>',
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/page.html',
        body='<html><body><div id="good">content</div></body></html>',
        status=200,
    )
    cfg = _cfg()
    results = _crawl(cfg)
    assert any('bad' in ba.target_url for ba in results.broken_anchors)


@resp_lib.activate
def test_fragment_on_already_visited_page_no_refetch() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body=(
            '<html><body>'
            '<a href="/docs/page.html">no frag</a>'
            '<a href="/docs/page.html#section1">with frag</a>'
            '</body></html>'
        ),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/page.html',
        body='<html><body><div id="section1">content</div></body></html>',
        status=200,
    )
    cfg = _cfg()
    results = _crawl(cfg)
    assert not results.broken_anchors
    assert results.statistics.total_requests == 2


# ---------------------------------------------------------------------------
# Visit-once
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_visit_once_different_schemes() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body=(
            '<html><body>'
            '<a href="http://example.com/docs/page.html">http</a>'
            '<a href="https://example.com/docs/page.html">https</a>'
            '</body></html>'
        ),
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/page.html', body='<html/>', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    assert results.statistics.total_requests == 2


@resp_lib.activate
def test_visit_once_same_url_visited_only_once() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body=(
            '<html><body>'
            '<a href="/docs/page.html">link1</a>'
            '<a href="/docs/page.html">link2</a>'
            '</body></html>'
        ),
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/page.html', body='<html/>', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    assert results.statistics.total_requests == 2


@resp_lib.activate
def test_visit_once_query_params_distinct() -> None:
    """URLs with different query strings are treated as distinct resources."""
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body=(
            '<html><body>'
            '<a href="/docs/page.html?a=1">link1</a>'
            '<a href="/docs/page.html?b=2">link2</a>'
            '</body></html>'
        ),
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/page.html?a=1', body='<html/>', status=200)
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/page.html?b=2', body='<html/>', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    assert results.statistics.total_requests == 3


# ---------------------------------------------------------------------------
# Depth limiting
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_depth_limit_enforced() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="/docs/level1/page.html">l1</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/docs/level1/page.html', status=200)
    cfg = _cfg_with(max_depth=0)
    results = _crawl(cfg)
    assert results.statistics.total_requests == 2
    assert results.statistics.pages_crawled == 1


# ---------------------------------------------------------------------------
# Max requests
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_max_requests_limit() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body=(
            '<html><body>'
            '<a href="/docs/a.html">a</a>'
            '<a href="/docs/b.html">b</a>'
            '<a href="/docs/c.html">c</a>'
            '</body></html>'
        ),
        status=200,
    )
    for page in ['a', 'b', 'c']:
        resp_lib.add(
            resp_lib.GET, f'https://example.com/docs/{page}.html', body='<html/>', status=200
        )
    cfg = _cfg_with(max_requests=2)
    results = _crawl(cfg)
    assert results.statistics.total_requests <= 2


# ---------------------------------------------------------------------------
# No-crawl URLs
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_no_crawl_prefix_checked_not_crawled() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="https://example.com/docs/archive/page.html">arch</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/docs/archive/page.html', status=200)
    cfg = _cfg_with(no_crawl_urls=('https://example.com/docs/archive',))
    results = _crawl(cfg)
    nc_urls = [m.url for m in results.no_crawl_matches]
    assert 'https://example.com/docs/archive/page.html' in nc_urls
    # The HEAD request for the no-crawl URL must be counted in statistics.
    assert results.statistics.total_requests == 2  # GET root + HEAD archive page


# ---------------------------------------------------------------------------
# Ignore URLs
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_ignore_prefix_not_checked() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="https://example.com/legacy/old.html">leg</a></body></html>',
        status=200,
    )
    cfg = _cfg_with(ignore_urls=('https://example.com/legacy',))
    results = _crawl(cfg)
    ig_urls = [m.url for m in results.ignore_matches]
    assert 'https://example.com/legacy/old.html' in ig_urls
    assert results.statistics.total_requests == 1


# ---------------------------------------------------------------------------
# Non-HTTP schemes
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_non_http_scheme_logged() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="mailto:user@example.com">email</a></body></html>',
        status=200,
    )
    cfg = _cfg()
    results = _crawl(cfg)
    non_http = [lk.url for lk in results.non_http_links]
    assert 'mailto:user@example.com' in non_http


# ---------------------------------------------------------------------------
# Asset classification
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_asset_classified_and_checked() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><img src="/docs/img/logo.png"></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/docs/img/logo.png', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    assert results.statistics.total_requests == 2
    assert not results.broken_links


# ---------------------------------------------------------------------------
# Misplaced assets
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_misplaced_asset_detected() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><img src="/docs/img/logo.png"></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/docs/img/logo.png', status=200)
    cfg = _cfg_with(asset_urls=('https://example.com/static',))
    results = _crawl(cfg)
    misplaced_urls = [a.url for a in results.misplaced_assets]
    assert 'https://example.com/docs/img/logo.png' in misplaced_urls


@resp_lib.activate
def test_misplaced_asset_detected_via_anchor_href() -> None:
    """Documents linked via <a href> must also be detected as misplaced assets.

    Previously only links with is_asset=True (img, script, etc.) were checked;
    <a href> links to .pdf/.csv/.txt files were silently skipped.
    """
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="/docs/data/report.csv">CSV</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/data/report.csv', status=200)
    cfg = _cfg_with(asset_urls=('https://example.com/static',))
    results = _crawl(cfg)
    misplaced_urls = [a.url for a in results.misplaced_assets]
    assert 'https://example.com/docs/data/report.csv' in misplaced_urls


@resp_lib.activate
def test_misplaced_asset_external_excluded() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><img src="https://cdn.external.com/logo.png"></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://cdn.external.com/logo.png', status=200)
    cfg = _cfg_with(asset_urls=('https://example.com/static',))
    results = _crawl(cfg)
    assert not results.misplaced_assets


@resp_lib.activate
def test_misplaced_asset_ignored_excluded() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><img src="/legacy/logo.png"></body></html>',
        status=200,
    )
    cfg = _cfg_with(
        asset_urls=('https://example.com/static',),
        ignore_urls=('https://example.com/legacy',),
    )
    results = _crawl(cfg)
    assert not results.misplaced_assets


# ---------------------------------------------------------------------------
# Subdomain treated as external
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_subdomain_treated_as_external() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="https://sub.example.com/page">sub</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://sub.example.com/page', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    assert results.statistics.external_checked == 1


# ---------------------------------------------------------------------------
# Path above root not crawled
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_path_above_root_not_crawled() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="https://example.com/other">other</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/other', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    assert results.statistics.external_checked == 1


# ---------------------------------------------------------------------------
# base href resolution
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_base_href_resolution() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body=(
            '<html><head><base href="https://example.com/docs/sub/"></head>'
            '<body><a href="page.html">p</a></body></html>'
        ),
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/sub/page.html', body='<html/>', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    assert results.statistics.total_requests == 2


# ---------------------------------------------------------------------------
# SSL errors
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_ssl_error_warns_per_domain() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="https://bad-ssl.example.com/p">ssl</a></body></html>',
        status=200,
    )
    resp_lib.add(
        resp_lib.HEAD,
        'https://bad-ssl.example.com/p',
        body=requests.exceptions.SSLError('cert verify failed'),
    )
    cfg = _cfg()
    results = _crawl(cfg)
    assert len(results.ssl_warnings) == 1
    assert results.ssl_warnings[0].domain == 'bad-ssl.example.com'


@resp_lib.activate
def test_ssl_error_on_internal_page_warns_and_continues() -> None:
    """SSL error on an internal GET must record a warning and not abort the crawl."""
    cfg = _cfg(root_url='https://bad-ssl.example.com/docs/')
    resp_lib.add(
        resp_lib.GET,
        'https://bad-ssl.example.com/docs/',
        body=requests.exceptions.SSLError('certificate verify failed'),
    )
    results = _crawl(cfg)
    domains = [sw.domain for sw in results.ssl_warnings]
    assert 'bad-ssl.example.com' in domains
    # crawl must not raise — reaching here means it continued cleanly


# ---------------------------------------------------------------------------
# Unvalidated anchors
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_unvalidated_anchor_on_no_crawl() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="https://example.com/archive/doc.html#intro">arch</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/archive/doc.html', status=200)
    cfg = _cfg_with(no_crawl_urls=('https://example.com/archive',))
    results = _crawl(cfg)
    unval = [ua.target_url for ua in results.unvalidated_anchors]
    assert 'https://example.com/archive/doc.html#intro' in unval


@resp_lib.activate
def test_unvalidated_anchor_on_external() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="https://external.com/api.html#auth">ext</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://external.com/api.html', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    unval = [ua.target_url for ua in results.unvalidated_anchors]
    assert 'https://external.com/api.html#auth' in unval


@resp_lib.activate
def test_unvalidated_anchor_on_depth_limited() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="/docs/deep/page.html#note">deep</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/docs/deep/page.html', status=200)
    cfg = _cfg_with(max_depth=0)
    results = _crawl(cfg)
    unval = [ua.target_url for ua in results.unvalidated_anchors]
    assert 'https://example.com/docs/deep/page.html#note' in unval


# ---------------------------------------------------------------------------
# Exit-code logic (via has_problems)
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_exit_code_0_clean() -> None:
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/', body='<html/>', status=200)
    cfg = _cfg()
    results = _crawl(cfg)
    assert results.has_problems() is False


@resp_lib.activate
def test_exit_code_1_broken() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="/docs/missing.html">m</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/missing.html', status=404)
    cfg = _cfg()
    results = _crawl(cfg)
    assert results.has_problems() is True


# ---------------------------------------------------------------------------
# Referrer accumulation for already-visited URLs
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_already_visited_broken_link_accumulates_referrers() -> None:
    """A broken URL linked from two different pages should list both referrers."""
    # Root page links to both page1 and page2, which in turn each link to broken.html.
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body=(
            '<html><body>'
            '<a href="/docs/page1.html">p1</a>'
            '<a href="/docs/page2.html">p2</a>'
            '</body></html>'
        ),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/page1.html',
        body='<html><body><a href="/docs/broken.html">x</a></body></html>',
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/page2.html',
        body='<html><body><a href="/docs/broken.html">x</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/broken.html', status=404)
    cfg = _cfg()
    results = _crawl(cfg)

    broken = results.broken_links
    assert len(broken) == 1
    entry = broken[0]
    assert entry.url == 'https://example.com/docs/broken.html'
    assert sorted(entry.referencing_pages) == [
        'https://example.com/docs/page1.html',
        'https://example.com/docs/page2.html',
    ]


# ---------------------------------------------------------------------------
# Network error (non-SSL) on internal page
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_network_error_on_internal_page_recorded_as_broken_link() -> None:
    """A connection error on an internal GET must record a broken link."""
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="/docs/page.html">p</a></body></html>',
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/page.html',
        body=requests.exceptions.ConnectionError('connection refused'),
    )
    cfg = _cfg(root_url='https://example.com/docs/')
    results = _crawl(cfg)
    broken_urls = [bl.url for bl in results.broken_links]
    assert 'https://example.com/docs/page.html' in broken_urls


# ---------------------------------------------------------------------------
# Fragment on internal page that returns an error
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_fragment_on_internal_error_page_recorded_as_unvalidated() -> None:
    """When an internal page GET fails, a fragment on that URL must be
    recorded as unvalidated (not crash)."""
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body><a href="/docs/bad.html#sec1">link</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/bad.html', status=500)
    cfg = _cfg()
    results = _crawl(cfg)
    unvalidated = [a.target_url for a in results.unvalidated_anchors]
    assert 'https://example.com/docs/bad.html#sec1' in unvalidated


# ---------------------------------------------------------------------------
# abort() and results property
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_abort_stops_crawl_and_results_accessible() -> None:
    """abort() must set the abort event; results property returns the same
    object as crawl() returns."""
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><body></body></html>',
        status=200,
    )
    cfg = _cfg()
    crawler = _make_crawler(cfg)
    # results property is accessible before crawl.
    assert crawler.results is not None
    results = crawler.crawl()
    # results property must return the same object as crawl().
    assert crawler.results is results
    # abort() is callable after crawl finishes without error.
    crawler.abort()


# ---------------------------------------------------------------------------
# Misplaced asset with no file extension (no asset type → not recorded)
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_misplaced_asset_no_extension_not_recorded() -> None:
    """An asset URL with no file extension must not be added to misplaced_assets."""
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body='<html><head><link rel="stylesheet" href="https://cdn.example.net/style"></head></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://cdn.example.net/style', status=200)
    cfg = _cfg_with(asset_urls=('https://example.com/docs/assets',))
    results = _crawl(cfg)
    assert results.misplaced_assets == []


# ---------------------------------------------------------------------------
# Already-visited URL: IGNORED disposition re-records referrer
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_already_visited_ignored_url_accumulates_referrers() -> None:
    """An ignored URL seen from two pages must list both referrers."""
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body=(
            '<html><body>'
            '<a href="/docs/page1.html">p1</a>'
            '<a href="/docs/page2.html">p2</a>'
            '</body></html>'
        ),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/page1.html',
        body='<html><body><a href="https://example.com/docs/skip/x.html">x</a></body></html>',
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/page2.html',
        body='<html><body><a href="https://example.com/docs/skip/x.html">x</a></body></html>',
        status=200,
    )
    cfg = _cfg_with(ignore_urls=('https://example.com/docs/skip',))
    results = _crawl(cfg)
    matches = [m for m in results.ignore_matches if m.url == 'https://example.com/docs/skip/x.html']
    assert matches
    assert len(matches[0].referencing_pages) == 2
    """A redirecting URL linked from two pages should list both referrers."""
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/',
        body=(
            '<html><body>'
            '<a href="/docs/page1.html">p1</a>'
            '<a href="/docs/page2.html">p2</a>'
            '</body></html>'
        ),
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/page1.html',
        body='<html><body><a href="/docs/old.html">x</a></body></html>',
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/page2.html',
        body='<html><body><a href="/docs/old.html">x</a></body></html>',
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/old.html',
        headers={'Location': 'https://example.com/docs/new.html'},
        status=301,
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs/new.html',
        body='<html><body></body></html>',
        status=200,
    )
    cfg = _cfg()
    results = _crawl(cfg)

    redirects = results.redirects
    assert len(redirects) == 1
    entry = redirects[0]
    assert entry.original_url == 'https://example.com/docs/old.html'
    assert sorted(entry.referencing_pages) == [
        'https://example.com/docs/page1.html',
        'https://example.com/docs/page2.html',
    ]

