"""
Extensions and enhancements for the pythonik client library.

This package extends the functionality of pythonik, providing additional
features and bug fixes while maintaining API compatibility.
"""

from .client import ExtendedPythonikClient, PythonikClient
from .specs.files import ExtendedFilesSpec
from .utils import calculate_md5, suppress_stdout


__version__ = "2025.4-beta"
__all__ = [
    "PythonikClient",
    "ExtendedPythonikClient",
    "ExtendedFilesSpec",
    "calculate_md5",
    "suppress_stdout",
]
