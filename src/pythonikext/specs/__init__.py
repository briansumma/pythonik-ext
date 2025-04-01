"""
Extended spec implementations for pythonik API endpoints.

This package mirrors the structure of pythonik.specs but provides enhanced
versions of each spec with improved logging, error handling, and additional
functionality.
"""

from .assets import ExtendedAssetSpec
from .collection import ExtendedCollectionSpec
from .files import ExtendedFilesSpec
from .jobs import ExtendedJobSpec
from .metadata import ExtendedMetadataSpec
from .search import ExtendedSearchSpec


__all__ = [
    "ExtendedAssetSpec",
    "ExtendedCollectionSpec",
    "ExtendedFilesSpec",
    "ExtendedJobSpec",
    "ExtendedMetadataSpec",
    "ExtendedSearchSpec",
]
