[![GitHub release; latest by date](https://img.shields.io/github/v/release/SETI/rms-link-checker)](https://github.com/SETI/rms-link-checker/releases)
[![GitHub Release Date](https://img.shields.io/github/release-date/SETI/rms-link-checker)](https://github.com/SETI/rms-link-checker/releases)
[![Test Status](https://img.shields.io/github/actions/workflow/status/SETI/rms-link-checker/run-tests.yml?branch=main)](https://github.com/SETI/rms-link-checker/actions)
[![Documentation Status](https://readthedocs.org/projects/rms-link-checker/badge/?version=latest)](https://rms-link-checker.readthedocs.io/en/latest/?badge=latest)
[![Code coverage](https://img.shields.io/codecov/c/github/SETI/rms-link-checker/main?logo=codecov)](https://codecov.io/gh/SETI/rms-link-checker)
<br />
[![PyPI - Version](https://img.shields.io/pypi/v/rms-link-checker)](https://pypi.org/project/rms-link-checker)
[![PyPI - Format](https://img.shields.io/pypi/format/rms-link-checker)](https://pypi.org/project/rms-link-checker)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/rms-link-checker)](https://pypi.org/project/rms-link-checker)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/rms-link-checker)](https://pypi.org/project/rms-link-checker)
<br />
[![GitHub commits since latest release](https://img.shields.io/github/commits-since/SETI/rms-link-checker/latest)](https://github.com/SETI/rms-link-checker/commits/main/)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/m/SETI/rms-link-checker)](https://github.com/SETI/rms-link-checker/commits/main/)
[![GitHub last commit](https://img.shields.io/github/last-commit/SETI/rms-link-checker)](https://github.com/SETI/rms-link-checker/commits/main/)
<br />
[![Number of GitHub open issues](https://img.shields.io/github/issues-raw/SETI/rms-link-checker)](https://github.com/SETI/rms-link-checker/issues)
[![Number of GitHub closed issues](https://img.shields.io/github/issues-closed-raw/SETI/rms-link-checker)](https://github.com/SETI/rms-link-checker/issues)
[![Number of GitHub open pull requests](https://img.shields.io/github/issues-pr-raw/SETI/rms-link-checker)](https://github.com/SETI/rms-link-checker/pulls)
[![Number of GitHub closed pull requests](https://img.shields.io/github/issues-pr-closed-raw/SETI/rms-link-checker)](https://github.com/SETI/rms-link-checker/pulls)
<br />
![GitHub License](https://img.shields.io/github/license/SETI/rms-link-checker)
[![Number of GitHub stars](https://img.shields.io/github/stars/SETI/rms-link-checker)](https://github.com/SETI/rms-link-checker/stargazers)
![GitHub forks](https://img.shields.io/github/forks/SETI/rms-link-checker)

# Link Checker

A Python tool that checks websites for broken links and catalogs internal assets.

## Features

- Crawls websites starting from a root URL that respects URL hierarchy boundaries
  (won't crawl "up" from the starting URL)
- Detects broken internal links
- Catalogs references to non-HTML assets (images, text files, etc.)
- Only visits each page once
- Ignores external links
- Provides detailed logging
- Allows specifying paths to exclude from internal asset reporting
- Supports checking but not crawling specific website sections

## Installation

```bash
pip install rms-link-checker
```

Or from source:

```bash
git clone https://github.com/SETI/rms-link-checker.git
cd rms-link-checker
pip install -e .
```

## Usage

```bash
link_checker https://example.com
```

### Options

- `--verbose` or `-v`: Increase verbosity (can be used multiple times)
- `--output` or `-o`: Specify output file for results (default: stdout)
- `--log-file`: Write log messages to a file (in addition to console output)
- `--log-level`: Set the minimum level for messages in the log file (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--timeout`: Timeout in seconds for HTTP requests (default: 10.0)
- `--max-requests`: Maximum number of requests to make (default: unlimited)
- `--max-depth`: Maximum depth to crawl (default: unlimited)
- `--ignore-asset-paths-file`: Specify a file containing paths to ignore when reporting internal assets (one per line)
- `--ignore-internal-paths-file`: Specify a file containing paths to check once but not crawl (one per line)

### Examples

Simple check:
```bash
link_checker https://example.com
```

Check a specific section of a website (won't crawl to parent directories):
```bash
link_checker https://example.com/section/subsection
```

Ignore specific asset paths:
```bash
# Create a file with paths to ignore
echo "/images" > ignore_assets.txt
echo "css" >> ignore_assets.txt      # Leading slash is optional
echo "scripts" >> ignore_assets.txt

link_checker https://example.com --ignore-asset-paths-file ignore_assets.txt
```

Check but don't crawl specific sections:
```bash
# Create a file with paths to check but not crawl
echo "docs" > ignore_crawl.txt       # Leading slash is optional
echo "/blog" >> ignore_crawl.txt

link_checker https://example.com --ignore-internal-paths-file ignore_crawl.txt
```

Verbose output with detailed logging:
```bash
link_checker https://example.com -vv
```

Verbose output with logs written to a file:
```bash
link_checker https://example.com -vv --log-file=link_checker.log
```

Verbose output with logs written to a file, but only warnings and errors:
```bash
link_checker https://example.com -vv --log-file=link_checker.log --log-level=WARNING
```

Limit crawl depth and set a longer timeout:
```bash
link_checker https://example.com --max-depth=3 --timeout=30.0
```

Limit the number of requests to avoid overwhelming the server:
```bash
link_checker https://example.com --max-requests=50
```

### Report Format

The report includes:
- Configuration summary (root URL, hierarchy boundary, and ignored paths)
- Broken links found (grouped by page)
- Internal assets (grouped by type)
- Summary with counts (visited pages, broken links, assets)
- Stats on ignored assets, limited-crawl sections, and URLs outside hierarchy

## Development

### Setup development environment

```bash
pip install -e ".[dev]"
```

### Run tests

```bash
pytest
```

## License

MIT License