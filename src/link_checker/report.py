"""Plain-text report generator for all 12 report sections."""

from __future__ import annotations

import http
import time
from collections import defaultdict

from link_checker.config import CrawlConfig
from link_checker.results import CrawlResults


def generate_report(results: CrawlResults, config: CrawlConfig) -> str:
    """Generate the full plain-text report for a completed crawl.

    Produces all 12 sections as defined in spec §10.

    Args:
        results: Completed crawl results.
        config: Crawl configuration used.

    Returns:
        The full report as a multi-line string.
    """
    sections = [
        _section_config_summary(config),
        _section_statistics(results),
        _section_broken_links(results, config),
        _section_broken_anchors(results, config),
        _section_non200_responses(results, config),
        _section_redirects(results, config),
        _section_misplaced_assets(results, config),
        _section_ignore_matches(results, config),
        _section_non_http_links(results, config),
        _section_ssl_warnings(results, config),
        _section_unvalidated_anchors(results, config),
    ]
    return '\n\n'.join(sections) + '\n'


# ---------------------------------------------------------------------------
# §10.1 Configuration Summary
# ---------------------------------------------------------------------------


def _section_config_summary(config: CrawlConfig) -> str:
    lines = ['=== Configuration Summary ===']
    lines.append(f'Root URL:        {config.root_url}')
    lines.append(f'Timeout:         {config.timeout}s')
    lines.append(f'Retries:         {config.retries}')
    lines.append(f'Max threads:     {config.max_threads}')
    max_depth_str = str(config.max_depth) if config.max_depth is not None else 'unlimited'
    lines.append(f'Max depth:       {max_depth_str}')
    max_req_str = str(config.max_requests) if config.max_requests is not None else 'unlimited'
    lines.append(f'Max requests:    {max_req_str}')
    lines.append(f'Max ref. pages:  {config.max_referencing_pages}')
    if config.output:
        lines.append(f'Output file:     {config.output}')

    if config.asset_urls:
        lines.append('')
        lines.append('Asset URL prefixes:')
        for url in config.asset_urls:
            lines.append(f'  - {url}')

    if config.no_crawl_urls:
        lines.append('')
        lines.append('No-crawl URL prefixes:')
        for url in config.no_crawl_urls:
            lines.append(f'  - {url}')

    if config.ignore_urls:
        lines.append('')
        lines.append('Ignore URL prefixes:')
        for url in config.ignore_urls:
            lines.append(f'  - {url}')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# §10.2 Statistics Summary
# ---------------------------------------------------------------------------


def _section_statistics(results: CrawlResults) -> str:
    stats = results.statistics
    elapsed = time.time() - stats.start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    rps = stats.total_requests / elapsed if elapsed > 0 else 0.0
    mb = stats.bytes_downloaded / (1024 * 1024)

    lines = ['=== Statistics Summary ===']
    lines.append(f'Elapsed time:            {minutes}m {seconds}s')
    lines.append(f'Total HTTP requests:     {stats.total_requests:,}')
    lines.append(f'Requests per second:     {rps:.1f}')
    lines.append(f'Total bytes downloaded:  {mb:.1f} MB')
    lines.append('')
    lines.append(f'Internal pages crawled:  {stats.pages_crawled}')
    lines.append(f'Internal pages checked:  {stats.pages_checked}')
    lines.append(f'External links checked:  {stats.external_checked}')
    lines.append('')

    broken_count = len(results.broken_links)
    anchor_count = len(results.broken_anchors)
    unval_count = len(results.unvalidated_anchors)
    redirect_count = len(results.redirects)
    misplaced_count = len(results.misplaced_assets)
    ssl_count = len(results.ssl_warnings)
    non_http_count = len(results.non_http_links)

    lines.append(f'Broken links:            {broken_count}')
    lines.append(f'Broken anchors:          {anchor_count}')
    lines.append(f'Unvalidated anchors:     {unval_count}')
    lines.append(f'Redirects encountered:   {redirect_count}')
    lines.append(f'Misplaced assets:        {misplaced_count}')
    lines.append(f'SSL warnings:            {ssl_count} domain{"s" if ssl_count != 1 else ""}')
    lines.append('')

    if non_http_count:
        lines.append(f'Non-HTTP scheme links:   {non_http_count}')
        scheme_counts: dict[str, int] = defaultdict(int)
        for lk in results.non_http_links:
            scheme_counts[lk.scheme] += 1
        for scheme, count in sorted(scheme_counts.items(), key=lambda x: -x[1]):
            lines.append(f'  {scheme}:  {count}')
        lines.append('')

    if stats.per_domain_requests:
        lines.append('Per-domain request breakdown:')
        sorted_domains = sorted(stats.per_domain_requests.items(), key=lambda x: -x[1])
        for domain, count in sorted_domains:
            lines.append(f'  {domain}:  {count:,}')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# §10.3 Broken Links
