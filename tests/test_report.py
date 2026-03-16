"""Tests for report module."""

from __future__ import annotations

import argparse
import re
from dataclasses import replace

from link_checker.config import CrawlConfig, load_config
from link_checker.report import generate_report
from link_checker.results import CrawlResults


def _cfg(
    root_url: str = 'https://example.com/docs',
    max_referencing_pages: int = 10,
) -> CrawlConfig:
    return load_config(
        argparse.Namespace(
            root_url=root_url,
            timeout=None,
            retries=None,
            max_requests=None,
            max_depth=None,
            max_threads=None,
            max_referencing_pages=max_referencing_pages,
            log_level=None,
            output=None,
            log_file=None,
            config_file=None,
        )
    )


# ---------------------------------------------------------------------------
# §10.1 Configuration Summary
# ---------------------------------------------------------------------------


def test_report_config_summary_header() -> None:
    r = CrawlResults()
    report = generate_report(r, _cfg())
    assert '=== Configuration Summary ===' in report


def test_report_config_summary_root_url() -> None:
    r = CrawlResults()
    report = generate_report(r, _cfg())
    assert 'Root URL:        https://example.com/docs' in report


def test_report_config_summary_defaults() -> None:
    r = CrawlResults()
    report = generate_report(r, _cfg())
    assert 'Timeout:         10s' in report
    assert 'Retries:         3' in report
    assert 'Max threads:     10' in report
    assert 'Max depth:       unlimited' in report
    assert 'Max requests:    unlimited' in report
    assert 'Max ref. pages:  10' in report


def test_report_config_summary_asset_urls() -> None:
    cfg = replace(_cfg(), asset_urls=('https://example.com/static',))
    r = CrawlResults()
    report = generate_report(r, cfg)
    assert 'Asset URL prefixes:' in report
    assert '  - https://example.com/static' in report


# ---------------------------------------------------------------------------
# §10.2 Statistics Summary
# ---------------------------------------------------------------------------


def test_report_statistics_header() -> None:
    r = CrawlResults()
    report = generate_report(r, _cfg())
    assert '=== Statistics Summary ===' in report


def test_report_statistics_requests() -> None:
    r = CrawlResults()
    r.record_request('https://example.com/page')
    report = generate_report(r, _cfg())
    assert 'Total HTTP requests:     1' in report


def test_report_statistics_per_domain() -> None:
    r = CrawlResults()
    r.record_request('https://example.com/page')
    r.record_request('https://example.com/page2')
    report = generate_report(r, _cfg())
    assert 'Per-domain request breakdown:' in report
    assert 'example.com:  2' in report


# ---------------------------------------------------------------------------
# §10.3 Broken Links
# ---------------------------------------------------------------------------


def test_report_broken_links_header_count() -> None:
    r = CrawlResults()
    r.add_broken_link(
        url='https://example.com/missing',
        status_code=404,
        error='404 Not Found',
        referrer='https://example.com/',
    )
    report = generate_report(r, _cfg())
    assert '=== Broken Links (1) ===' in report


def test_report_broken_links_shows_url_and_error() -> None:
    r = CrawlResults()
    r.add_broken_link(
        url='https://example.com/missing',
        status_code=404,
        error='404 Not Found',
        referrer='https://example.com/',
    )
    report = generate_report(r, _cfg())
    assert 'https://example.com/missing' in report
    assert '404 Not Found' in report


def test_report_broken_links_grouped_by_page() -> None:
    r = CrawlResults()
    r.add_broken_link(
        url='https://example.com/missing',
        status_code=404,
        error='404 Not Found',
        referrer='https://example.com/src',
    )
    report = generate_report(r, _cfg())
    assert 'Page: https://example.com/src' in report


def test_report_broken_links_zero() -> None:
    r = CrawlResults()
    report = generate_report(r, _cfg())
    assert '=== Broken Links (0) ===' in report


# ---------------------------------------------------------------------------
# §10.4 Broken Anchors
# ---------------------------------------------------------------------------


