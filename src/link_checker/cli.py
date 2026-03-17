"""Command-line entry point for rms-link-checker."""

from __future__ import annotations

import argparse
import logging
import sys

from link_checker import __version__
from link_checker.config import load_config
from link_checker.crawler import Crawler
from link_checker.progress import ProgressReporter
from link_checker.report import generate_report

_EXIT_OK = 0
_EXIT_PROBLEMS = 1
_EXIT_CONFIG_ERROR = 2
_EXIT_INTERRUPTED = 130


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the link_check CLI.

    Returns:
        Configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog='link_check',
        description='Crawl a website, check all links, and generate a report.',
    )
    parser.add_argument(
        'root_url',
        nargs='?',
        default=None,
        help='Root URL to begin crawling (may also be set in the config file).',
    )
    parser.add_argument(
        '-o',
        '--output',
        default=None,
        metavar='PATH',
        help='File path for the final plain-text report (default: stdout).',
    )
    parser.add_argument(
        '--log-file',
        default=None,
        metavar='PATH',
        help='File path for log messages (default: stderr).',
    )
    parser.add_argument(
        '--log-level',
        default=None,
        type=str.upper,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        metavar='LEVEL',
        help='Minimum log level (default: INFO).',
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=None,
        metavar='SECONDS',
        help='Timeout in seconds for each HTTP request (default: 10).',
    )
    parser.add_argument(
        '--retries',
        type=int,
        default=None,
        metavar='N',
        help='Number of retry attempts for transient failures (default: 3).',
    )
    parser.add_argument(
        '--max-requests',
        type=int,
        default=None,
        metavar='N',
        help='Maximum total HTTP requests to issue (default: unlimited).',
    )
    parser.add_argument(
        '--max-depth',
        type=int,
        default=None,
        metavar='N',
        help='Maximum directory depth to crawl (default: unlimited).',
    )
    parser.add_argument(
        '--max-threads',
        type=int,
        default=None,
        metavar='N',
        help='Maximum number of concurrent threads (default: 10).',
    )
    parser.add_argument(
        '--max-referencing-pages',
        type=int,
        default=None,
        metavar='N',
        help='Maximum referencing pages listed per URL in report (default: 10).',
    )
    parser.add_argument(
        '--verify',
        default=None,
        metavar='BOOL_OR_PATH',
        help=(
            'TLS certificate verification. '
            'Pass "false" to disable (insecure, e.g. for self-signed certs), '
            '"true" to enable (default), or a path to a CA-bundle file.'
        ),
    )
    parser.add_argument(
        '--config-file',
        default=None,
        metavar='PATH',
        help='Path to a YAML configuration file.',
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}',
    )
    return parser


def _setup_logging(log_file: str | None, log_level: str) -> None:
    """Configure the ``link_checker`` logger.

    Parameters:
        log_file: File path for log output. If None, logs go to stderr.
        log_level: Log level string (e.g. ``'INFO'``).
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    handler: logging.Handler
    if log_file is not None:
        handler = logging.FileHandler(log_file, encoding='utf-8')
    else:
        handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(numeric_level)
    formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    log = logging.getLogger('link_checker')
    log.setLevel(numeric_level)
    for h in log.handlers:
        h.close()
    log.handlers.clear()
    log.addHandler(handler)
    log.propagate = False


def main() -> None:
    """Entry point for the link_check CLI command."""
    parser = _build_parser()
    args = parser.parse_args()

    try:
        config = load_config(args, config_path=args.config_file)
    except ValueError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(_EXIT_CONFIG_ERROR)

    _setup_logging(config.log_file, config.log_level)

    progress = ProgressReporter()
    crawler = Crawler(config, progress=progress)
    progress.start()
    interrupted = False
    try:
        results = crawler.crawl()
    except KeyboardInterrupt:
        interrupted = True
        print('\nInterrupted — waiting for in-flight requests to finish...', file=sys.stderr)
        crawler.abort()
        results = crawler.results
    finally:
        progress.stop()

    if interrupted:
        print('Generating partial report.', file=sys.stderr)

    report = generate_report(results, config)

    if config.output:
        with open(config.output, 'w', encoding='utf-8') as fh:
            fh.write(report)
    else:
        print(report, end='')

    sys.exit(
        _EXIT_INTERRUPTED
        if interrupted
        else (_EXIT_PROBLEMS if results.has_problems() else _EXIT_OK)
    )
