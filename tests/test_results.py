"""Tests for results module."""

from __future__ import annotations

import threading

from link_checker.results import CrawlResults


def test_add_broken_link_records_url() -> None:
    r = CrawlResults()
    r.add_broken_link('https://example.com/missing', 404, 'Not Found', 'https://example.com/')
    assert len(r.broken_links) == 1
    assert r.broken_links[0].url == 'https://example.com/missing'


def test_add_broken_link_records_referrer() -> None:
    r = CrawlResults()
    r.add_broken_link('https://example.com/missing', 404, 'Not Found', 'https://example.com/')
    assert 'https://example.com/' in r.broken_links[0].referencing_pages


def test_add_broken_link_multiple_referrers() -> None:
    r = CrawlResults()
    r.add_broken_link('https://example.com/missing', 404, 'Not Found', 'https://example.com/a')
    r.add_broken_link('https://example.com/missing', 404, 'Not Found', 'https://example.com/b')
    assert len(r.broken_links[0].referencing_pages) == 2


def test_add_broken_link_no_duplicate_referrers() -> None:
    r = CrawlResults()
    r.add_broken_link('https://example.com/missing', 404, 'Not Found', 'https://example.com/')
    r.add_broken_link('https://example.com/missing', 404, 'Not Found', 'https://example.com/')
    assert len(r.broken_links[0].referencing_pages) == 1


def test_add_redirect_records_info() -> None:
    r = CrawlResults()
    r.add_redirect(
        'https://example.com/old', 'https://example.com/new', 301, 'https://example.com/'
    )
    assert len(r.redirects) == 1
    rdr = r.redirects[0]
    assert rdr.original_url == 'https://example.com/old'
    assert rdr.final_url == 'https://example.com/new'
    assert rdr.status_code == 301


def test_add_broken_anchor_records() -> None:
    r = CrawlResults()
    r.add_broken_anchor('https://example.com/page#missing', 'https://example.com/src')
    assert len(r.broken_anchors) == 1
    assert r.broken_anchors[0].target_url == 'https://example.com/page#missing'


def test_add_unvalidated_anchor_records() -> None:
    r = CrawlResults()
    r.add_unvalidated_anchor('https://example.com/page#s', 'external', 'https://example.com/src')
    assert len(r.unvalidated_anchors) == 1
    assert r.unvalidated_anchors[0].reason == 'external'


def test_add_non_http_link_records() -> None:
    r = CrawlResults()
    r.add_non_http_link('mailto:user@example.com', 'mailto', 'https://example.com/')
    assert len(r.non_http_links) == 1
    assert r.non_http_links[0].scheme == 'mailto'


def test_add_ignore_match_records() -> None:
    r = CrawlResults()
    r.add_ignore_match('https://example.com/legacy/old', 'https://example.com/')
    assert len(r.ignore_matches) == 1


def test_add_no_crawl_match_records() -> None:
    r = CrawlResults()
    r.add_no_crawl_match('https://example.com/archive/p', 'https://example.com/')
    assert len(r.no_crawl_matches) == 1


def test_add_ssl_warning_records() -> None:
    r = CrawlResults()
    r.add_ssl_warning(
        'https://bad.example.com/page',
        'bad.example.com',
        'cert expired',
        'https://example.com/',
    )
    assert len(r.ssl_warnings) == 1
    assert r.ssl_warnings[0].domain == 'bad.example.com'


def test_add_misplaced_asset_records() -> None:
    r = CrawlResults()
    r.add_misplaced_asset('https://example.com/docs/img.jpg', 'Image', 'https://example.com/')
    assert len(r.misplaced_assets) == 1
    assert r.misplaced_assets[0].asset_type == 'Image'


def test_record_request_increments_total() -> None:
    r = CrawlResults()
    r.record_request('https://example.com/page')
    r.record_request('https://example.com/page2')
    assert r.statistics.total_requests == 2


def test_record_request_tracks_bytes() -> None:
    r = CrawlResults()
    r.record_request('https://example.com/page', bytes_downloaded=500)
    assert r.statistics.bytes_downloaded == 500


def test_record_request_tracks_per_domain() -> None:
    r = CrawlResults()
    r.record_request('https://example.com/page')
    r.record_request('https://example.com/page2')
    r.record_request('https://external.com/page')
    assert r.statistics.per_domain_requests['example.com'] == 2
    assert r.statistics.per_domain_requests['external.com'] == 1


def test_has_problems_false_when_clean() -> None:
    r = CrawlResults()
    assert r.has_problems() is False


def test_has_problems_true_with_broken_link() -> None:
    r = CrawlResults()
    r.add_broken_link('https://example.com/missing', 404, 'Not Found', 'https://example.com/')
    assert r.has_problems() is True


def test_thread_safety_concurrent_adds() -> None:
    r = CrawlResults()
    threads = []
    for i in range(50):
        t = threading.Thread(
            target=r.add_broken_link,
            args=(f'https://example.com/p{i}', 404, 'Not Found', 'https://example.com/'),
        )
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(r.broken_links) == 50


def test_thread_safety_broken_link_deduplication() -> None:
    """Many threads adding the same broken URL with distinct referrers must produce
    exactly one BrokenLink entry whose referencing_pages contains every referrer."""
    r = CrawlResults()
    n = 50
    referrers = [f'https://example.com/page{i}' for i in range(n)]
    threads = [
        threading.Thread(
            target=r.add_broken_link,
            args=('https://example.com/broken', 404, 'Not Found', ref),
        )
        for ref in referrers
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(r.broken_links) == 1
    entry = r.broken_links[0]
    assert entry.url == 'https://example.com/broken'
    assert sorted(entry.referencing_pages) == sorted(referrers)


def test_thread_safety_record_request() -> None:
    r = CrawlResults()
    threads = []
    for i in range(100):
        t = threading.Thread(
            target=r.record_request,
            args=(f'https://example.com/p{i}',),
        )
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert r.statistics.total_requests == 100


def test_non200_records() -> None:
    r = CrawlResults()
    r.add_non200('https://example.com/forbidden', 403, 'https://example.com/')
    assert len(r.non200_responses) == 1
    assert r.non200_responses[0].status_code == 403