def test_report_broken_anchors_header_count() -> None:
    r = CrawlResults()
    r.add_broken_anchor(
        target_url='https://example.com/page#missing', referrer='https://example.com/'
    )
    report = generate_report(r, _cfg())
    assert '=== Broken Anchors (1) ===' in report


def test_report_broken_anchors_shows_target() -> None:
    r = CrawlResults()
    r.add_broken_anchor(
        target_url='https://example.com/page#missing', referrer='https://example.com/'
    )
    report = generate_report(r, _cfg())
    assert 'Target: https://example.com/page#missing' in report


# ---------------------------------------------------------------------------
# §10.5 Non-200 Responses
# ---------------------------------------------------------------------------


def test_report_non200_header() -> None:
    r = CrawlResults()
    r.add_non200(
        url='https://example.com/forbidden', status_code=403, referrer='https://example.com/'
    )
    report = generate_report(r, _cfg())
    assert '=== Non-200 Responses (1) ===' in report


def test_report_non200_grouped_by_status() -> None:
    r = CrawlResults()
    r.add_non200(
        url='https://example.com/forbidden', status_code=403, referrer='https://example.com/'
    )
    report = generate_report(r, _cfg())
    assert '403 Forbidden:' in report


# ---------------------------------------------------------------------------
# §10.6 Redirects
# ---------------------------------------------------------------------------


def test_report_redirects_header_count() -> None:
    r = CrawlResults()
    r.add_redirect(
        original_url='https://example.com/old',
        final_url='https://example.com/new',
        status_code=301,
        referrer='https://example.com/',
    )
    report = generate_report(r, _cfg())
    assert '=== Redirects (1) ===' in report


def test_report_redirects_shows_chain() -> None:
    r = CrawlResults()
    r.add_redirect(
        original_url='https://example.com/old',
        final_url='https://example.com/new',
        status_code=301,
        referrer='https://example.com/',
    )
    report = generate_report(r, _cfg())
    assert 'https://example.com/old  →  https://example.com/new (301)' in report


# ---------------------------------------------------------------------------
# §10.7 Misplaced Assets
# ---------------------------------------------------------------------------


def test_report_misplaced_assets_header_count() -> None:
    r = CrawlResults()
    r.add_misplaced_asset(
        url='https://example.com/docs/img.jpg', asset_type='Image', referrer='https://example.com/'
    )
    report = generate_report(r, _cfg())
    assert '=== Misplaced Assets (1) ===' in report


def test_report_misplaced_assets_grouped_by_type() -> None:
    r = CrawlResults()
    r.add_misplaced_asset(
        url='https://example.com/docs/img.jpg', asset_type='Image', referrer='https://example.com/'
    )
    report = generate_report(r, _cfg())
    assert 'Image:' in report


def test_report_misplaced_assets_none_for_empty_type() -> None:
    r = CrawlResults()
    r.add_misplaced_asset(
        url='https://example.com/docs/img.jpg', asset_type='Image', referrer='https://example.com/'
    )
    report = generate_report(r, _cfg())
    assert 'Document:\n  (none)' in report


# ---------------------------------------------------------------------------
# §10.9 Ignore URL Matches
# ---------------------------------------------------------------------------


def test_report_ignore_matches_header() -> None:
    r = CrawlResults()
    r.add_ignore_match(url='https://example.com/legacy/old', referrer='https://example.com/')
    report = generate_report(r, _cfg())
    assert '=== Ignore URL Matches (1) ===' in report


# ---------------------------------------------------------------------------
# §10.10 Non-HTTP Scheme Links
# ---------------------------------------------------------------------------


def test_report_non_http_links_header() -> None:
    r = CrawlResults()
    r.add_non_http_link(
        url='mailto:user@example.com', scheme='mailto', referrer='https://example.com/'
    )
    report = generate_report(r, _cfg())
    assert '=== Non-HTTP Scheme Links (1) ===' in report


def test_report_non_http_links_shows_url() -> None:
    r = CrawlResults()
    r.add_non_http_link(
        url='mailto:user@example.com', scheme='mailto', referrer='https://example.com/'
    )
    report = generate_report(r, _cfg())
    assert 'mailto:user@example.com' in report


