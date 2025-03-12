#!/usr/bin/env python3
"""Command-line interface for the link checker."""

import argparse
import logging
import sys
from typing import List, Optional

from colorama import init as colorama_init, Fore, Style

from link_checker.main import LinkChecker

try:
    from link_checker._version import __version__  # type: ignore
except ImportError:  # pragma: no cover
    __version__ = 'Version unspecified'


# Custom formatter for colored and properly formatted logs
class ColoredFormatter(logging.Formatter):
    """A formatter that adds colors to logs based on their level and uses periods for
    fractions."""

    COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    def __init__(self, fmt=None, datefmt=None, style='%'):
        # Note: Don't include microseconds in datefmt as we'll manually format it in
        # formatTime
        if datefmt is None:
            datefmt = '%Y-%m-%d %H:%M:%S'
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)

    def formatTime(self, record, datefmt=None):
        """Override formatTime to ensure periods are used for fractional seconds."""
        # Get the basic timestamp without microseconds
        if datefmt is None:
            datefmt = self.datefmt

        # Create time string without microseconds
        time_str = super().formatTime(record, datefmt)

        # Manually add microseconds with a period
        if '%f' not in datefmt:  # If %f not in format, add microseconds ourselves
            msec = record.created - int(record.created)
            time_str = f"{time_str}.{int(msec * 1000000):06d}"

        return time_str

    def format(self, record: logging.LogRecord) -> str:
        log_message = super().format(record)
        color = self.COLORS.get(record.levelno, Fore.WHITE)
        return color + log_message + Style.RESET_ALL


