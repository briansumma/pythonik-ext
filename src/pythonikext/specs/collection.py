"""Extended collection spec implementation."""

from pythonik.specs.collection import CollectionSpec as OriginalCollectionSpec

from .base import ExtendedSpecBase


class ExtendedCollectionSpec(ExtendedSpecBase, OriginalCollectionSpec):
    """
    Extended version of the pythonik CollectionSpec with improved features.

    Enhances the original CollectionSpec with:
    - Better logging using the logging module instead of print statements
    - Improved error handling
    """
