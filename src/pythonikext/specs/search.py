"""Extended search spec implementation."""

from pythonik.specs.search import SearchSpec as OriginalSearchSpec

from .base import ExtendedSpecBase


class ExtendedSearchSpec(ExtendedSpecBase, OriginalSearchSpec):
    """
    Extended version of the pythonik SearchSpec with improved features.

    Enhances the original SearchSpec with:
    - Better logging using the logging module instead of print statements
    - Improved error handling
    """
