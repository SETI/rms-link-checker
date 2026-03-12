# REPONAME

<!-- pyml disable MD025 -->

[![GitHub release; latest by date](https://img.shields.io/github/v/release/SETI/REPONAME)](https://github.com/SETI/REPONAME/releases)
[![GitHub Release Date](https://img.shields.io/github/release-date/SETI/REPONAME)](https://github.com/SETI/REPONAME/releases)
[![Test Status](https://img.shields.io/github/actions/workflow/status/SETI/REPONAME/run-tests.yml?branch=main)](https://github.com/SETI/REPONAME/actions)
[![Documentation Status](https://readthedocs.org/projects/REPONAME/badge/?version=latest)](https://REPONAME.readthedocs.io/en/latest/?badge=latest)
[![Code coverage](https://img.shields.io/codecov/c/github/SETI/REPONAME/main?logo=codecov)](https://codecov.io/gh/SETI/REPONAME)
<br />
[![PyPI - Version](https://img.shields.io/pypi/v/REPONAME)](https://pypi.org/project/REPONAME)
[![PyPI - Format](https://img.shields.io/pypi/format/REPONAME)](https://pypi.org/project/REPONAME)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/REPONAME)](https://pypi.org/project/REPONAME)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/REPONAME)](https://pypi.org/project/REPONAME)
<br />
[![GitHub commits since latest release](https://img.shields.io/github/commits-since/SETI/REPONAME/latest)](https://github.com/SETI/REPONAME/commits/main/)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/m/SETI/REPONAME)](https://github.com/SETI/REPONAME/commits/main/)
[![GitHub last commit](https://img.shields.io/github/last-commit/SETI/REPONAME)](https://github.com/SETI/REPONAME/commits/main/)
<br />
[![Number of GitHub open issues](https://img.shields.io/github/issues-raw/SETI/REPONAME)](https://github.com/SETI/REPONAME/issues)
[![Number of GitHub closed issues](https://img.shields.io/github/issues-closed-raw/SETI/REPONAME)](https://github.com/SETI/REPONAME/issues)
[![Number of GitHub open pull requests](https://img.shields.io/github/issues-pr-raw/SETI/REPONAME)](https://github.com/SETI/REPONAME/pulls)
[![Number of GitHub closed pull requests](https://img.shields.io/github/issues-pr-closed-raw/SETI/REPONAME)](https://github.com/SETI/REPONAME/pulls)
<br />
![GitHub License](https://img.shields.io/github/license/SETI/REPONAME)
[![Number of GitHub stars](https://img.shields.io/github/stars/SETI/REPONAME)](https://github.com/SETI/REPONAME/stargazers)
![GitHub forks](https://img.shields.io/github/forks/SETI/REPONAME)
[![DOI](https://zenodo.org/badge/REPONAME.svg)](https://zenodo.org/badge/latestdoi/{REPONAME})
<!-- start-after-point -->

# Features

`REPONAME` is TODO

# Installation

## Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/SETI/REPONAME.git
   cd REPONAME
   ```

2. Create and activate a virtual environment (recommended):

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the package (editable with dev tools):

   ```bash
   pip install -e ".[dev]"
   ```
   Or install only runtime dependencies: `pip install -e .`

4. Set up SPICE kernels:
   - Download the required SPICE kernels for your mission
   - Set the `SPICE_PATH` environment variable to point to your kernels directory:

     ```bash
     export SPICE_PATH=/path/to/your/spice/kernels
     ```

> **Note**: To fix mypy operability with editable pip installs:
> ```bash
> export SETUPTOOLS_ENABLE_FEATURES="legacy-editable"
> ```

# Quick Start

TODO

# Documentation

Comprehensive documentation is available in the `docs` directory.

To build the documentation:

```bash
cd docs
make html
```

The built documentation will be available in `docs/_build/html`.

# Contributing

Information on contributing to this package can be found in the
[Contributing Guide](https://github.com/SETI/REPONAME/blob/main/CONTRIBUTING.md).

# Licensing

This code is licensed under the [Apache License v2.0](https://github.com/SETI/REPONAME/blob/main/LICENSE).
