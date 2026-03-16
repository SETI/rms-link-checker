"""HTTP client with retry, redirect, SSL, and User-Agent support."""

from __future__ import annotations

import logging
import time as _time_module
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
import requests.exceptions

logger = logging.getLogger('link_checker')

_MAX_REDIRECTS = 10
_TRANSIENT_STATUSES: frozenset[int] = frozenset({429, 503})


@dataclass
class RedirectHop:
    """A single hop in an HTTP redirect chain.

    Attributes:
        url: The URL of this hop.
        status_code: The HTTP status code returned for this hop.
    """

    url: str
    status_code: int


@dataclass
class RequestResult:
    """Result of an HTTP request, including all redirect hops.

    Attributes:
        final_url: The final URL after following all redirects.
        status_code: The final HTTP status code.
        headers: Response headers from the final response.
        body: Response body text (only populated for GET requests).
        content_type: Value of the ``Content-Type`` header, if present.
        redirect_chain: List of redirect hops leading to the final URL.
        error: Human-readable error string if the request failed.
        bytes_downloaded: Approximate bytes received.
    """

    final_url: str
    status_code: int
    headers: dict[str, str]
    body: str | None
    content_type: str | None
    redirect_chain: list[RedirectHop] = field(default_factory=list)
    error: str | None = None
    bytes_downloaded: int = 0


class HttpClient:
    """HTTP client wrapping :mod:`requests` with retry, redirect, and SSL handling.

    Parameters:
        timeout: Timeout in seconds for each individual request attempt.
        retries: Maximum number of retry attempts for transient failures.
        user_agent: User-Agent header value to send with every request.
        verify: TLS certificate verification.  Pass ``False`` to disable
            (e.g. for internal environments with self-signed certificates),
            or a path to a CA bundle.  Defaults to ``True``.
        sleep: Callable used to pause between retry attempts.  Defaults to
            :func:`time.sleep`.  Pass a no-op (e.g. ``lambda _: None``) in
            tests to avoid real waits.
    """

    def __init__(
        self,
        *,
        timeout: int,
        retries: int,
        user_agent: str,
        verify: bool | str = True,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """Initialise the HTTP client.

        Parameters:
            timeout: Timeout in seconds per request attempt.
            retries: Max retry attempts for transient errors.
            user_agent: User-Agent string.
            verify: TLS verification flag or CA-bundle path.
            sleep: Optional callable for inter-retry pauses.  Defaults to
                :func:`time.sleep`.
        """
        self._timeout = timeout
        self._retries = retries
        self._user_agent = user_agent
        self._verify: bool | str = verify
        self._sleep: Callable[[float], None] = sleep if sleep is not None else _time_module.sleep
        self._session = self._make_session()
        self._ssl_warned_domains: set[str] = set()

    @property
    def ssl_warned_domains(self) -> set[str]:
        """Domains that have already triggered an SSL warning."""
        return set(self._ssl_warned_domains)

    def _make_session(self) -> requests.Session:
        """Create a new :class:`~requests.Session` with a cleared cookie jar and User-Agent set.

        Returns:
            Configured :class:`~requests.Session` instance.
        """
        session = requests.Session()
        session.cookies.clear()
        session.headers.update({'User-Agent': self._user_agent})
        return session

    def request(self, url: str, *, method: str = 'HEAD') -> RequestResult:
        """Issue an HTTP request, following redirects manually and retrying on transient errors.

        If *method* is ``'HEAD'`` and the server returns 405, automatically
        retries with ``'GET'``.

        Parameters:
            url: The URL to request.
            method: HTTP method string (``'HEAD'`` or ``'GET'``).

        Returns:
            A :class:`RequestResult` describing the outcome.
        """
        result = self._request_with_retry(url, method=method)

        if method == 'HEAD' and result.status_code == 405:
            result = self._request_with_retry(url, method='GET')

        return result

    def _request_with_retry(self, url: str, *, method: str) -> RequestResult:
        """Attempt a request up to ``retries + 1`` times on transient failures.

        Parameters:
            url: Target URL.
            method: HTTP method string.

        Returns:
            :class:`RequestResult` from the final attempt.
        """
        last_result: RequestResult | None = None
        attempts = self._retries + 1

        for attempt in range(attempts):
            try:
                result = self._do_request(url, method=method)
            except requests.exceptions.SSLError as exc:
                domain = urlparse(url).netloc
                if domain not in self._ssl_warned_domains:
                    self._ssl_warned_domains.add(domain)
                    logger.warning('SSL error for %s: %s', url, exc)
                return RequestResult(
                    final_url=url,
                    status_code=0,
                    headers={},
                    body=None,
                    content_type=None,
                    error=str(exc),
                )
            except requests.exceptions.RequestException as exc:
                last_result = RequestResult(
                    final_url=url,
                    status_code=0,
                    headers={},
                    body=None,
                    content_type=None,
                    error=str(exc),
                )
                if attempt < attempts - 1:
                    logger.warning('Transient error for %s (attempt %d): %s', url, attempt + 1, exc)
                    self._sleep(self._timeout)
                    continue
                return last_result

            if self._is_transient(result.status_code):
                last_result = result
                if attempt < attempts - 1:
                    logger.warning(
                        'Transient status %d for %s (attempt %d), retrying',
                        result.status_code,
                        url,
                        attempt + 1,
                    )
                    self._sleep(self._timeout)
                    continue
            return result

        return last_result or RequestResult(
            final_url=url,
            status_code=0,
            headers={},
            body=None,
            content_type=None,
            error='All retry attempts exhausted',
        )

    def _is_transient(self, status_code: int) -> bool:
        """Return True if *status_code* indicates a transient failure.

        Parameters:
            status_code: HTTP status code integer.

        Returns:
            True for codes in :data:`_TRANSIENT_STATUSES`.
        """
        return status_code in _TRANSIENT_STATUSES

    def _do_request(self, url: str, method: str) -> RequestResult:
        """Perform a single HTTP request, manually following redirects up to the limit.

        Parameters:
            url: Starting URL.
            method: HTTP method string.

        Returns:
            :class:`RequestResult` for the final response.

        Raises:
            :exc:`requests.exceptions.RequestException`: On network-level failures.
        """
        redirect_chain: list[RedirectHop] = []
        current_url = url

        for _ in range(_MAX_REDIRECTS + 1):
            with self._session.request(
                method,
                current_url,
                allow_redirects=False,
                timeout=self._timeout,
                stream=True,
                verify=self._verify,
            ) as response:
                if response.is_redirect:
                    location = response.headers.get('Location', '')
                    redirect_chain.append(
                        RedirectHop(url=current_url, status_code=response.status_code)
                    )
                    current_url = urljoin(current_url, location)
                    continue

                body: str | None = None
                bytes_downloaded = 0
                if method == 'GET':
                    body = response.text
                    bytes_downloaded = len(response.content)

                return RequestResult(
                    final_url=current_url,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    body=body,
                    content_type=response.headers.get('Content-Type'),
                    redirect_chain=redirect_chain,
                    bytes_downloaded=bytes_downloaded,
                )

        return RequestResult(
            final_url=current_url,
            status_code=0,
            headers={},
            body=None,
            content_type=None,
            redirect_chain=redirect_chain,
            error=f'Too many redirects (>{_MAX_REDIRECTS}) starting from {url}',
        )
