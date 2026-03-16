"""Tests for config module."""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path

import pytest

from link_checker.config import CrawlConfig, load_config


def _minimal_namespace(**kwargs: object) -> argparse.Namespace:
    """Build an argparse.Namespace with all config fields defaulting to None."""
    defaults: dict[str, object] = {
        'root_url': None,
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
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


def test_default_config_timeout() -> None:
    ns = _minimal_namespace(root_url='https://example.com')
    cfg = load_config(ns)
    assert cfg.timeout == 10


def test_default_config_retries() -> None:
    ns = _minimal_namespace(root_url='https://example.com')
    cfg = load_config(ns)
    assert cfg.retries == 3


def test_default_config_max_threads() -> None:
    ns = _minimal_namespace(root_url='https://example.com')
    cfg = load_config(ns)
    assert cfg.max_threads == 10


def test_default_config_max_requests_is_none() -> None:
    ns = _minimal_namespace(root_url='https://example.com')
    cfg = load_config(ns)
    assert cfg.max_requests is None


def test_default_config_max_depth_is_none() -> None:
    ns = _minimal_namespace(root_url='https://example.com')
    cfg = load_config(ns)
    assert cfg.max_depth is None


def test_default_config_log_level() -> None:
    ns = _minimal_namespace(root_url='https://example.com')
    cfg = load_config(ns)
    assert cfg.log_level == 'INFO'


def test_default_config_output_is_none() -> None:
    ns = _minimal_namespace(root_url='https://example.com')
    cfg = load_config(ns)
    assert cfg.output is None


def test_default_config_log_file_is_none() -> None:
    ns = _minimal_namespace(root_url='https://example.com')
    cfg = load_config(ns)
    assert cfg.log_file is None


def test_default_config_max_referencing_pages() -> None:
    ns = _minimal_namespace(root_url='https://example.com')
    cfg = load_config(ns)
    assert cfg.max_referencing_pages == 10


def test_default_config_url_lists_empty() -> None:
    ns = _minimal_namespace(root_url='https://example.com')
    cfg = load_config(ns)
    assert cfg.asset_urls == ()
    assert cfg.no_crawl_urls == ()
    assert cfg.ignore_urls == ()


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


def test_load_yaml_all_fields(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'config.yaml'
    yaml_file.write_text(
        'root_url: "https://example.com/docs"\n'
        'timeout: 15\n'
        'retries: 5\n'
        'max_requests: 1000\n'
        'max_depth: 8\n'
        'max_threads: 20\n'
        'max_referencing_pages: 20\n'
        'log_level: "DEBUG"\n'
        'output: "report.txt"\n'
        'log_file: "crawl.log"\n'
    )
    ns = _minimal_namespace()
    cfg = load_config(ns, config_path=str(yaml_file))
    assert cfg.root_url == 'https://example.com/docs'
    assert cfg.timeout == 15
    assert cfg.retries == 5
    assert cfg.max_requests == 1000
    assert cfg.max_depth == 8
    assert cfg.max_threads == 20
    assert cfg.max_referencing_pages == 20
    assert cfg.log_level == 'DEBUG'
    assert cfg.output == 'report.txt'
    assert cfg.log_file == 'crawl.log'


def test_load_yaml_empty_file_uses_defaults(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'config.yaml'
    yaml_file.write_text('')
    ns = _minimal_namespace(root_url='https://example.com')
    cfg = load_config(ns, config_path=str(yaml_file))
    assert cfg.timeout == 10
    assert cfg.retries == 3


def test_load_yaml_partial_uses_defaults_for_missing(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'config.yaml'
    yaml_file.write_text('root_url: "https://example.com"\ntimeout: 30\n')
    ns = _minimal_namespace()
    cfg = load_config(ns, config_path=str(yaml_file))
    assert cfg.timeout == 30
    assert cfg.retries == 3


def test_load_yaml_url_lists_parsed(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'config.yaml'
    yaml_file.write_text(
        'root_url: "https://example.com"\n'
        'asset_urls:\n'
        '  - "https://example.com/static/images"\n'
        '  - "https://example.com/static/docs"\n'
        'no_crawl_urls:\n'
        '  - "https://example.com/archive"\n'
        'ignore_urls:\n'
        '  - "https://example.com/legacy"\n'
    )
    ns = _minimal_namespace()
    cfg = load_config(ns, config_path=str(yaml_file))
    assert cfg.asset_urls == (
        'https://example.com/static/images',
        'https://example.com/static/docs',
    )
    assert cfg.no_crawl_urls == ('https://example.com/archive',)
    assert cfg.ignore_urls == ('https://example.com/legacy',)


def test_load_yaml_url_lists_default_empty(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'config.yaml'
    yaml_file.write_text('root_url: "https://example.com"\n')
    ns = _minimal_namespace()
    cfg = load_config(ns, config_path=str(yaml_file))
    assert cfg.asset_urls == ()
    assert cfg.no_crawl_urls == ()
    assert cfg.ignore_urls == ()


# ---------------------------------------------------------------------------
# CLI overrides YAML
# ---------------------------------------------------------------------------


def test_cli_overrides_yaml_timeout(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'config.yaml'
    yaml_file.write_text('root_url: "https://example.com"\ntimeout: 15\n')
    ns = _minimal_namespace(timeout=99)
    cfg = load_config(ns, config_path=str(yaml_file))
    assert cfg.timeout == 99


def test_cli_overrides_yaml_root_url(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'config.yaml'
    yaml_file.write_text('root_url: "https://yaml.example.com"\n')
    ns = _minimal_namespace(root_url='https://cli.example.com')
    cfg = load_config(ns, config_path=str(yaml_file))
    assert cfg.root_url == 'https://cli.example.com'


def test_cli_overrides_yaml_log_level(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'config.yaml'
    yaml_file.write_text('root_url: "https://example.com"\nlog_level: "DEBUG"\n')
    ns = _minimal_namespace(log_level='WARNING')
    cfg = load_config(ns, config_path=str(yaml_file))
    assert cfg.log_level == 'WARNING'


# ---------------------------------------------------------------------------
# root_url requirements
# ---------------------------------------------------------------------------


def test_root_url_from_yaml(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'config.yaml'
    yaml_file.write_text('root_url: "https://example.com"\n')
    ns = _minimal_namespace()
    cfg = load_config(ns, config_path=str(yaml_file))
    assert cfg.root_url == 'https://example.com'


def test_root_url_from_cli() -> None:
    ns = _minimal_namespace(root_url='https://example.com')
    cfg = load_config(ns)
    assert cfg.root_url == 'https://example.com'


def test_root_url_missing_raises() -> None:
    ns = _minimal_namespace()
    with pytest.raises(ValueError, match='root_url'):
        load_config(ns)


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'config.yaml'
    yaml_file.write_text('key: [unclosed')
    ns = _minimal_namespace(root_url='https://example.com')
    with pytest.raises(ValueError, match=r'[Ii]nvalid|[Pp]arse|YAML|yaml'):
        load_config(ns, config_path=str(yaml_file))


def test_missing_config_file_raises() -> None:
    ns = _minimal_namespace(root_url='https://example.com')
    with pytest.raises(ValueError, match=r'[Nn]ot found|[Cc]onfig|not found|does not exist'):
        load_config(ns, config_path='/nonexistent/path/config.yaml')


def test_invalid_timeout_raises() -> None:
    ns = _minimal_namespace(root_url='https://example.com', timeout=0)
    with pytest.raises(ValueError, match='timeout'):
        load_config(ns)


def test_invalid_retries_negative_raises() -> None:
    ns = _minimal_namespace(root_url='https://example.com', retries=-1)
    with pytest.raises(ValueError, match='retries'):
        load_config(ns)


def test_non_integer_timeout_raises(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'cfg.yaml'
    yaml_file.write_text('root_url: "https://example.com"\ntimeout: "fast"\n')
    ns = _minimal_namespace()
    with pytest.raises(ValueError, match=r'timeout must be an integer'):
        load_config(ns, config_path=str(yaml_file))


def test_non_integer_max_requests_raises(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'cfg.yaml'
    yaml_file.write_text('root_url: "https://example.com"\nmax_requests: "lots"\n')
    ns = _minimal_namespace()
    with pytest.raises(ValueError, match=r'max_requests must be an integer'):
        load_config(ns, config_path=str(yaml_file))


def test_invalid_log_level_raises() -> None:
    ns = _minimal_namespace(root_url='https://example.com', log_level='VERBOSE')
    with pytest.raises(ValueError, match=r'log_level|log level'):
        load_config(ns)


def test_unknown_yaml_key_raises(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'cfg.yaml'
    yaml_file.write_text(
        'root_url: "https://example.com"\nnon_crawl_urls:\n  - https://example.com/skip\n'
    )
    ns = _minimal_namespace()
    with pytest.raises(ValueError, match=r'Unknown key.*non_crawl_urls'):
        load_config(ns, config_path=str(yaml_file))


def test_multiple_unknown_yaml_keys_raises(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'cfg.yaml'
    yaml_file.write_text(
        'root_url: "https://example.com"\nnon_crawl_urls: []\nextra_setting: true\n'
    )
    ns = _minimal_namespace()
    with pytest.raises(ValueError, match=r'Unknown key.*extra_setting|non_crawl_urls'):
        load_config(ns, config_path=str(yaml_file))


@pytest.mark.parametrize('field', ['asset_urls', 'no_crawl_urls', 'ignore_urls'])
def test_url_list_scalar_raises(tmp_path: Path, field: str) -> None:
    yaml_file = tmp_path / 'cfg.yaml'
    yaml_file.write_text(f'root_url: "https://example.com"\n{field}: "not-a-list"\n')
    ns = _minimal_namespace()
    with pytest.raises(ValueError, match=rf'{field} must be a list'):
        load_config(ns, config_path=str(yaml_file))


@pytest.mark.parametrize('field', ['asset_urls', 'no_crawl_urls', 'ignore_urls'])
def test_url_list_null_treated_as_empty(tmp_path: Path, field: str) -> None:
    yaml_file = tmp_path / 'cfg.yaml'
    yaml_file.write_text(f'root_url: "https://example.com"\n{field}: ~\n')
    ns = _minimal_namespace()
    cfg = load_config(ns, config_path=str(yaml_file))
    assert getattr(cfg, field) == ()


@pytest.mark.parametrize('value', ['debug', 'Debug', 'WARNING', 'warning', 'Error', 'critical', 'INFO'])
def test_log_level_case_insensitive(value: str) -> None:
    ns = _minimal_namespace(root_url='https://example.com', log_level=value)
    cfg = load_config(ns)
    assert cfg.log_level == value.upper()


# ---------------------------------------------------------------------------
# Range validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('field', 'value', 'match'),
    [
        ('max_requests', 0, r'max_requests must be > 0'),
        ('max_requests', -1, r'max_requests must be > 0'),
        ('max_depth', -1, r'max_depth must be >= 0'),
        ('max_threads', 0, r'max_threads must be >= 1'),
        ('max_threads', -5, r'max_threads must be >= 1'),
        ('max_referencing_pages', 0, r'max_referencing_pages must be >= 1'),
    ],
)
def test_invalid_range_raises(field: str, value: int, match: str) -> None:
    ns = _minimal_namespace(root_url='https://example.com', **{field: value})
    with pytest.raises(ValueError, match=match):
        load_config(ns)


def test_max_depth_zero_is_valid() -> None:
    ns = _minimal_namespace(root_url='https://example.com', max_depth=0)
    cfg = load_config(ns)
    assert cfg.max_depth == 0


# ---------------------------------------------------------------------------
# CrawlConfig is frozen
# ---------------------------------------------------------------------------


def test_crawl_config_is_frozen() -> None:
    cfg = CrawlConfig(root_url='https://example.com')
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.timeout = 99  # type: ignore[misc]
