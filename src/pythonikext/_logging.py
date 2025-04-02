"""
Logging configuration and setup for pythonik-ext.
Supports both JSON and text formats with structured logging.
"""

import logging
import logging.config
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

# Handle both old and new pythonjsonlogger import locations
JSON_LOGGING_AVAILABLE = False
try:
    # Try new import location first
    from pythonjsonlogger.json import JsonFormatter

    JSON_LOGGING_AVAILABLE = True
except ImportError:
    try:
        # Fall back to old import location
        from pythonjsonlogger.jsonlogger import JsonFormatter

        JSON_LOGGING_AVAILABLE = True
    except ImportError:
        # Package not available
        JsonFormatter = None
        JSON_LOGGING_AVAILABLE = False

# Constants
VALID_LOG_FORMATS = ["text", "json"]
VALID_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Get version from package
try:
    from .__version__ import __version__ as VERSION
except ImportError:
    VERSION = "unknown"


class PythonikJsonFormatter(JsonFormatter):
    """Custom JSON formatter with additional fields."""

    def __init__(
        self,
        app_name: str = "pythonik-ext",
        extra_fields: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the JSON formatter.

        Args:
            app_name: Name of the application
            extra_fields: Additional fields to include in every log entry
        """
        super().__init__()
        self.app_name = app_name
        self.extra_fields = extra_fields or {}

    def add_fields(
        self, log_record: Dict[str, Any], record: logging.LogRecord,
        message_dict: Dict[str, Any]
    ) -> None:
        """Add custom fields to the log record."""
        super().add_fields(log_record, record, message_dict)

        # Add standard fields
        log_record.update({
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "app": self.app_name,
            "version": VERSION,
            "logger": record.name,
        })

        # Add any extra fields
        log_record.update(self.extra_fields)


class LogConfig:
    """Configuration for logging."""

    def __init__(
        self,
        level: str = "INFO",
        format_: str = "text",
        app_name: str = "pythonik-ext",
        extra_fields: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize logging configuration.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            format_: Log format (text, json)
            app_name: Name of the application
            extra_fields: Additional fields to include in JSON logs
        """
        self.level = level.upper()
        self.format = format_.lower()
        self.app_name = app_name
        self.extra_fields = extra_fields or {}


def configure_logging(
    config: Optional[Union[LogConfig, Dict[str, Any]]] = None
) -> None:
    """
    Configure logging with proper stderr handling.
    
    Args:
        config: LogConfig object or dict with configuration options
        
    Raises:
        ValueError: If log level or format is invalid
        ImportError: If JSON logging is requested but pythonjsonlogger isn't
            installed
    """
    # Parse configuration
    if config is None:
        # Default configuration
        config = LogConfig()
    elif isinstance(config, dict):
        # Convert dict to LogConfig
        config = LogConfig(**config)

    if config.level not in VALID_LOG_LEVELS:
        raise ValueError(f"Invalid log level: {config.level}")

    if config.format not in VALID_LOG_FORMATS:
        raise ValueError(f"Invalid log format: {config.format}")

    # Check if JSON logging is available
    if config.format == "json" and not JSON_LOGGING_AVAILABLE:
        raise ImportError(
            "JSON logging requested but python-json-logger is not installed. "
            "Install with 'pip install python-json-logger'."
        )

    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(config.level)

    # Create formatter based on format
    if config.format == "json":
        formatter = PythonikJsonFormatter(
            app_name=config.app_name, extra_fields=config.extra_fields
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    # Update existing handlers or create new one
    if logger.handlers:
        for handler in logger.handlers:
            handler.setFormatter(formatter)
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Args:
        name: Logger name, typically __name__
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def configure_from_env() -> None:
    """
    Configure logging based on environment variables.
    
    Environment variables:
        PYTHONIK_LOG_LEVEL: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        PYTHONIK_LOG_FORMAT: Log format (text, json)
        PYTHONIK_APP_NAME: Application name for JSON logs
    """
    level = os.environ.get("PYTHONIK_LOG_LEVEL", "INFO")
    format_ = os.environ.get("PYTHONIK_LOG_FORMAT", "text")
    app_name = os.environ.get("PYTHONIK_APP_NAME", "pythonik-ext")

    config = LogConfig(level=level, format_=format_, app_name=app_name)
    configure_logging(config)


# Autoconfigure from environment if this module is imported directly
if __name__ != "__main__":
    # Only configure if no handlers exist to avoid duplicate configuration
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        configure_from_env()