# ---------------------------------------------------------------------------


def _section_broken_links(results: CrawlResults, config: CrawlConfig) -> str:
    items = results.broken_links
    lines = [f'=== Broken Links ({len(items)}) ===']
    if not items:
        return '\n'.join(lines)

    by_page: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for bl in items:
        for page in bl.referencing_pages:
            by_page[page].append((bl.url, bl.error))

    for page in sorted(by_page):
        lines.append('')
        lines.append(f'Page: {page}')
        for url, error in sorted(by_page[page]):
            lines.append(f'  - {url}  →  {error}')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# §10.4 Broken Anchors
# ---------------------------------------------------------------------------


def _section_broken_anchors(results: CrawlResults, config: CrawlConfig) -> str:
    items = results.broken_anchors
    lines = [f'=== Broken Anchors ({len(items)}) ===']
    for ba in items:
        lines.append('')
        lines.append(f'Target: {ba.target_url}')
        lines.append('  Referenced by:')
        for page in _truncated_pages(ba.referencing_pages, config.max_referencing_pages):
            lines.append(f'    - {page}')
        extra = len(ba.referencing_pages) - config.max_referencing_pages
        if extra > 0:
            lines.append(f'    ... and {extra} more referencing pages')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# §10.5 Non-200 Responses
# ---------------------------------------------------------------------------


def _section_non200_responses(results: CrawlResults, config: CrawlConfig) -> str:
    items = results.non200_responses
    lines = [f'=== Non-200 Responses ({len(items)}) ===']
    by_status: dict[int, list[tuple[str, list[str]]]] = defaultdict(list)
    for r in items:
        by_status[r.status_code].append((r.url, r.referencing_pages))

    for status in sorted(by_status):
        reason = _http_reason(status)
        lines.append('')
        lines.append(f'{status} {reason}:')
        for url, refs in sorted(by_status[status], key=lambda x: x[0]):
            lines.append(f'  - {url}')
            lines.append('    Referenced by:')
            for page in _truncated_pages(refs, config.max_referencing_pages):
                lines.append(f'      - {page}')
            extra = len(refs) - config.max_referencing_pages
            if extra > 0:
                lines.append(f'      ... and {extra} more referencing pages')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# §10.6 Redirects
# ---------------------------------------------------------------------------


def _section_redirects(results: CrawlResults, config: CrawlConfig) -> str:
    items = results.redirects
    lines = [f'=== Redirects ({len(items)}) ===']
    for r in items:
        lines.append('')
        lines.append(f'{r.original_url}  →  {r.final_url} ({r.status_code})')
        lines.append('  Referenced by:')
        for page in _truncated_pages(r.referencing_pages, config.max_referencing_pages):
            lines.append(f'    - {page}')
        extra = len(r.referencing_pages) - config.max_referencing_pages
        if extra > 0:
            lines.append(f'    ... and {extra} more referencing pages')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# §10.7 Misplaced Assets
# ---------------------------------------------------------------------------

_ASSET_TYPE_ORDER = ['Image', 'Document', 'Data', 'Infrastructure', 'Other']


def _section_misplaced_assets(results: CrawlResults, config: CrawlConfig) -> str:
    items = results.misplaced_assets
    lines = [f'=== Misplaced Assets ({len(items)}) ===']

    by_type: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for a in items:
        by_type[a.asset_type].append((a.url, a.referencing_pages))

    for asset_type in _ASSET_TYPE_ORDER:
        lines.append('')
        lines.append(f'{asset_type}:')
        entries = by_type.get(asset_type, [])
        if not entries:
            lines.append('  (none)')
            continue
        for url, refs in sorted(entries, key=lambda x: x[0].rsplit('/', 1)[-1]):
            filename = url.rsplit('/', 1)[-1]
            lines.append(f'  {filename} ({url})')
            lines.append('    Referenced by:')
            for page in _truncated_pages(refs, config.max_referencing_pages):
                lines.append(f'      - {page}')
            extra = len(refs) - config.max_referencing_pages
            if extra > 0:
                lines.append(f'      ... and {extra} more referencing pages')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# §10.8 No-Crawl URL Matches
