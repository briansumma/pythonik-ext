"""Extended Pythonik client with additional functionality."""

from pythonik.client import PythonikClient as OriginalClient

from .specs import (
    ExtendedAssetSpec,
    ExtendedCollectionSpec,
    ExtendedFilesSpec,
    ExtendedJobSpec,
    ExtendedMetadataSpec,
    ExtendedSearchSpec,
)


class ExtendedPythonikClient(OriginalClient):
    """
    Extended version of the pythonik PythonikClient with additional features.

    - Uses enhanced specs with improved logging and error handling
    - Provides access to additional functionality like file checksum lookup

    Usage:
        >>> from pythonikext import ExtendedPythonikClient
        >>> client = ExtendedPythonikClient(
        ...     app_id="...", auth_token="...", timeout=10
        ... )
        >>> response = client.files().get_files_by_checksum("path/to/file.txt")
    """

    def assets(self) -> ExtendedAssetSpec:
        """
        Returns an extended version of the AssetSpec with additional features.

        Returns:
            ExtendedAssetSpec: An enhanced assets spec with improved logging
                and error handling
        """
        return ExtendedAssetSpec(self.session, self.timeout, self.base_url)

    def collections(self) -> ExtendedCollectionSpec:
        """
        Returns an extended version of the CollectionSpec with additional
        features.

        Returns:
            ExtendedCollectionSpec: An enhanced collections spec with improved
                logging and error handling
        """
        return ExtendedCollectionSpec(self.session, self.timeout, self.base_url)

    def files(self) -> ExtendedFilesSpec:
        """
        Returns an extended version of the FilesSpec with additional
        functionality.

        Returns:
            ExtendedFilesSpec: An enhanced files spec with additional methods
                including checksum-based file lookup
        """
        return ExtendedFilesSpec(self.session, self.timeout, self.base_url)

    def jobs(self) -> ExtendedJobSpec:
        """
        Returns an extended version of the JobSpec with additional features.

        Returns:
            ExtendedJobSpec: An enhanced jobs spec with improved logging and
                error handling
        """
        return ExtendedJobSpec(self.session, self.timeout, self.base_url)

    def metadata(self) -> ExtendedMetadataSpec:
        """
        Returns an extended version of the MetadataSpec with additional
        features.

        Returns:
            ExtendedMetadataSpec: An enhanced metadata spec with improved
                logging and error handling
        """
        return ExtendedMetadataSpec(self.session, self.timeout, self.base_url)

    def search(self) -> ExtendedSearchSpec:
        """
        Returns an extended version of the SearchSpec with additional features.

        Returns:
            ExtendedSearchSpec: An enhanced search spec with improved logging
                and error handling
        """
        return ExtendedSearchSpec(self.session, self.timeout, self.base_url)


# Create an alias for backward compatibility
PythonikClient = ExtendedPythonikClient