def setup_logging(verbosity: int,
                  log_file: Optional[str] = None,
                  log_level: Optional[str] = None) -> None:
    """Set up logging based on verbosity level.

    Args:
        verbosity: The verbosity level (0=ERROR, 1=WARNING, 2=INFO, 3=DEBUG).
        log_file: Optional path to a file where log messages should be written.
        log_level: Optional minimum level for messages in the log file.
    """
    # Initialize colorama for colored output
    colorama_init()

    # Ensure that Python's logging system uses periods for fractional seconds globally
    import locale
    locale_bak = locale.setlocale(locale.LC_ALL)
    try:
        # Set locale to ensure periods are used instead of commas
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except Exception:
        try:
            # Try C locale as fallback (which uses period as decimal separator)
            locale.setlocale(locale.LC_ALL, 'C')
        except Exception as e:
            # If locale setting fails, just log a warning
            print(f"Warning: Could not set locale to use periods in timestamps: {str(e)}")
    finally:
        # Restore original locale once logging is configured
        locale.setlocale(locale.LC_ALL, locale_bak)

    # Set up logging
    root_logger = logging.getLogger()

    # Clear any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Determine log level based on verbosity for console output
    if verbosity == 0:
        console_log_level = logging.ERROR
    elif verbosity == 1:
        console_log_level = logging.WARNING
    elif verbosity == 2:
        console_log_level = logging.INFO
    else:  # verbosity >= 3
        console_log_level = logging.DEBUG

    # Configure the root logger to the most verbose level that will be used
    # (between console and file)
    file_log_level = getattr(logging, log_level) if log_level else logging.DEBUG
    root_logger.setLevel(min(console_log_level, file_log_level))

    # Create a console handler and set its level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_log_level)

    # Create a formatter with a custom date format using periods
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S.%f'
    )
    console_handler.setFormatter(formatter)

    # Set up colored logging for the console handler
    console_handler.setFormatter(ColoredFormatter(formatter._fmt))

    # Add the console handler to the root logger
    root_logger.addHandler(console_handler)

    # Set up file logging if a log file is specified
    if log_file:
        try:
            # Create a file handler
            file_handler = logging.FileHandler(log_file, mode='w')

            # Set the log level for the file handler
            file_handler.setLevel(file_log_level)

            # Use the same formatter but without colors
            file_formatter = logging.Formatter(
                fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S.%f'
            )
            file_handler.setFormatter(file_formatter)

            # Add the file handler to the root logger
            root_logger.addHandler(file_handler)

            logging.info(f"Logging to file: {log_file} (level: {log_level})")
        except Exception as e:
            logging.error(f"Failed to set up logging to file {log_file}: {str(e)}")

    # Set the logger for the requests library to warning to avoid verbose output
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the command line tool."""
    parser = argparse.ArgumentParser(
        description="Check for broken links in a file or directory of files. "
        f"Version: {__version__}."
    )
    parser.add_argument(
        "root_url", help="File or directory to check for broken links."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase output verbosity. Can be used multiple times."
    )
    parser.add_argument(
        "--log-file",
        help="File to write log messages to."
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="DEBUG",
        help="Minimum level for messages in the log file."
    )
    parser.add_argument(
        "-o", "--output",
        help="Write the report to the specified file instead of stdout."
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Timeout in seconds for HTTP requests."
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="Maximum number of requests to make (default: unlimited)."
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum depth to crawl (default: unlimited)."
    )
    parser.add_argument(
        "--max-threads",
        type=int,
        default=10,
        help="Maximum number of concurrent threads for requests (default: 10)."
    )
    parser.add_argument(
        "--ignore-asset-url-file",
        default=None,
        help="URL pattern to ignore for assets. Can be used multiple times."
    )
    parser.add_argument(
        "--ignore-internal-url-file",
        default=None,
        help="URL pattern to ignore for internal links. Can be used multiple times."
    )
    parser.add_argument(
        "--ignore-external-links-file",
        default=None,
        help="File with external links to ignore in reporting, one per line."
    )
    return parser


def read_list_from_file(file_path: str) -> List[str]:
    """Read a list of items from a file, one per line.

    Args:
        file_path: Path to the file.

    Returns:
        A list of strings, one per line in the file.
    """
    with open(file_path, 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]


def main(args: Optional[List[str]] = None) -> int:
    """Run the link checker from the command line.

    Args:
        args: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        The exit code (0 for success, non-zero for errors).
    """
    try:
        # Parse command-line arguments
        parsed_args = create_parser().parse_args(args)

        # Set up logging
        setup_logging(parsed_args.verbose, parsed_args.log_file, parsed_args.log_level)

        if parsed_args.log_file:
            logging.info(f"Logs will be written to: {parsed_args.log_file}")

        # Read ignored paths from files
        ignored_asset_paths = None
        ignored_internal_paths = None
        ignored_external_links = None

        if parsed_args.ignore_asset_url_file:
            try:
                ignored_asset_paths = read_list_from_file(parsed_args.ignore_asset_url_file)
                logging.info(f"Loaded {len(ignored_asset_paths)} asset paths to ignore")
            except Exception as e:
                logging.error(f"Error reading ignored asset paths file: {e}")
                return 1

        if parsed_args.ignore_internal_url_file:
            try:
                ignored_internal_paths = read_list_from_file(parsed_args.ignore_internal_url_file)
                logging.info(f"Loaded {len(ignored_internal_paths)} asset paths to ignore")
            except Exception as e:
                logging.error(f"Error reading ignored internal paths file: {e}")
                return 1

        if parsed_args.ignore_external_links_file:
            try:
                ignored_external_links = read_list_from_file(parsed_args.ignore_external_links_file)
                logging.info(f"Loaded {len(ignored_external_links)} external links to ignore")
            except Exception as e:
                logging.error(f"Error reading ignored external links file: {e}")
                return 1

        # Create a link checker
        checker = LinkChecker(parsed_args.root_url,
                              ignored_asset_paths or [],
                              ignored_internal_paths or [],
                              ignored_external_links=ignored_external_links,
                              timeout=parsed_args.timeout,
                              max_requests=parsed_args.max_requests,
                              max_depth=parsed_args.max_depth,
                              max_threads=parsed_args.max_threads)

        logging.info(f"Starting link checker with: timeout={parsed_args.timeout}s, "
                     f"max_requests={parsed_args.max_requests}, "
                     f"max_depth={parsed_args.max_depth}, "
                     f"max_threads={parsed_args.max_threads}")

        # Run the link checker
        checker.run()

        # Redirect output to a file if specified
        if parsed_args.output:
            sys.stdout = open(parsed_args.output, 'w')

        # Print the report
        checker.print_report()

        # Close the output file if specified
        if parsed_args.output:
            sys.stdout.close()
            sys.stdout = sys.__stdout__

        # Return success exit code (0)
        return 0

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
