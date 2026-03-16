"""Tests for http_client module."""

from __future__ import annotations

from unittest.mock import patch

import requests.exceptions
import responses as resp_lib

from link_checker.http_client import HttpClient, RequestResult


def _make_client(timeout: int = 10, retries: int = 3) -> HttpClient:
    return HttpClient(
        timeout=timeout,
        retries=retries,
        user_agent='rms-link-checker/test',
        sleep=lambda _: None,
    )


# ---------------------------------------------------------------------------
# Basic success cases
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_head_request_200() -> None:
    resp_lib.add(resp_lib.HEAD, 'https://example.com/page', status=200)
    client = _make_client()
    result = client.request('https://example.com/page', method='HEAD')
    assert result.status_code == 200
    assert result.error is None


@resp_lib.activate
def test_get_request_returns_body() -> None:
    resp_lib.add(resp_lib.GET, 'https://example.com/page', body='<html/>', status=200)
    client = _make_client()
    result = client.request('https://example.com/page', method='GET')
    assert result.status_code == 200
    assert result.body == '<html/>'


@resp_lib.activate
def test_head_405_falls_back_to_get() -> None:
    resp_lib.add(resp_lib.HEAD, 'https://example.com/page', status=405)
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=200)
    client = _make_client()
    result = client.request('https://example.com/page', method='HEAD')
    assert result.status_code == 200


@resp_lib.activate
def test_get_request_records_content_type() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/page',
        body='<html/>',
        status=200,
        headers={'Content-Type': 'text/html; charset=utf-8'},
    )
    client = _make_client()
    result = client.request('https://example.com/page', method='GET')
    assert result.content_type == 'text/html; charset=utf-8'


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_429_triggers_retry() -> None:
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=429)
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=429)
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=200)
    client = _make_client(timeout=1, retries=3)
    result = client.request('https://example.com/page', method='GET')
    assert result.status_code == 200


@resp_lib.activate
def test_503_triggers_retry() -> None:
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=503)
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=200)
    client = _make_client(timeout=1, retries=3)
    result = client.request('https://example.com/page', method='GET')
    assert result.status_code == 200


@resp_lib.activate
def test_404_not_retried() -> None:
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=404)
    call_count = 0

    def callback(request: object) -> tuple[int, dict[str, str], str]:
        nonlocal call_count
        call_count += 1
        return (404, {}, '')

    resp_lib.reset()
    resp_lib.add_callback(resp_lib.GET, 'https://example.com/page', callback)
    client = _make_client(timeout=1, retries=3)
    result = client.request('https://example.com/page', method='GET')
    assert result.status_code == 404
    assert call_count == 1


@resp_lib.activate
def test_retries_exhausted_records_error() -> None:
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=503)
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=503)
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=503)
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=503)
    client = _make_client(timeout=1, retries=3)
    result = client.request('https://example.com/page', method='GET')
    assert result.status_code == 503


@resp_lib.activate
def test_connection_error_triggers_retry() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/page',
        body=requests.exceptions.ConnectionError('timeout'),
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=200)
    client = _make_client(timeout=1, retries=3)
    result = client.request('https://example.com/page', method='GET')
    assert result.status_code == 200


@resp_lib.activate
def test_backoff_uses_timeout_value() -> None:
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=503)
    resp_lib.add(resp_lib.GET, 'https://example.com/page', status=200)
    sleep_calls: list[float] = []
    client = HttpClient(
        timeout=7,
        retries=3,
        user_agent='rms-link-checker/test',
        sleep=lambda s: sleep_calls.append(s),
    )
    client.request('https://example.com/page', method='GET')
    assert sleep_calls[0] == 7


# ---------------------------------------------------------------------------
# Redirects
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_redirect_chain_recorded() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/old',
        status=301,
        headers={'Location': 'https://example.com/mid'},
    )
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/mid',
        status=302,
        headers={'Location': 'https://example.com/new'},
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/new', status=200)
    client = _make_client()
    result = client.request('https://example.com/old', method='GET')
    assert result.status_code == 200
    assert result.final_url == 'https://example.com/new'
    assert len(result.redirect_chain) == 2
    assert result.redirect_chain[0].status_code == 301
    assert result.redirect_chain[1].status_code == 302


