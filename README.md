# Check Links

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
pip install link_checker
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