"""Extended Pythonik client with additional functionality."""

from pythonik.client import PythonikClient as OriginalClient

from .specs.files import ExtendedFilesSpec


class ExtendedPythonikClient(OriginalClient):
    """
    Extended version of the pythonik PythonikClient with additional features.
    
    - Uses enhanced specs with improved logging and error handling
    - Provides access to additional functionality like file checksum lookup
    
    Usage:
        >>> from pythonikext import ExtendedPythonikClient
        >>> client = ExtendedPythonikClient(app_id="...", auth_token="...", timeout=10)
        >>> response = client.files().get_files_by_checksum("path/to/file.txt")
    """  # noqa: E501

    def files(self) -> ExtendedFilesSpec:
        """
        Returns an extended version of the FilesSpec with additional functionality.
        
        Returns:
            ExtendedFilesSpec: An enhanced files spec with additional methods
        """  # noqa: E501
        return ExtendedFilesSpec(self.session, self.timeout, self.base_url)


# Create an alias for backward compatibility
PythonikClient = ExtendedPythonikClient