# ---------------------------------------------------------------------------
# §10.11 SSL Warnings
# ---------------------------------------------------------------------------


def test_report_ssl_warnings_header() -> None:
    r = CrawlResults()
    r.add_ssl_warning(
        url='https://bad.example.com/p',
        domain='bad.example.com',
        error='cert expired',
        referrer='https://example.com/',
    )
    report = generate_report(r, _cfg())
    assert '=== SSL Warnings (1 domain) ===' in report


def test_report_ssl_warnings_grouped_by_domain() -> None:
    r = CrawlResults()
    r.add_ssl_warning(
        url='https://bad.example.com/p1',
        domain='bad.example.com',
        error='cert expired',
        referrer='https://example.com/a',
    )
    r.add_ssl_warning(
        url='https://bad.example.com/p2',
        domain='bad.example.com',
        error='cert expired',
        referrer='https://example.com/b',
    )
    report = generate_report(r, _cfg())
    assert 'bad.example.com — cert expired' in report
    # Only one domain group
    assert report.count('bad.example.com — cert expired') == 1


def test_report_ssl_warnings_plural_domains() -> None:
    r = CrawlResults()
    r.add_ssl_warning(
        url='https://a.example.com/p',
        domain='a.example.com',
        error='err',
        referrer='https://example.com/',
    )
    r.add_ssl_warning(
        url='https://b.example.com/p',
        domain='b.example.com',
        error='err',
        referrer='https://example.com/',
    )
    report = generate_report(r, _cfg())
    assert '=== SSL Warnings (2 domains) ===' in report


# ---------------------------------------------------------------------------
# §10.12 Unvalidated Anchors
# ---------------------------------------------------------------------------


def test_report_unvalidated_anchors_header() -> None:
    r = CrawlResults()
    r.add_unvalidated_anchor(
        target_url='https://example.com/page#s', reason='external', referrer='https://example.com/'
    )
    report = generate_report(r, _cfg())
    assert '=== Unvalidated Anchors (1) ===' in report


def test_report_unvalidated_anchors_shows_reason() -> None:
    r = CrawlResults()
    r.add_unvalidated_anchor(
        target_url='https://example.com/page#s', reason='no-crawl', referrer='https://example.com/'
    )
    report = generate_report(r, _cfg())
    assert 'https://example.com/page#s (no-crawl)' in report


# ---------------------------------------------------------------------------
# §10.13 Referencing page truncation
# ---------------------------------------------------------------------------


def test_report_referencing_page_truncation() -> None:
    r = CrawlResults()
    for i in range(15):
        r.add_broken_anchor(
            target_url='https://example.com/page#missing',
            referrer=f'https://example.com/page{i}',
        )
    report = generate_report(r, _cfg(max_referencing_pages=10))
    assert '... and 5 more referencing pages' in report


def test_report_no_truncation_when_under_limit() -> None:
    r = CrawlResults()
    for i in range(5):
        r.add_broken_anchor(
            target_url='https://example.com/page#missing',
            referrer=f'https://example.com/page{i}',
        )
    report = generate_report(r, _cfg(max_referencing_pages=10))
    assert 'more referencing pages' not in report


# ---------------------------------------------------------------------------
# All sections present in a complete report
# ---------------------------------------------------------------------------


def test_report_contains_all_sections() -> None:
    r = CrawlResults()
    report = generate_report(r, _cfg())
    assert '=== Configuration Summary ===' in report
    assert '=== Statistics Summary ===' in report
    assert '=== Broken Links (0) ===' in report
    assert '=== Broken Anchors (0) ===' in report
    assert '=== Non-200 Responses (0) ===' in report
    assert '=== Redirects (0) ===' in report
    assert '=== Misplaced Assets (0) ===' in report
    assert '=== Ignore URL Matches (0) ===' in report
    assert '=== Non-HTTP Scheme Links (0) ===' in report
    assert '=== SSL Warnings (0 domains) ===' in report
    assert '=== Unvalidated Anchors (0) ===' in report
    assert '=== No-Crawl URL Matches' not in report


