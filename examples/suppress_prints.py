"""
Example script showing how to suppress all print statements from pythonik.

The original pythonik library uses print statements for debugging,
which can be noisy and interfere with logging. This example demonstrates
how to completely suppress these print statements while still getting
proper logging.
"""

import sys

from pythonikext import (
    ExtendedPythonikClient,
    LogConfig,
    configure_logging,
    get_logger,
    suppress_stdout,
)

# Get a logger for this module
logger = get_logger(__name__)


class PrintCapture:
    """
    A context manager that captures print statements and redirects them
    to a logger if desired.
    """

    def __init__(self, log_captured=False, log_level='DEBUG'):
        """
        Initialize the print capturer.
        
        Args:
            log_captured: Whether to log captured print statements
            log_level: Level to use for logging captured prints
        """
        self.log_captured = log_captured
        self.log_level = log_level
        self.original_stdout = None
        self.captured_output = []

    def __enter__(self):
        """Start capturing stdout."""

        class StdoutRedirector:

            def __init__(self, capture_obj):
                self.capture_obj = capture_obj

            def write(self, text):
                if text.strip():  # Only capture non-empty strings
                    self.capture_obj.captured_output.append(text)
                    if self.capture_obj.log_captured:
                        log_method = getattr(
                            logger, self.capture_obj.log_level.lower()
                        )
                        log_method("Captured print: %s", text.strip())

            def flush(self):
                pass

        self.original_stdout = sys.stdout
        sys.stdout = StdoutRedirector(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore original stdout."""
        sys.stdout = self.original_stdout

    def get_captured_text(self):
        """Get all captured text."""
        return ''.join(self.captured_output)


def example_with_print_suppression():
    """Example using suppress_stdout context manager."""
    # Configure logging first
    configure_logging(LogConfig(level="INFO"))
    logger.info("Starting operation with print suppression")

    # Use the built-in suppress_stdout
    with suppress_stdout():
        # This print will be suppressed
        print("This print statement won't be visible")

        # Create client and make API calls
        # All print statements from the pythonik library will be suppressed
        # pylint: disable=unused-variable
        client = ExtendedPythonikClient(
            app_id="demo-app-id", auth_token="demo-token", timeout=10
        )

        # Logging still works
        logger.info("Client initialized with print suppression")

    # Prints outside the context manager work normally
    # pylint: disable=unreachable
    print("This print statement is visible again")


def example_with_print_redirection():
    """Example using PrintCapture to redirect prints to logs."""
    # Configure logging first
    configure_logging(LogConfig(level="DEBUG"))
    logger.info("Starting operation with print redirection")

    # Use the PrintCapture context manager to redirect prints to logs
    with PrintCapture(log_captured=True, log_level='DEBUG'):
        # This print will be captured and logged
        print("This print statement is captured and logged")

        # Create client and make API calls
        # All print statements from the pythonik library will be logged
        # pylint: disable=unused-variable
        client = ExtendedPythonikClient(
            app_id="demo-app-id", auth_token="demo-token", timeout=10
        )

        # Logging works as normal
        logger.info("Client initialized with print redirection")

    # Prints outside the context manager work normally
    print("This print statement is visible again")


if __name__ == "__main__":
    print("\n=== Example 1: Suppressing Print Statements ===")
    example_with_print_suppression()

    print("\n=== Example 2: Redirecting Print Statements to Logs ===")
    example_with_print_redirection()

    print("\nAll examples completed.")
