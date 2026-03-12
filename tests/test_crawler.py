"""Tests for crawler module."""

from __future__ import annotations

import argparse

import responses as resp_lib

from link_checker.config import CrawlConfig, load_config
from link_checker.crawler import Crawler


def _cfg(**kwargs: object) -> CrawlConfig:
    defaults: dict[str, object] = {
        'root_url': 'https://example.com/docs',
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
    from dataclasses import replace

    base = _cfg(root_url=kwargs.pop('root_url', 'https://example.com/docs'))
    return replace(base, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Basic crawling
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_single_page_no_links() -> None:
    resp_lib.add(
        resp_lib.GET, 'https://example.com/docs', body='<html><body></body></html>', status=200
    )
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    assert results.statistics.total_requests == 1
    assert not results.broken_links


@resp_lib.activate
def test_two_pages_linked() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="/docs/page2.html">link</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/page2.html', body='<html/>', status=200)
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    assert results.statistics.total_requests == 2
    assert not results.broken_links


# ---------------------------------------------------------------------------
# External links
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_external_link_head_checked() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="https://external.com/page">ext</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://external.com/page', status=200)
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    assert results.statistics.external_checked == 1
    assert not results.broken_links


@resp_lib.activate
def test_external_link_head_405_falls_back() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="https://external.com/page">ext</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://external.com/page', status=405)
    resp_lib.add(resp_lib.GET, 'https://external.com/page', status=200)
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    assert not results.broken_links


# ---------------------------------------------------------------------------
# Broken links
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_broken_link_recorded() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="/docs/missing.html">m</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/missing.html', status=404)
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    broken_urls = [bl.url for bl in results.broken_links]
    assert 'https://example.com/docs/missing.html' in broken_urls


# ---------------------------------------------------------------------------
# Redirects
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_redirect_followed_and_recorded() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
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
    results = Crawler(cfg).crawl()
    redirect_originals = [r.original_url for r in results.redirects]
    assert 'https://example.com/docs/old.html' in redirect_originals


# ---------------------------------------------------------------------------
# Fragment validation
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_fragment_valid_anchor() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
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
    results = Crawler(cfg).crawl()
    assert not results.broken_anchors


@resp_lib.activate
def test_fragment_missing_anchor() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
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
    results = Crawler(cfg).crawl()
    assert any('bad' in ba.target_url for ba in results.broken_anchors)


@resp_lib.activate
def test_fragment_on_already_visited_page_no_refetch() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
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
    results = Crawler(cfg).crawl()
    assert not results.broken_anchors
    assert results.statistics.total_requests == 2


# ---------------------------------------------------------------------------
# Visit-once
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_visit_once_different_schemes() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
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
    results = Crawler(cfg).crawl()
    assert results.statistics.total_requests == 2


@resp_lib.activate
def test_visit_once_query_params_stripped() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body=(
            '<html><body>'
            '<a href="/docs/page.html?a=1">link1</a>'
            '<a href="/docs/page.html?b=2">link2</a>'
            '</body></html>'
        ),
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/page.html', body='<html/>', status=200)
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    assert results.statistics.total_requests == 2


# ---------------------------------------------------------------------------
# Depth limiting
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_depth_limit_enforced() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="/docs/level1/page.html">l1</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/docs/level1/page.html', status=200)
    cfg = _cfg_with(max_depth=0)
    results = Crawler(cfg).crawl()
    assert results.statistics.total_requests == 2
    assert results.statistics.pages_crawled == 1


# ---------------------------------------------------------------------------
# Max requests
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_max_requests_limit() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
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
    results = Crawler(cfg).crawl()
    assert results.statistics.total_requests <= 2


# ---------------------------------------------------------------------------
# No-crawl URLs
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_no_crawl_prefix_checked_not_crawled() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="https://example.com/archive/page.html">arch</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/archive/page.html', status=200)
    cfg = _cfg_with(no_crawl_urls=('https://example.com/archive',))
    results = Crawler(cfg).crawl()
    nc_urls = [m.url for m in results.no_crawl_matches]
    assert 'https://example.com/archive/page.html' in nc_urls


# ---------------------------------------------------------------------------
# Ignore URLs
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_ignore_prefix_not_checked() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="https://example.com/legacy/old.html">leg</a></body></html>',
        status=200,
    )
    cfg = _cfg_with(ignore_urls=('https://example.com/legacy',))
    results = Crawler(cfg).crawl()
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
        'https://example.com/docs',
        body='<html><body><a href="mailto:user@example.com">email</a></body></html>',
        status=200,
    )
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    non_http = [lk.url for lk in results.non_http_links]
    assert 'mailto:user@example.com' in non_http


