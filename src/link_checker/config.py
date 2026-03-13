"""Configuration dataclass and YAML loading for rms-link-checker."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_VALID_LOG_LEVELS: frozenset[str] = frozenset({'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'})

_KNOWN_YAML_KEYS: frozenset[str] = frozenset(
    {
        'root_url',
        'timeout',
        'retries',
        'max_requests',
        'max_depth',
        'max_threads',
        'max_referencing_pages',
        'log_level',
        'output',
        'log_file',
        'asset_urls',
        'no_crawl_urls',
        'ignore_urls',
    }
)


@dataclass(frozen=True)
class CrawlConfig:
    """Immutable crawl configuration.

    Attributes:
        root_url: The root URL to begin crawling from.
        timeout: Timeout in seconds for each HTTP request.
        retries: Number of retry attempts for transient failures.
        max_requests: Maximum total HTTP requests (None = unlimited).
        max_depth: Maximum directory depth (None = unlimited).
        max_threads: Maximum concurrent threads.
        max_referencing_pages: Max referencing pages per URL in report.
        log_level: Minimum log level string.
        output: File path for report (None = stdout).
        log_file: File path for log messages (None = stderr).
        asset_urls: Expected URL prefixes for asset files.
        no_crawl_urls: URL prefixes to check but not crawl.
        ignore_urls: URL prefixes to skip entirely.
    """

    root_url: str
    timeout: int = 10
    retries: int = 3
    max_requests: int | None = None
    max_depth: int | None = None
    max_threads: int = 10
    max_referencing_pages: int = 10
    log_level: str = 'INFO'
    output: str | None = None
    log_file: str | None = None
    asset_urls: tuple[str, ...] = field(default_factory=tuple)
    no_crawl_urls: tuple[str, ...] = field(default_factory=tuple)
    ignore_urls: tuple[str, ...] = field(default_factory=tuple)


def load_config(
    cli_namespace: argparse.Namespace,
    *,
    config_path: str | None = None,
) -> CrawlConfig:
    """Build a :class:`CrawlConfig` by merging a YAML file and CLI overrides.

    Precedence (highest to lowest): CLI arguments > YAML file > defaults.

    Args:
        cli_namespace: Parsed argparse namespace. Fields set to ``None``
            are treated as "not specified" and do not override YAML or defaults.
        config_path: Path to a YAML configuration file. If ``None``, no file
            is loaded. May also be read from ``cli_namespace.config_file``.

    Returns:
        A fully populated :class:`CrawlConfig` instance.

    Raises:
        ValueError: If required fields are missing, the config file cannot be
            parsed, or any value fails validation.
    """
    effective_path = config_path or getattr(cli_namespace, 'config_file', None)

    yaml_data: dict[str, Any] = {}
    if effective_path is not None:
        yaml_data = _load_yaml_file(effective_path)

    def _resolve(key: str, default: Any = None) -> Any:
        cli_val = getattr(cli_namespace, key, None)
        if cli_val is not None:
            return cli_val
        return yaml_data.get(key, default)

    root_url: str | None = _resolve('root_url')
    if not root_url:
        raise ValueError(
            'root_url is required: provide it as a positional argument or in the config file.'
        )

    timeout = _coerce_int(_resolve('timeout', 10), 'timeout')
    retries = _coerce_int(_resolve('retries', 3), 'retries')
    max_requests_raw = _resolve('max_requests')
    max_requests = (
        _coerce_int(max_requests_raw, 'max_requests') if max_requests_raw is not None else None
    )
    max_depth_raw = _resolve('max_depth')
    max_depth = _coerce_int(max_depth_raw, 'max_depth') if max_depth_raw is not None else None
    max_threads = _coerce_int(_resolve('max_threads', 10), 'max_threads')
    max_referencing_pages = _coerce_int(
        _resolve('max_referencing_pages', 10), 'max_referencing_pages'
    )
    log_level = str(_resolve('log_level', 'INFO')).upper()
    output = _resolve('output')
    log_file = _resolve('log_file')

    asset_urls = tuple(yaml_data.get('asset_urls', []))
    no_crawl_urls = tuple(yaml_data.get('no_crawl_urls', []))
    ignore_urls = tuple(yaml_data.get('ignore_urls', []))

    _validate(timeout=timeout, retries=retries, log_level=log_level)

    return CrawlConfig(
        root_url=root_url,
        timeout=timeout,
        retries=retries,
        max_requests=max_requests,
        max_depth=max_depth,
        max_threads=max_threads,
        max_referencing_pages=max_referencing_pages,
        log_level=log_level,
        output=output,
        log_file=log_file,
        asset_urls=asset_urls,
        no_crawl_urls=no_crawl_urls,
        ignore_urls=ignore_urls,
    )


def _load_yaml_file(path: str) -> dict[str, Any]:
    """Load and parse a YAML config file.

    Args:
        path: Filesystem path to the YAML file.

    Returns:
        Parsed YAML contents as a dict (empty dict for empty files).

    Raises:
        ValueError: If the file does not exist or cannot be parsed.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f'Config file not found: {path!r}')

    try:
        content = p.read_text(encoding='utf-8')
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ValueError(f'Invalid YAML in config file {path!r}: {exc}') from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f'Config file {path!r} must contain a YAML mapping, got {type(data)}')

    unknown = sorted(set(data.keys()) - _KNOWN_YAML_KEYS)
    if unknown:
        raise ValueError(
            f'Unknown key(s) in config file {path!r}: {", ".join(unknown)}. '
            f'Valid keys are: {", ".join(sorted(_KNOWN_YAML_KEYS))}'
        )

    return data


def _coerce_int(value: Any, field: str) -> int:
    """Coerce *value* to int, raising :exc:`ValueError` with a clear message on failure.

    Args:
        value: The raw value to coerce.
        field: The field name, used in the error message.

    Returns:
        Integer representation of *value*.

    Raises:
        ValueError: If *value* cannot be converted to an integer.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field} must be an integer, got {value!r}') from None


def _validate(*, timeout: int, retries: int, log_level: str) -> None:
    """Validate config values, raising ValueError on failure.

    Args:
        timeout: Request timeout in seconds (must be > 0).
        retries: Retry count (must be >= 0).
        log_level: Log level string (must be one of the standard levels).

    Raises:
        ValueError: If any value is invalid.
    """
    if timeout <= 0:
        raise ValueError(f'timeout must be > 0, got {timeout}')
    if retries < 0:
        raise ValueError(f'retries must be >= 0, got {retries}')
    if log_level not in _VALID_LOG_LEVELS:
        raise ValueError(f'log_level must be one of {sorted(_VALID_LOG_LEVELS)}, got {log_level!r}')
