"""
Extensions and enhancements for the pythonik client library.

This package extends the functionality of pythonik, providing additional
features and bug fixes while maintaining API compatibility.
"""

from ._logging import LogConfig, configure_logging, get_logger
from .client import ExtendedPythonikClient, PythonikClient
from .specs.files import ExtendedFilesSpec
from .utils import calculate_md5, suppress_stdout


__all__ = [
    "PythonikClient",
    "ExtendedPythonikClient",
    "ExtendedFilesSpec",
    "calculate_md5",
    "suppress_stdout",
    "configure_logging",
    "get_logger",
    "LogConfig",
]
