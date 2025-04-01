"""Extended jobs spec implementation."""

from pythonik.specs.jobs import JobSpec as OriginalJobSpec

from .base import ExtendedSpecBase


class ExtendedJobSpec(ExtendedSpecBase, OriginalJobSpec):
    """
    Extended version of the pythonik JobSpec with improved features.

    Enhances the original JobSpec with:
    - Better logging using the logging module instead of print statements
    - Improved error handling
    """
