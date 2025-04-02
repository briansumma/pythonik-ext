"""
Example demonstrating the pythonik-ext logging capabilities.

This example shows how to configure and use the advanced logging
features including:
- Basic text logging
- JSON structured logging
- Environment variable configuration
- Custom extra fields
- Different log levels

Requirements:
- For JSON logging: pip install 'pythonik-ext[logging]'
"""

import os
import time

# Example 1: Basic logging usage
from pythonikext import (
    ExtendedPythonikClient,
    LogConfig,
    configure_logging,
    get_logger,
)
from pythonikext._logging import configure_from_env

# Get a module-level logger
logger = get_logger(__name__)


def example_text_logging():
    """Demonstrate basic text logging."""
    # Configure text logging with INFO level
    config = LogConfig(level="INFO", format_="text")
    configure_logging(config)

    logger.info("Text logging configured at INFO level")
    logger.debug("This debug message won't be displayed")

    # Change to DEBUG level to see more details
    config = LogConfig(level="DEBUG", format_="text")
    configure_logging(config)

    logger.info("Text logging reconfigured at DEBUG level")
    logger.debug("Now debug messages are visible")

    # Log different levels
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")

    # Log with parameters (recommended %s style)
    logger.info("Processing file: %s", "example.txt")
    logger.debug("Operation completed in %.2f seconds", 0.54)


def example_json_logging():
    """Demonstrate JSON structured logging (requires python-json-logger)."""
    try:
        # Configure JSON logging with extra fields
        config = LogConfig(
            level="INFO",
            format_="json",
            app_name="pythonik-demo",
            extra_fields={
                "environment": "development",
                "region": "us-west-2",
                "component": "api-client"
            }
        )
        configure_logging(config)

        logger.info("JSON logging configured with extra fields")

        # Log an event with context
        logger.info(
            "API request completed",
            extra={
                "method": "GET",
                "endpoint": "/assets",
                "status_code": 200,
                "duration_ms": 150,
            }
        )

        # Log a more complex event
        try:
            # Simulate an operation
            time.sleep(0.1)
            # pylint: disable=using-constant-test
            if True:  # Simulated condition
                raise ValueError("Simulated error for demonstration")
        except Exception as e:
            logger.exception(
                "Operation failed: %s",
                str(e),
                extra={
                    "operation": "get_asset",
                    "asset_id": "123456",
                    "attempt": 2,
                }
            )
    except ImportError:
        logger.warning(
            "JSON logging not available. Install with: pip install "
            "'pythonik-ext[logging]'"
        )
        # Fall back to text logging
        configure_logging(LogConfig(format_="text"))


def example_env_configuration():
    """Demonstrate configuration through environment variables."""
    # Set environment variables
    os.environ["PYTHONIK_LOG_LEVEL"] = "DEBUG"
    os.environ["PYTHONIK_LOG_FORMAT"] = "text"
    os.environ["PYTHONIK_APP_NAME"] = "env-config-demo"

    # Apply configuration from environment variables
    configure_from_env()

    logger.info("Logging configured from environment variables")
    logger.debug("Debug level enabled via PYTHONIK_LOG_LEVEL")


def example_client_integration():
    """Demonstrate integration with the pythonik client."""
    # Configure logging
    configure_logging(LogConfig(level="INFO"))

    # Initialize client (normally you would use real credentials)
    # pylint: disable=unused-variable
    client = ExtendedPythonikClient(
        app_id="demo-app-id",
        auth_token="demo-token",
        timeout=10,
        base_url="https://app.iconik.io"
    )

    logger.info("Initializing API client")

    # The client methods now use the configured logger
    try:
        # This will likely fail with demo credentials, but shows the logging
        logger.debug("Searching for files with checksum")
        # Uncomment to test real API calls:
        # response = client.files().get_files_by_checksum(
        #     "d41d8cd98f00b204e9800998ecf8427e"
        # )
        # logger.info("Found %d files", len(response.data.objects))

        # For demo purposes, simulate some activity
        logger.info("Simulating file operations")
        time.sleep(0.5)
        logger.info("Operations completed successfully")
    except Exception as e:
        logger.exception("API request failed: %s", str(e))


if __name__ == "__main__":
    print("\n=== Example 1: Basic Text Logging ===")
    example_text_logging()

    print("\n=== Example 2: JSON Structured Logging ===")
    example_json_logging()

    print("\n=== Example 3: Environment Variable Configuration ===")
    example_env_configuration()

    print("\n=== Example 4: Client Integration ===")
    example_client_integration()

    print("\nAll examples completed.")
