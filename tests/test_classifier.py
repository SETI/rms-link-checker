"""Tests for classifier module."""

from __future__ import annotations

import argparse
from dataclasses import replace

import pytest

from link_checker.classifier import (
    AssetType,
    UrlDisposition,
    classify_asset,
    classify_url,
    is_misplaced_asset,
)
from link_checker.config import CrawlConfig, load_config


def _cfg(
    root_url: str = 'https://example.com/docs',
    max_depth: int | None = None,
) -> CrawlConfig:
    """Build a minimal CrawlConfig for testing."""
    return load_config(
        argparse.Namespace(
            root_url=root_url,
            timeout=None,
            retries=None,
            max_requests=None,
            max_depth=max_depth,
            max_threads=None,
            max_referencing_pages=None,
            log_level=None,
            output=None,
            log_file=None,
            config_file=None,
        ),
    )


def _cfg_with_lists(
    root_url: str = 'https://example.com/docs',
    asset_urls: tuple[str, ...] = (),
    no_crawl_urls: tuple[str, ...] = (),
    ignore_urls: tuple[str, ...] = (),
    max_depth: int | None = None,
) -> CrawlConfig:
    """Build a CrawlConfig with URL lists."""
    ns = argparse.Namespace(
        root_url=root_url,
        timeout=None,
        retries=None,
        max_requests=None,
        max_depth=max_depth,
        max_threads=None,
        max_referencing_pages=None,
        log_level=None,
        output=None,
        log_file=None,
        config_file=None,
    )
    return replace(
        load_config(ns),
        asset_urls=asset_urls,
        no_crawl_urls=no_crawl_urls,
        ignore_urls=ignore_urls,
    )


# ---------------------------------------------------------------------------
# classify_asset
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'ext',
    ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.bmp', '.tiff', '.tif', '.avif'],
)
def test_classify_asset_image(ext: str) -> None:
    assert classify_asset(ext) == AssetType.IMAGE


@pytest.mark.parametrize(
    'ext',
    ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv', '.rtf', '.odt'],
)
def test_classify_asset_document(ext: str) -> None:
    assert classify_asset(ext) == AssetType.DOCUMENT


@pytest.mark.parametrize('ext', ['.tab', '.xml', '.lbl', '.lblx', '.img'])
def test_classify_asset_data(ext: str) -> None:
    assert classify_asset(ext) == AssetType.DATA


@pytest.mark.parametrize(
    'ext',
    ['.js', '.mjs', '.css', '.woff', '.woff2', '.ttf', '.eot', '.otf', '.map', '.json'],
)
def test_classify_asset_infrastructure(ext: str) -> None:
    assert classify_asset(ext) == AssetType.INFRASTRUCTURE


@pytest.mark.parametrize('ext', ['.zip', '.exe', '.xyz', '.unknown'])
def test_classify_asset_other(ext: str) -> None:
    assert classify_asset(ext) == AssetType.OTHER


# ---------------------------------------------------------------------------
# classify_url: NON_HTTP
# ---------------------------------------------------------------------------


def test_classify_url_non_http_mailto() -> None:
    cfg = _cfg()
    result = classify_url(
        'mailto:user@example.com',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=0,
    )
    assert result == UrlDisposition.NON_HTTP


def test_classify_url_non_http_tel() -> None:
    cfg = _cfg()
    result = classify_url(
        'tel:+1-555-0100',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=0,
    )
    assert result == UrlDisposition.NON_HTTP


def test_classify_url_non_http_javascript() -> None:
    cfg = _cfg()
    result = classify_url(
        'javascript:void(0)',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=0,
    )
    assert result == UrlDisposition.NON_HTTP


# ---------------------------------------------------------------------------
# classify_url: IGNORED
# ---------------------------------------------------------------------------


def test_classify_url_ignored() -> None:
    cfg = _cfg_with_lists(ignore_urls=('https://example.com/legacy',))
    result = classify_url(
        'https://example.com/legacy/old.html',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=0,
    )
    assert result == UrlDisposition.IGNORED


def test_classify_url_not_ignored_when_no_match() -> None:
    cfg = _cfg_with_lists(ignore_urls=('https://example.com/legacy',))
    result = classify_url(
        'https://example.com/docs/page.html',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=0,
    )
    assert result != UrlDisposition.IGNORED


# ---------------------------------------------------------------------------
# classify_url: ALREADY_VISITED
# ---------------------------------------------------------------------------


def test_classify_url_already_visited() -> None:
    cfg = _cfg()
    visited = {'https://example.com/docs/page.html'}
    result = classify_url(
        'https://example.com/docs/page.html',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=visited,
        depth=1,
    )
    assert result == UrlDisposition.ALREADY_VISITED


# ---------------------------------------------------------------------------
# classify_url: NO_CRAWL
# ---------------------------------------------------------------------------


def test_classify_url_no_crawl() -> None:
    cfg = _cfg_with_lists(no_crawl_urls=('https://example.com/archive',))
    result = classify_url(
        'https://example.com/archive/page.html',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=0,
    )
    assert result == UrlDisposition.NO_CRAWL