@resp_lib.activate
def test_max_redirects_exceeded() -> None:
    for i in range(12):
        resp_lib.add(
            resp_lib.GET,
            f'https://example.com/page{i}',
            status=301,
            headers={'Location': f'https://example.com/page{i + 1}'},
        )
    resp_lib.add(resp_lib.GET, 'https://example.com/page12', status=200)
    client = _make_client()
    result = client.request('https://example.com/page0', method='GET')
    assert result.error is not None
    assert 'redirect' in result.error.lower()


# ---------------------------------------------------------------------------
# SSL errors
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_ssl_error_warns_once_per_domain() -> None:
    import requests.exceptions

    resp_lib.add(
        resp_lib.GET,
        'https://bad-ssl.example.com/page1',
        body=requests.exceptions.SSLError('cert verify failed'),
    )
    resp_lib.add(
        resp_lib.GET,
        'https://bad-ssl.example.com/page2',
        body=requests.exceptions.SSLError('cert verify failed'),
    )
    client = _make_client(retries=0)
    result1 = client.request('https://bad-ssl.example.com/page1', method='GET')
    result2 = client.request('https://bad-ssl.example.com/page2', method='GET')
    assert result1.error is not None
    assert result2.error is not None
    assert client.ssl_warned_domains == {'bad-ssl.example.com'}


# ---------------------------------------------------------------------------
# User-Agent header
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_user_agent_set() -> None:
    captured_headers: list[dict[str, str]] = []

    def callback(request: object) -> tuple[int, dict[str, str], str]:
        import requests

        assert isinstance(request, requests.PreparedRequest)
        captured_headers.append(dict(request.headers))
        return (200, {}, '')

    resp_lib.add_callback(resp_lib.GET, 'https://example.com/page', callback)
    client = _make_client()
    client.request('https://example.com/page', method='GET')
    assert captured_headers[0]['User-Agent'] == 'rms-link-checker/test'


# ---------------------------------------------------------------------------
# No cookies
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_no_cookies_sent() -> None:
    captured: list[dict[str, str]] = []

    def callback(request: object) -> tuple[int, dict[str, str], str]:
        import requests

        assert isinstance(request, requests.PreparedRequest)
        captured.append(dict(request.headers))
        return (200, {}, '')

    resp_lib.add_callback(resp_lib.GET, 'https://example.com/page', callback)
    client = _make_client()
    client.request('https://example.com/page', method='GET')
    assert 'Cookie' not in captured[0]


# ---------------------------------------------------------------------------
# TLS verification option
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_verify_false_passed_to_request() -> None:
    def callback(request: object) -> tuple[int, dict[str, str], str]:
        return (200, {}, '')

    resp_lib.add_callback(resp_lib.GET, 'https://example.com/page', callback)
    client = HttpClient(
        timeout=10, retries=0, user_agent='test', verify=False
    )
    with patch.object(
        client._session,
        'request',
        wraps=client._session.request,
    ) as mock_req:
        client.request('https://example.com/page', method='GET')
    _args, kwargs = mock_req.call_args
    assert kwargs.get('verify') is False


# ---------------------------------------------------------------------------
# Broad RequestException handling
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_chunked_encoding_error_returns_error_result() -> None:
    """A RequestException subclass other than SSLError/ConnectionError/Timeout
    must be caught and returned as an error result (not propagated)."""
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/page',
        body=requests.exceptions.ChunkedEncodingError('broken chunk'),
    )
    client = _make_client(timeout=1, retries=0)
    result = client.request('https://example.com/page', method='GET')
    assert result.error is not None
    assert result.status_code == 0


# ---------------------------------------------------------------------------
# RequestResult structure
# ---------------------------------------------------------------------------


@resp_lib.activate
def test_request_result_fields() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com/page',
        status=200,
        body='hello',
        headers={'Content-Type': 'text/html'},
    )
    client = _make_client()
    result = client.request('https://example.com/page', method='GET')
    assert isinstance(result, RequestResult)
    assert result.final_url == 'https://example.com/page'
    assert result.status_code == 200
    assert result.body == 'hello'
    assert result.redirect_chain == []
    assert result.error is None
    assert result.bytes_downloaded > 0
