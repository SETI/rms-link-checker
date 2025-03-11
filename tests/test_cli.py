"""Tests for the CLI module."""

import unittest
from unittest.mock import patch, MagicMock, mock_open

from check_links.cli import create_parser, main


class TestCLI(unittest.TestCase):
    """Tests for the CLI module."""

    def test_parse_args(self):
        """Test argument parsing."""
        # Test with required arguments only
        args = create_parser().parse_args(["example.html"])
        self.assertEqual(args.target, "example.html")
        self.assertEqual(args.verbose, 0)
        self.assertIsNone(args.output)
        self.assertIsNone(args.log_file)
        self.assertEqual(args.log_level, "DEBUG")
        self.assertIsNone(args.root_url)

        # Test with verbose flag
        args = create_parser().parse_args(["example.html", "-v"])
        self.assertEqual(args.verbose, 1)

        # Test with multiple verbose flags
        args = create_parser().parse_args(["example.html", "-vvv"])
        self.assertEqual(args.verbose, 3)

        # Test with output file
        args = create_parser().parse_args(["example.html", "-o", "report.txt"])
        self.assertEqual(args.output, "report.txt")

        # Test with log file option
        args = create_parser().parse_args(["example.html", "--log-file", "log.txt"])
        self.assertEqual(args.log_file, "log.txt")

        # Test with log level option
        args = create_parser().parse_args(["example.html", "--log-level", "WARNING"])
        self.assertEqual(args.log_level, "WARNING")

        # Test with root URL
        args = create_parser().parse_args(["example.html", "--root-url", "https://example.com"])
        self.assertEqual(args.root_url, "https://example.com")

    @patch('check_links.cli.LinkChecker')
    @patch('check_links.cli.setup_logging')
    def test_main(self, mock_setup_logging, mock_link_checker_cls):
        """Test main function."""
        # Mock the LinkChecker instance
        mock_link_checker = MagicMock()
        mock_link_checker_cls.return_value = mock_link_checker

        # Test successful execution with default arguments
        exit_code = main(["example.html"])

        # Check that setup_logging was called
        mock_setup_logging.assert_called_once()

        # Check that LinkChecker was created with the right arguments
        mock_link_checker_cls.assert_called_once_with(None, [], [])

        # Check that check_links and check_assets were called
        mock_link_checker.check_links.assert_called_once()
        mock_link_checker.check_assets.assert_called_once()

        # Check that print_report was called
        mock_link_checker.print_report.assert_called_once()

        # Check exit code
        self.assertEqual(exit_code, 0)

        # Reset mocks
        mock_setup_logging.reset_mock()
        mock_link_checker_cls.reset_mock()

        # Test with log level option
        exit_code = main(["example.html", "--log-file", "test.log", "--log-level", "WARNING"])

        # Check that setup_logging was called with the right log level
        mock_setup_logging.assert_called_once_with(0, "test.log", "WARNING")

        # Reset mocks
        mock_setup_logging.reset_mock()
        mock_link_checker_cls.reset_mock()

        # Test with root URL
        exit_code = main(["example.html", "--root-url", "https://example.com"])

        # Check that LinkChecker was created with the right root URL
        mock_link_checker_cls.assert_called_once_with("https://example.com", [], [])

        # Reset mocks
        mock_setup_logging.reset_mock()
        mock_link_checker_cls.reset_mock()

        # Test with ignore URLs
        exit_code = main(["example.html", "--ignore-url", "pattern1", "--ignore-url", "pattern2"])

        # Check that LinkChecker was created with the right ignored URLs
        mock_link_checker_cls.assert_called_once_with(None, ["pattern1", "pattern2"], [])

        # Check exit code
        self.assertEqual(exit_code, 0)

        # Test with error in link checking
        mock_link_checker.check_links.side_effect = Exception("Test error")
        exit_code = main(["example.html"])
        self.assertEqual(exit_code, 1)

    def test_logger_format_uses_periods(self):
        """Test that the logger uses periods for fractional seconds."""
        import io
        import logging
        import re
        from check_links.cli import ColoredFormatter

        # Create a test logger
        test_logger = logging.getLogger("test_period_format")
        test_logger.setLevel(logging.DEBUG)

        # Clean any existing handlers
        test_logger.handlers = []

        # Create a stream to capture log output
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        test_logger.addHandler(handler)

        # Use our custom formatter directly
        formatter = ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)

        # Log a test message
        test_logger.debug("Test message with microseconds")

        # Get the log output
        log_output = log_stream.getvalue()

        # Check for period in timestamp
        # Expected format: YYYY-MM-DD HH:MM:SS.microseconds - logger - LEVEL - message
        timestamp_pattern = re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}')
        match = timestamp_pattern.search(log_output)

        self.assertIsNotNone(match, f"Log timestamp doesn't match expected format: {log_output}")

        # Extract the timestamp and verify it has a period for microseconds
        timestamp = match.group(0)
        self.assertIn(".", timestamp, f"No period found in timestamp: {timestamp}")
        self.assertNotIn(",", timestamp, f"Comma found in timestamp: {timestamp}")

    def test_log_file_option(self):
        """Test that the --log-file option works correctly."""
        # Create a temporary file to use as a log file
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            log_path = temp.name

        try:
            # Import the setup_logging function directly
            from check_links.cli import setup_logging

            # Set up logging with a log file
            setup_logging(3, log_path)  # Verbosity 3 = DEBUG

            # Log some test messages
            import logging
            logging.debug("Debug message")
            logging.info("Info message")
            logging.warning("Warning message")
            logging.error("Error message")

            # Check if the log file was created and contains the messages
            with open(log_path, 'r') as f:
                log_content = f.read()
                print(f"Log content: {log_content}")

            # Check for each log level
            self.assertIn("Debug message", log_content)
            self.assertIn("Info message", log_content)
            self.assertIn("Warning message", log_content)
            self.assertIn("Error message", log_content)

            # Check that there is some content in the log file
            self.assertTrue(log_content, "Log file is empty")

        finally:
            # Clean up the temporary file
            import os
            if os.path.exists(log_path):
                os.unlink(log_path)

    def test_log_level_option(self):
        """Test that the --log-level option works correctly for the log file."""
        # Create a temporary file to use as a log file
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            log_path = temp.name

        try:
            # Import the setup_logging function directly
            from check_links.cli import setup_logging

            # Set up logging with a log file and log level set to WARNING
            setup_logging(3, log_path, "WARNING")  # Verbosity 3 = DEBUG, but log file level is WARNING

            # Log some test messages
            import logging
            logging.debug("Debug message")
            logging.info("Info message")
            logging.warning("Warning message")
            logging.error("Error message")

            # Check if the log file was created and contains only WARNING and ERROR messages
            with open(log_path, 'r') as f:
                log_content = f.read()
                print(f"Log content: {log_content}")

            # Debug and Info should not be in the log file
            self.assertNotIn("Debug message", log_content)
            self.assertNotIn("Info message", log_content)

            # Warning and Error should be in the log file
            self.assertIn("Warning message", log_content)
            self.assertIn("Error message", log_content)

            # Check that there is some content in the log file
            self.assertTrue(log_content, "Log file is empty")

        finally:
            # Clean up the temporary file
            import os
            if os.path.exists(log_path):
                os.unlink(log_path)


if __name__ == '__main__':
    unittest.main()