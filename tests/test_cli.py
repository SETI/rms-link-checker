"""Tests for cli module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import responses as resp_lib

from link_checker import __version__
from link_checker.cli import _build_parser, main


def test_parse_args_root_url_positional() -> None:
    parser = _build_parser()
    ns = parser.parse_args(['https://example.com'])
    assert ns.root_url == 'https://example.com'


def test_parse_args_all_options() -> None:
    parser = _build_parser()
    ns = parser.parse_args(
        [
            'https://example.com',
            '-o',
            'report.txt',
            '--log-file',
            'crawl.log',
            '--log-level',
            'DEBUG',
            '--timeout',
            '30',
            '--retries',
            '5',
            '--max-requests',
            '1000',
            '--max-depth',
            '8',
            '--max-threads',
            '20',
            '--max-referencing-pages',
            '20',
            '--config-file',
            'config.yaml',
        ]
    )
    assert ns.output == 'report.txt'
    assert ns.log_file == 'crawl.log'
    assert ns.log_level == 'DEBUG'
    assert ns.timeout == 30
    assert ns.retries == 5
    assert ns.max_requests == 1000
    assert ns.max_depth == 8
    assert ns.max_threads == 20
    assert ns.max_referencing_pages == 20
    assert ns.config_file == 'config.yaml'


def test_parse_args_defaults() -> None:
    parser = _build_parser()
    ns = parser.parse_args(['https://example.com'])
    assert ns.output is None
    assert ns.log_file is None
    assert ns.log_level is None
    assert ns.timeout is None
    assert ns.retries is None
    assert ns.max_requests is None
    assert ns.max_depth is None
    assert ns.max_threads is None
    assert ns.max_referencing_pages is None
    assert ns.config_file is None


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(['--version'])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out or __version__ in captured.err


def test_config_file_loaded(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'config.yaml'
    yaml_file.write_text('root_url: "https://example.com"\ntimeout: 42\n')
    with resp_lib.RequestsMock() as rsps:
        rsps.add(rsps.GET, 'https://example.com', body='<html/>', status=200)
        with patch('sys.argv', ['link_check', '--config-file', str(yaml_file)]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0


def test_cli_overrides_config(tmp_path: Path) -> None:
    yaml_file = tmp_path / 'config.yaml'
    yaml_file.write_text('root_url: "https://yaml.example.com"\ntimeout: 15\n')
    with resp_lib.RequestsMock() as rsps:
        rsps.add(rsps.GET, 'https://cli.example.com', body='<html/>', status=200)
        with patch(
            'sys.argv',
            [
                'link_check',
                'https://cli.example.com',
                '--config-file',
                str(yaml_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0


def test_missing_root_url_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with patch('sys.argv', ['link_check']):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2


def test_output_to_file(tmp_path: Path) -> None:
    output_file = tmp_path / 'report.txt'
    with resp_lib.RequestsMock() as rsps:
        rsps.add(rsps.GET, 'https://example.com', body='<html/>', status=200)
        with patch('sys.argv', ['link_check', 'https://example.com', '-o', str(output_file)]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
    assert output_file.exists()
    content = output_file.read_text()
    assert '=== Configuration Summary ===' in content


@resp_lib.activate
def test_exit_code_0_clean() -> None:
    resp_lib.add(resp_lib.GET, 'https://example.com', body='<html/>', status=200)
    with patch('sys.argv', ['link_check', 'https://example.com']):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0


@resp_lib.activate
def test_exit_code_1_broken() -> None:
    resp_lib.add(
        resp_lib.GET,
        'https://example.com',
        body='<html><body><a href="/missing.html">m</a></body></html>',
        status=200,
    )
    resp_lib.add(resp_lib.GET, 'https://example.com/missing.html', status=404)
    with patch('sys.argv', ['link_check', 'https://example.com']):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
