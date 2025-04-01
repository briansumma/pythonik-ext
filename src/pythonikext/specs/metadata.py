"""Extended metadata spec implementation."""

from pythonik.specs.metadata import MetadataSpec as OriginalMetadataSpec

from .base import ExtendedSpecBase


class ExtendedMetadataSpec(ExtendedSpecBase, OriginalMetadataSpec):
    """
    Extended version of the pythonik MetadataSpec with improved features.

    Enhances the original MetadataSpec with:
    - Better logging using the logging module instead of print statements
    - Improved error handling
    """
