"""Tests for results module."""

from __future__ import annotations

import threading

from link_checker.results import CrawlResults


def test_add_broken_link_records_url() -> None:
    r = CrawlResults()
    r.add_broken_link(
        url='https://example.com/missing',
        status_code=404,
        error='Not Found',
        referrer='https://example.com/',
    )
    assert len(r.broken_links) == 1
    assert r.broken_links[0].url == 'https://example.com/missing'


def test_add_broken_link_records_referrer() -> None:
    r = CrawlResults()
    r.add_broken_link(
        url='https://example.com/missing',
        status_code=404,
        error='Not Found',
        referrer='https://example.com/',
    )
    assert 'https://example.com/' in r.broken_links[0].referencing_pages


def test_add_broken_link_multiple_referrers() -> None:
    r = CrawlResults()
    r.add_broken_link(
        url='https://example.com/missing',
        status_code=404,
        error='Not Found',
        referrer='https://example.com/a',
    )
    r.add_broken_link(
        url='https://example.com/missing',
        status_code=404,
        error='Not Found',
        referrer='https://example.com/b',
    )
    assert len(r.broken_links[0].referencing_pages) == 2


def test_add_broken_link_no_duplicate_referrers() -> None:
    r = CrawlResults()
    r.add_broken_link(
        url='https://example.com/missing',
        status_code=404,
        error='Not Found',
        referrer='https://example.com/',
    )
    r.add_broken_link(
        url='https://example.com/missing',
        status_code=404,
        error='Not Found',
        referrer='https://example.com/',
    )
    assert len(r.broken_links[0].referencing_pages) == 1