# ---------------------------------------------------------------------------
# classify_url: EXTERNAL
# ---------------------------------------------------------------------------


def test_classify_url_external_different_domain() -> None:
    cfg = _cfg()
    result = classify_url(
        'https://external.com/page',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=0,
    )
    assert result == UrlDisposition.EXTERNAL


def test_classify_url_external_subdomain() -> None:
    cfg = _cfg()
    result = classify_url(
        'https://sub.example.com/docs/page',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=0,
    )
    assert result == UrlDisposition.EXTERNAL


def test_classify_url_external_path_above_root() -> None:
    cfg = _cfg()
    result = classify_url(
        'https://example.com/other',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=0,
    )
    assert result == UrlDisposition.EXTERNAL


# ---------------------------------------------------------------------------
# classify_url: DEPTH_LIMITED
# ---------------------------------------------------------------------------


def test_classify_url_beyond_depth() -> None:
    cfg = _cfg_with_lists(max_depth=1)
    result = classify_url(
        'https://example.com/docs/a/b/deep.html',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=3,
    )
    assert result == UrlDisposition.DEPTH_LIMITED


def test_classify_url_at_max_depth_is_not_limited() -> None:
    cfg = _cfg_with_lists(max_depth=2)
    result = classify_url(
        'https://example.com/docs/a/b.html',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=2,
    )
    assert result in (UrlDisposition.INTERNAL_CRAWL, UrlDisposition.INTERNAL_ASSET)


# ---------------------------------------------------------------------------
# classify_url: INTERNAL_CRAWL and INTERNAL_ASSET
# ---------------------------------------------------------------------------


def test_classify_url_internal_html_is_crawl() -> None:
    cfg = _cfg()
    result = classify_url(
        'https://example.com/docs/guide.html',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=1,
    )
    assert result == UrlDisposition.INTERNAL_CRAWL


def test_classify_url_internal_no_extension_is_crawl() -> None:
    cfg = _cfg()
    result = classify_url(
        'https://example.com/docs/about',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=1,
    )
    assert result == UrlDisposition.INTERNAL_CRAWL


def test_classify_url_internal_asset_jpg() -> None:
    cfg = _cfg()
    result = classify_url(
        'https://example.com/docs/image.jpg',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=1,
    )
    assert result == UrlDisposition.INTERNAL_ASSET


def test_classify_url_no_depth_limit_not_limited() -> None:
    cfg = _cfg()
    result = classify_url(
        'https://example.com/docs/a/b/c/d/e.html',
        config=cfg,
        root_url='https://example.com/docs',
        root_path='/docs',
        visited_set=set(),
        depth=5,
    )
    assert result in (UrlDisposition.INTERNAL_CRAWL, UrlDisposition.INTERNAL_ASSET)


# ---------------------------------------------------------------------------
# is_misplaced_asset
# ---------------------------------------------------------------------------


def test_is_misplaced_asset_true_when_not_in_asset_urls() -> None:
    cfg = _cfg_with_lists(asset_urls=('https://example.com/static',))
    assert (
        is_misplaced_asset(
            'https://example.com/docs/img.jpg',
            config=cfg,
            root_url='https://example.com/docs',
            root_path='/docs',
        )
        is True
    )


def test_is_misplaced_asset_false_when_in_asset_urls() -> None:
    cfg = _cfg_with_lists(asset_urls=('https://example.com/static',))
    assert (
        is_misplaced_asset(
            'https://example.com/static/img.jpg',
            config=cfg,
            root_url='https://example.com/docs',
            root_path='/docs',
        )
        is False
    )


def test_is_misplaced_asset_false_external() -> None:
    cfg = _cfg_with_lists(asset_urls=('https://example.com/static',))
    assert (
        is_misplaced_asset(
            'https://cdn.example.com/img.jpg',
            config=cfg,
            root_url='https://example.com/docs',
            root_path='/docs',
        )
        is False
    )


def test_is_misplaced_asset_false_when_ignored() -> None:
    cfg = _cfg_with_lists(
        asset_urls=('https://example.com/static',),
        ignore_urls=('https://example.com/legacy',),
    )
    assert (
        is_misplaced_asset(
            'https://example.com/legacy/img.jpg',
            config=cfg,
            root_url='https://example.com/docs',
            root_path='/docs',
        )
        is False
    )


def test_is_misplaced_asset_false_when_no_crawl() -> None:
    cfg = _cfg_with_lists(
        asset_urls=('https://example.com/static',),
        no_crawl_urls=('https://example.com/archive',),
    )
    assert (
        is_misplaced_asset(
            'https://example.com/archive/img.jpg',
            config=cfg,
            root_url='https://example.com/docs',
            root_path='/docs',
        )
        is False
    )


def test_is_misplaced_asset_false_when_no_asset_urls_configured() -> None:
    cfg = _cfg()
    assert (
        is_misplaced_asset(
            'https://example.com/docs/img.jpg',
            config=cfg,
            root_url='https://example.com/docs',
            root_path='/docs',
        )
        is False
    )
