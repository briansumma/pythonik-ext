"""Extended assets spec implementation."""

from pythonik.specs.assets import AssetSpec as OriginalAssetSpec

from .base import ExtendedSpecBase


class ExtendedAssetSpec(ExtendedSpecBase, OriginalAssetSpec):
    """
    Extended version of the pythonik AssetSpec with improved features.

    Enhances the original AssetSpec with:
    - Better logging using the logging module instead of print statements
    - Improved error handling
    """