# ---------------------------------------------------------------------------


def _section_no_crawl_matches(results: CrawlResults, config: CrawlConfig) -> str:
    items = results.no_crawl_matches
    lines = [f'=== No-Crawl URL Matches ({len(items)}) ===']
    for m in items:
        lines.append('')
        lines.append(m.url)
        lines.append('  Referenced by:')
        for page in _truncated_pages(m.referencing_pages, config.max_referencing_pages):
            lines.append(f'    - {page}')
        extra = len(m.referencing_pages) - config.max_referencing_pages
        if extra > 0:
            lines.append(f'    ... and {extra} more referencing pages')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# §10.9 Ignore URL Matches
# ---------------------------------------------------------------------------


def _section_ignore_matches(results: CrawlResults, config: CrawlConfig) -> str:
    items = results.ignore_matches
    lines = [f'=== Ignore URL Matches ({len(items)}) ===']
    for m in items:
        lines.append('')
        lines.append(m.url)
        lines.append('  Referenced by:')
        for page in _truncated_pages(m.referencing_pages, config.max_referencing_pages):
            lines.append(f'    - {page}')
        extra = len(m.referencing_pages) - config.max_referencing_pages
        if extra > 0:
            lines.append(f'    ... and {extra} more referencing pages')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# §10.10 Non-HTTP Scheme Links
# ---------------------------------------------------------------------------


def _section_non_http_links(results: CrawlResults, config: CrawlConfig) -> str:
    items = results.non_http_links
    lines = [f'=== Non-HTTP Scheme Links ({len(items)}) ===']
    for lk in items:
        lines.append('')
        lines.append(lk.url)
        lines.append('  Referenced by:')
        for page in _truncated_pages(lk.referencing_pages, config.max_referencing_pages):
            lines.append(f'    - {page}')
        extra = len(lk.referencing_pages) - config.max_referencing_pages
        if extra > 0:
            lines.append(f'    ... and {extra} more referencing pages')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# §10.11 SSL Warnings
# ---------------------------------------------------------------------------


def _section_ssl_warnings(results: CrawlResults, config: CrawlConfig) -> str:
    items = results.ssl_warnings
    lines = [f'=== SSL Warnings ({len(items)} domain{"s" if len(items) != 1 else ""}) ===']
    for sw in items:
        lines.append('')
        lines.append(f'{sw.domain} — {sw.error}')
        lines.append('  Affected URLs:')
        for url, refs in sw.affected_urls:
            lines.append(f'    - {url}')
            lines.append('      Referenced by:')
            for page in _truncated_pages(refs, config.max_referencing_pages):
                lines.append(f'        - {page}')
            extra = len(refs) - config.max_referencing_pages
            if extra > 0:
                lines.append(f'        ... and {extra} more referencing pages')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# §10.12 Unvalidated Anchors
# ---------------------------------------------------------------------------


def _section_unvalidated_anchors(results: CrawlResults, config: CrawlConfig) -> str:
    items = results.unvalidated_anchors
    lines = [f'=== Unvalidated Anchors ({len(items)}) ===']
    for ua in items:
        lines.append('')
        lines.append(f'{ua.target_url} ({ua.reason})')
        lines.append('  Referenced by:')
        for page in _truncated_pages(ua.referencing_pages, config.max_referencing_pages):
            lines.append(f'    - {page}')
        extra = len(ua.referencing_pages) - config.max_referencing_pages
        if extra > 0:
            lines.append(f'    ... and {extra} more referencing pages')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncated_pages(pages: list[str], max_pages: int) -> list[str]:
    """Return at most *max_pages* items from *pages*.

    Args:
        pages: List of page URLs.
        max_pages: Maximum number to return.

    Returns:
        Truncated list.
    """
    return pages[:max_pages]


def _http_reason(status_code: int) -> str:
    """Return the HTTP reason phrase for *status_code*, or an empty string.

    Args:
        status_code: HTTP status code integer.

    Returns:
        Reason phrase string (e.g. ``'Not Found'``).
    """
    try:
        return http.HTTPStatus(status_code).phrase
    except ValueError:
        return ''