def test_add_redirect_records_info() -> None:
    r = CrawlResults()
    r.add_redirect(
        original_url='https://example.com/old',
        final_url='https://example.com/new',
        status_code=301,
        referrer='https://example.com/',
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
        url='https://bad.example.com/page',
        domain='bad.example.com',
        error='cert expired',
        referrer='https://example.com/',
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
    r.add_broken_link(
        url='https://example.com/missing',
        status_code=404,
        error='Not Found',
        referrer='https://example.com/',
    )
    assert r.has_problems() is True


def test_thread_safety_concurrent_adds() -> None:
    r = CrawlResults()
    threads = []
    for i in range(50):
        t = threading.Thread(
            target=r.add_broken_link,
            kwargs={
                'url': f'https://example.com/p{i}',
                'status_code': 404,
                'error': 'Not Found',
                'referrer': 'https://example.com/',
            },
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
            kwargs={
                'url': 'https://example.com/broken',
                'status_code': 404,
                'error': 'Not Found',
                'referrer': ref,
            },
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


def test_merge_referrer_broken_link() -> None:
    r = CrawlResults()
    r.add_broken_link(
        url='https://example.com/gone',
        status_code=404,
        error='404',
        referrer='https://example.com/page1',
    )
    r.merge_referrer('https://example.com/gone', 'https://example.com/page2')
    entry = r.broken_links[0]
    assert sorted(entry.referencing_pages) == [
        'https://example.com/page1',
        'https://example.com/page2',
    ]


def test_merge_referrer_redirect() -> None:
    r = CrawlResults()
    r.add_redirect(
        original_url='https://example.com/old',
        final_url='https://example.com/new',
        status_code=301,
        referrer='https://example.com/page1',
    )
    r.merge_referrer('https://example.com/old', 'https://example.com/page2')
    entry = r.redirects[0]
    assert sorted(entry.referencing_pages) == [
        'https://example.com/page1',
        'https://example.com/page2',
    ]


def test_merge_referrer_no_op_for_unknown_url() -> None:
    """merge_referrer must not create new entries for unknown URLs."""
    r = CrawlResults()
    r.merge_referrer('https://example.com/unknown', 'https://example.com/page1')
    assert r.broken_links == []
    assert r.redirects == []


def test_merge_referrer_deduplicates_referrer() -> None:
    """Calling merge_referrer twice with the same referrer must not duplicate it."""
    r = CrawlResults()
    r.add_broken_link(
        url='https://example.com/gone',
        status_code=404,
        error='404',
        referrer='https://example.com/page1',
    )
    r.merge_referrer('https://example.com/gone', 'https://example.com/page1')
    assert r.broken_links[0].referencing_pages == ['https://example.com/page1']


def test_accessors_return_snapshots_not_live_objects() -> None:
    """Mutating objects returned by accessors must not affect internal state."""
    r = CrawlResults()
    r.add_broken_link(
        url='https://example.com/gone',
        status_code=404,
        error='404',
        referrer='https://example.com/ref1',
    )
    r.add_redirect(
        original_url='https://example.com/old',
        final_url='https://example.com/new',
        status_code=301,
        referrer='https://example.com/ref1',
    )
    r.add_broken_anchor('https://example.com/page#missing', 'https://example.com/ref1')
    r.add_non200('https://example.com/gone', 404, 'https://example.com/ref1')
    r.add_ssl_warning(
        url='https://bad.example.com/x',
        domain='bad.example.com',
        error='SSL fail',
        referrer='https://example.com/ref1',
    )

    # Mutate every returned snapshot.
    r.broken_links[0].referencing_pages.append('INJECTED')
    r.redirects[0].referencing_pages.append('INJECTED')
    r.broken_anchors[0].referencing_pages.append('INJECTED')
    r.non200_responses[0].referencing_pages.append('INJECTED')
    r.ssl_warnings[0].affected_urls[0][1].append('INJECTED')

    # Internal state must be unchanged.
    assert r.broken_links[0].referencing_pages == ['https://example.com/ref1']
    assert r.redirects[0].referencing_pages == ['https://example.com/ref1']
    assert r.broken_anchors[0].referencing_pages == ['https://example.com/ref1']
    assert r.non200_responses[0].referencing_pages == ['https://example.com/ref1']
    assert r.ssl_warnings[0].affected_urls[0][1] == ['https://example.com/ref1']


# ---------------------------------------------------------------------------
# merge_referrer: SSL warning path & empty-referrer guard
# ---------------------------------------------------------------------------


def test_merge_referrer_empty_referrer_is_no_op() -> None:
    r = CrawlResults()
    r.add_broken_link(
        url='https://example.com/gone',
        status_code=404,
        error='404',
        referrer='https://example.com/ref1',
    )
    r.merge_referrer('https://example.com/gone', '')
    assert r.broken_links[0].referencing_pages == ['https://example.com/ref1']


def test_merge_referrer_ssl_warning_path() -> None:
    r = CrawlResults()
    r.add_ssl_warning(
        url='https://bad.example.com/x', domain='bad.example.com', error='SSL fail', referrer='ref1'
    )
    r.merge_referrer('https://bad.example.com/x', 'ref2')
    assert sorted(r.ssl_warnings[0].affected_urls[0][1]) == ['ref1', 'ref2']


def test_merge_referrer_ssl_warning_deduplicates() -> None:
    r = CrawlResults()
    r.add_ssl_warning(
        url='https://bad.example.com/x', domain='bad.example.com', error='SSL fail', referrer='ref1'
    )
    r.merge_referrer('https://bad.example.com/x', 'ref1')
    assert r.ssl_warnings[0].affected_urls[0][1] == ['ref1']


def test_merge_referrer_pending_then_ssl_warning_drains() -> None:
    """Pending referrer queued before ssl_warning entry must be drained into it."""
    r = CrawlResults()
    r.merge_referrer('https://bad.example.com/x', 'pending-ref')
    r.add_ssl_warning(
        url='https://bad.example.com/x',
        domain='bad.example.com',
        error='SSL fail',
        referrer='direct-ref',
    )
    refs = r.ssl_warnings[0].affected_urls[0][1]
    assert 'pending-ref' in refs
    assert 'direct-ref' in refs


# ---------------------------------------------------------------------------
# Pending-referrer drain paths for add_* methods
# ---------------------------------------------------------------------------


def test_pending_referrer_drained_into_redirect() -> None:
    r = CrawlResults()
    r.merge_referrer('https://example.com/old', 'pending-ref')
    r.add_redirect(
        original_url='https://example.com/old',
        final_url='https://example.com/new',
        status_code=301,
        referrer='direct-ref',
    )
    entry = r.redirects[0]
    assert 'pending-ref' in entry.referencing_pages
    assert 'direct-ref' in entry.referencing_pages


def test_pending_referrer_drained_into_non200() -> None:
    r = CrawlResults()
    r.merge_referrer('https://example.com/gone', 'pending-ref')
    r.add_non200('https://example.com/gone', 404, 'direct-ref')
    entry = r.non200_responses[0]
    assert 'pending-ref' in entry.referencing_pages


def test_pending_referrer_drained_into_misplaced_asset() -> None:
    r = CrawlResults()
    r.merge_referrer('https://example.com/img.png', 'pending-ref')
    r.add_misplaced_asset('https://example.com/img.png', 'Image', 'direct-ref')
    entry = r.misplaced_assets[0]
    assert 'pending-ref' in entry.referencing_pages


def test_pending_referrer_drained_into_non_http_link() -> None:
    r = CrawlResults()
    r.merge_referrer('mailto:info@example.com', 'pending-ref')
    r.add_non_http_link('mailto:info@example.com', 'mailto', 'direct-ref')
    entry = r.non_http_links[0]
    assert 'pending-ref' in entry.referencing_pages


def test_pending_referrer_drained_into_ignore_match() -> None:
    r = CrawlResults()
    r.merge_referrer('https://example.com/ignored', 'pending-ref')
    r.add_ignore_match('https://example.com/ignored', 'direct-ref')
    entry = r.ignore_matches[0]
    assert 'pending-ref' in entry.referencing_pages


def test_pending_referrer_drained_into_no_crawl_match() -> None:
    r = CrawlResults()
    r.merge_referrer('https://example.com/archive', 'pending-ref')
    r.add_no_crawl_match('https://example.com/archive', 'direct-ref')
    entry = r.no_crawl_matches[0]
    assert 'pending-ref' in entry.referencing_pages


def test_record_request_no_domain_does_not_crash() -> None:
    """record_request with a URL that has no domain must not raise."""
    r = CrawlResults()
    r.record_request('', bytes_downloaded=0)
    assert r.statistics.total_requests == 1


# ---------------------------------------------------------------------------
# add_ssl_warning: second referrer to same URL (existing entry branch)
# ---------------------------------------------------------------------------


def test_add_ssl_warning_second_referrer_to_existing_url() -> None:
    r = CrawlResults()
    r.add_ssl_warning(
        url='https://bad.example.com/x', domain='bad.example.com', error='err', referrer='ref1'
    )
    r.add_ssl_warning(
        url='https://bad.example.com/x', domain='bad.example.com', error='err', referrer='ref2'
    )
    refs = r.ssl_warnings[0].affected_urls[0][1]
    assert sorted(refs) == ['ref1', 'ref2']