def test_report_sections_separated_by_two_blank_lines() -> None:
    r = CrawlResults()
    report = generate_report(r, _cfg())

    headers = list(re.finditer(r'=== ', report))
    assert len(headers) == 11
    for match in headers[1:]:
        assert report[match.start() - 2 : match.start()] == '\n\n', (
            f'Expected two blank lines before section at position {match.start()}'
        )


# ---------------------------------------------------------------------------
# Config summary: no_crawl_urls and ignore_urls
# ---------------------------------------------------------------------------


def test_report_config_summary_no_crawl_urls() -> None:
    cfg = replace(_cfg(), no_crawl_urls=('https://example.com/archive',))
    r = CrawlResults()
    report = generate_report(r, cfg)
    assert 'No-crawl URL prefixes:' in report
    assert '  - https://example.com/archive' in report


def test_report_config_summary_ignore_urls() -> None:
    cfg = replace(_cfg(), ignore_urls=('https://example.com/skip',))
    r = CrawlResults()
    report = generate_report(r, cfg)
    assert 'Ignore URL prefixes:' in report
    assert '  - https://example.com/skip' in report


# ---------------------------------------------------------------------------
# Truncation "+N more" lines in each section
# ---------------------------------------------------------------------------


def test_broken_links_truncation_more_line() -> None:
    r = CrawlResults()
    cfg = replace(_cfg(), max_referencing_pages=1)
    r.add_broken_anchor(target_url='https://example.com/page#missing', referrer='ref1')
    r.add_broken_anchor(target_url='https://example.com/page#missing', referrer='ref2')
    report = generate_report(r, cfg)
    assert '... and 1 more referencing pages' in report


def test_non200_truncation_more_line() -> None:
    r = CrawlResults()
    cfg = replace(_cfg(), max_referencing_pages=1)
    r.add_non200(url='https://example.com/gone', status_code=404, referrer='ref1')
    r.add_non200(url='https://example.com/gone', status_code=404, referrer='ref2')
    report = generate_report(r, cfg)
    assert '... and 1 more referencing pages' in report


def test_redirects_truncation_more_line() -> None:
    r = CrawlResults()
    cfg = replace(_cfg(), max_referencing_pages=1)
    r.add_redirect(
        original_url='https://example.com/old',
        final_url='https://example.com/new',
        status_code=301,
        referrer='ref1',
    )
    r.add_redirect(
        original_url='https://example.com/old',
        final_url='https://example.com/new',
        status_code=301,
        referrer='ref2',
    )
    report = generate_report(r, cfg)
    assert '... and 1 more referencing pages' in report


def test_ignore_matches_truncation_more_line() -> None:
    r = CrawlResults()
    cfg = replace(_cfg(), max_referencing_pages=1)
    r.add_ignore_match(url='https://example.com/skip', referrer='ref1')
    r.add_ignore_match(url='https://example.com/skip', referrer='ref2')
    report = generate_report(r, cfg)
    assert '... and 1 more referencing pages' in report


def test_non_http_links_truncation_more_line() -> None:
    r = CrawlResults()
    cfg = replace(_cfg(), max_referencing_pages=1)
    r.add_non_http_link(url='mailto:a@example.com', scheme='mailto', referrer='ref1')
    r.add_non_http_link(url='mailto:a@example.com', scheme='mailto', referrer='ref2')
    report = generate_report(r, cfg)
    assert '... and 1 more referencing pages' in report


def test_ssl_warnings_truncation_more_line() -> None:
    r = CrawlResults()
    cfg = replace(_cfg(), max_referencing_pages=1)
    r.add_ssl_warning(
        url='https://bad.example.com/x',
        domain='bad.example.com',
        error='err',
        referrer='ref1',
    )
    r.add_ssl_warning(
        url='https://bad.example.com/x',
        domain='bad.example.com',
        error='err',
        referrer='ref2',
    )
    report = generate_report(r, cfg)
    assert '... and 1 more referencing pages' in report


# ---------------------------------------------------------------------------
# _http_reason: unknown status code → empty string
# ---------------------------------------------------------------------------


def test_http_reason_unknown_status_returns_empty() -> None:
    from link_checker.report import _http_reason

    assert _http_reason(999) == ''