# ---------------------------------------------------------------------------
# Asset classification
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_asset_classified_and_checked() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><img src="/docs/img/logo.png"></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/docs/img/logo.png', status=200)
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    assert results.statistics.total_requests == 2
    assert not results.broken_links


# ---------------------------------------------------------------------------
# Misplaced assets
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_misplaced_asset_detected() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><img src="/docs/img/logo.png"></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/docs/img/logo.png', status=200)
    cfg = _cfg_with(asset_urls=('https://example.com/static',))
    results = Crawler(cfg).crawl()
    misplaced_urls = [a.url for a in results.misplaced_assets]
    assert 'https://example.com/docs/img/logo.png' in misplaced_urls


@resp_lib.activate
def test_misplaced_asset_external_excluded() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><img src="https://cdn.external.com/logo.png"></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://cdn.external.com/logo.png', status=200)
    cfg = _cfg_with(asset_urls=('https://example.com/static',))
    results = Crawler(cfg).crawl()
    assert not results.misplaced_assets


@resp_lib.activate
def test_misplaced_asset_ignored_excluded() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><img src="/legacy/logo.png"></body></html>',
        status=200,
    )
    cfg = _cfg_with(
        asset_urls=('https://example.com/static',),
        ignore_urls=('https://example.com/legacy',),
    )
    results = Crawler(cfg).crawl()
    assert not results.misplaced_assets


# ---------------------------------------------------------------------------
# Subdomain treated as external
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_subdomain_treated_as_external() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="https://sub.example.com/page">sub</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://sub.example.com/page', status=200)
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    assert results.statistics.external_checked == 1


# ---------------------------------------------------------------------------
# Path above root not crawled
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_path_above_root_not_crawled() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="https://example.com/other">other</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/other', status=200)
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    assert results.statistics.external_checked == 1


# ---------------------------------------------------------------------------
# base href resolution
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_base_href_resolution() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body=(
            '<html><head><base href="https://example.com/docs/sub/"></head>'
            '<body><a href="page.html">p</a></body></html>'
        ),
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/sub/page.html', body='<html/>', status=200)
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    assert results.statistics.total_requests == 2


# ---------------------------------------------------------------------------
# SSL errors
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_ssl_error_warns_per_domain() -> None:
    import requests.exceptions

    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="https://bad-ssl.example.com/p">ssl</a></body></html>',
        status=200,
    )
    resp_lib.add(
        resp_lib.HEAD,
        'https://bad-ssl.example.com/p',
        body=requests.exceptions.SSLError('cert verify failed'),
    )
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    assert len(results.ssl_warnings) == 1
    assert results.ssl_warnings[0].domain == 'bad-ssl.example.com'


# ---------------------------------------------------------------------------
# Unvalidated anchors
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_unvalidated_anchor_on_no_crawl() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="https://example.com/archive/doc.html#intro">arch</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/archive/doc.html', status=200)
    cfg = _cfg_with(no_crawl_urls=('https://example.com/archive',))
    results = Crawler(cfg).crawl()
    unval = [ua.target_url for ua in results.unvalidated_anchors]
    assert 'https://example.com/archive/doc.html#intro' in unval


@resp_lib.activate
def test_unvalidated_anchor_on_external() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="https://external.com/api.html#auth">ext</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://external.com/api.html', status=200)
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    unval = [ua.target_url for ua in results.unvalidated_anchors]
    assert 'https://external.com/api.html#auth' in unval


@resp_lib.activate
def test_unvalidated_anchor_on_depth_limited() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="/docs/deep/page.html#note">deep</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.HEAD, 'https://example.com/docs/deep/page.html', status=200)
    cfg = _cfg_with(max_depth=0)
    results = Crawler(cfg).crawl()
    unval = [ua.target_url for ua in results.unvalidated_anchors]
    assert 'https://example.com/docs/deep/page.html#note' in unval


# ---------------------------------------------------------------------------
# Exit-code logic (via has_problems)
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_exit_code_0_clean() -> None:
    resp_lib.add(resp_lib.GET, 'https://example.com/docs', body='<html/>', status=200)
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    assert results.has_problems() is False


@resp_lib.activate
def test_exit_code_1_broken() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/docs',
        body='<html><body><a href="/docs/missing.html">m</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/docs/missing.html', status=404)
    cfg = _cfg()
    results = Crawler(cfg).crawl()
    assert results.has_problems() is True
