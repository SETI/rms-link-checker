# rms-link-checker

<!-- pyml disable MD025 -->

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
<!-- start-after-point -->

**rms-link-checker** is a Python command-line application that crawls a website
starting from a given root URL, checks all discovered links for validity, detects
misplaced asset files, and produces a plain-text report summarizing the results.

Full documentation is available at
[rms-link-checker.readthedocs.io](https://rms-link-checker.readthedocs.io/en/latest/).

# Features

- Crawls an entire website starting from a single root URL
- Checks all discovered links (internal and external) for validity
- Detects broken links (4xx/5xx responses) and broken anchor fragments
- Follows and reports redirect chains
- Detects misplaced asset files (images, documents, scripts, etc.)
- Configurable depth limit, request limit, and thread count
- YAML configuration file support with CLI override precedence
- Non-HTTP scheme links (mailto:, tel:, etc.) recorded and reported
- SSL certificate errors reported per domain
- Plain-text report with 11 sections

# Installation

## End-user (recommended)

```bash
pipx install rms-link-checker
```

## Developer

```bash
git clone https://github.com/SETI/rms-link-checker.git
cd rms-link-checker
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

# Quick Start

```bash
link_check https://example.com
```

With options:

```bash
link_check https://example.com --max-depth 3 --max-threads 20 -o report.txt
```

With a configuration file:

```bash
link_check --config-file config.yaml
```

# Contributing

Information on contributing to this package can be found in the
[Contributing Guide](https://github.com/SETI/rms-link-checker/blob/main/CONTRIBUTING.md).

# Licensing

This code is licensed under the [Apache License v2.0](https://github.com/SETI/rms-link-checker/blob/main/LICENSE).
