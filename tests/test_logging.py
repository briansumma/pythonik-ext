"""Tests for the logging functionality in pythonik-ext."""

import io
import json
import logging
import os
import unittest
from unittest.mock import patch

import pytest

# Import directly to avoid any potential package initialization issues
from src.pythonikext._logging import (
    JSON_LOGGING_AVAILABLE,
    LogConfig,
    configure_from_env,
    configure_logging,
    get_logger,
)


class TestLogging(unittest.TestCase):
    """Test suite for the logging module."""

    def setUp(self):
        """Set up test fixtures."""
        # Reset logging configuration before each test
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)

    def test_get_logger(self):
        """Test that get_logger returns a logger with the correct name."""
        logger = get_logger("test_logger")
        self.assertEqual(logger.name, "test_logger")

    def test_configure_basic_logging(self):
        """Test basic logging configuration."""
        # Configure with defaults
        configure_logging()

        # Get root logger
        root = logging.getLogger()

        # Check log level
        self.assertEqual(root.level, logging.INFO)

        # Check that a handler was added
        self.assertTrue(len(root.handlers) > 0)

        # Check formatter
        handler = root.handlers[0]
        self.assertIsInstance(handler.formatter, logging.Formatter)

    def test_configure_with_log_config(self):
        """Test logging configuration with LogConfig."""
        # Configure with LogConfig
        config = LogConfig(level="DEBUG", format_="text")
        configure_logging(config)

        # Get root logger
        root = logging.getLogger()

        # Check log level
        self.assertEqual(root.level, logging.DEBUG)

    def test_invalid_log_level(self):
        """Test that invalid log level raises ValueError."""
        config = LogConfig(level="INVALID")
        with self.assertRaises(ValueError):
            configure_logging(config)

    def test_invalid_log_format(self):
        """Test that invalid log format raises ValueError."""
        config = LogConfig(format_="INVALID")
        with self.assertRaises(ValueError):
            configure_logging(config)

    @pytest.mark.skipif(
        not JSON_LOGGING_AVAILABLE, reason="python-json-logger not installed"
    )
    def test_json_logging(self):
        """Test JSON logging format (skipped if module not available)."""
        # Skip if JSON logging is not available
        if not JSON_LOGGING_AVAILABLE:
            self.skipTest("python-json-logger not installed")

        # Configure JSON logging
        config = LogConfig(format_="json", app_name="test-app")
        configure_logging(config)

        # Capture log output
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)

        # Get root logger formatter
        root = logging.getLogger()
        handler.setFormatter(root.handlers[0].formatter)

        # Add handler to test logger
        logger = get_logger("test_json")
        logger.addHandler(handler)

        # Log a message
        logger.warning("Test JSON logging")

        # Check that output is valid JSON
        log_output = stream.getvalue()
        log_data = json.loads(log_output)

        # Check required fields
        self.assertEqual(log_data.get("message"), "Test JSON logging")
        self.assertEqual(log_data.get("app"), "test-app")
        self.assertTrue("@timestamp" in log_data)
        self.assertEqual(log_data.get("logger"), "test_json")

    def test_configure_from_env(self):
        """Test logging configuration from environment variables."""
        # Set environment variables
        with patch.dict(
            os.environ, {
                "PYTHONIK_LOG_LEVEL": "ERROR",
                "PYTHONIK_LOG_FORMAT": "text",
                "PYTHONIK_APP_NAME": "env-test"
            }
        ):
            # Use internal function to configure from env
            configure_from_env()

            # Check log level
            root = logging.getLogger()
            self.assertEqual(root.level, logging.ERROR)

    def test_log_output(self):
        """Test that log messages are correctly formatted."""
        # Configure logging
        configure_logging(LogConfig(level="INFO", format_="text"))

        # Capture log output
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)

        # Get formatter from root logger
        root = logging.getLogger()
        handler.setFormatter(root.handlers[0].formatter)

        # Create test logger with the captured handler
        logger = get_logger("test_output")
        logger.addHandler(handler)

        # Log a message
        logger.info("Test message with %s", "parameters")

        # Check output format
        log_output = stream.getvalue()
        self.assertIn("test_output", log_output)
        self.assertIn("INFO", log_output)
        self.assertIn("Test message with parameters", log_output)

    def test_extra_fields_in_json_logging(self):
        """Test that extra fields are included in JSON output."""
        if not JSON_LOGGING_AVAILABLE:
            self.skipTest("python-json-logger not installed")

        # Configure JSON logging with extra fields
        extra_fields = {"environment": "test", "service": "pythonik-tests"}
        config = LogConfig(
            format_="json", app_name="test-app", extra_fields=extra_fields
        )
        configure_logging(config)

        # Capture log output
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)

        # Get root logger formatter
        root = logging.getLogger()
        handler.setFormatter(root.handlers[0].formatter)

        # Add handler to test logger
        logger = get_logger("test_extra_fields")
        logger.addHandler(handler)

        # Log a message
        logger.info("Testing extra fields")

        # Parse JSON
        log_output = stream.getvalue()
        log_data = json.loads(log_output)

        # Check extra fields
        self.assertEqual(log_data.get("environment"), "test")
        self.assertEqual(log_data.get("service"), "pythonik-tests")


if __name__ == "__main__":
    unittest.main()
