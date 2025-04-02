"""Extended files spec implementation with additional functionality."""

from pathlib import Path
from typing import Any, Dict, Optional, Union

from pythonik.models.base import Response
from pythonik.models.files.file import Files
from pythonik.specs.files import FilesSpec as OriginalFilesSpec

from ..utils import calculate_md5
from .base import ExtendedSpecBase


class ExtendedFilesSpec(ExtendedSpecBase, OriginalFilesSpec):
    """
    Extended version of the pythonik FilesSpec with additional features.

    - Added get_files_by_checksum method to search files by MD5 checksum
    - Improved error handling and logging
    """

    def get_files_by_checksum(
        self,
        checksum_or_file: Union[str, Path],
        per_page: Optional[int] = None,
        page: Optional[int] = None,
        chunk_size: int = 8192,
        **kwargs
    ) -> Response:
        """
        Get files by their checksum. Accepts either a checksum string or a file
        path. If a file path is provided, calculates the MD5 checksum
        automatically.

        Args:
            checksum_or_file: Either an MD5 checksum string or a path to a file
            per_page: Optional number of items per page
            page: Optional page number
            chunk_size: Size of chunks when reading file (default 8192)
            **kwargs: Additional kwargs to pass to the request

        Returns:
            Response with Files model

        Raises:
            FileNotFoundError: If a file path is provided and file doesn't exist
            PermissionError: If there's no read permission for the provided file
            IOError: For other IO-related errors
            ValueError: If path is not a file or checksum format is invalid

        Examples:
            # Using a checksum string directly
            >>> client = ExtendedPythonikClient(app_id="...", auth_token="...")
            >>> response = client.files().get_files_by_checksum(
            ...     "d41d8cd98f00b204e9800998ecf8427e"
            ... )

            # Using a file path
            >>> response = client.files().get_files_by_checksum(
            ...     "path/to/your/file.txt"
            ... )
        """
        if isinstance(checksum_or_file, (str, Path)):
            try:
                path = Path(checksum_or_file)
                if path.exists():
                    checksum = calculate_md5(path, chunk_size=chunk_size)
                else:
                    checksum = str(checksum_or_file)
            except (TypeError, ValueError):
                checksum = str(checksum_or_file)
        else:
            raise TypeError("checksum_or_file must be a string or Path object")

        if not all(c in '0123456789abcdefABCDEF'
                   for c in checksum) or len(checksum) != 32:
            raise ValueError("Invalid MD5 checksum format")

        params: Dict[str, Any] = {}
        if per_page is not None:
            params['per_page'] = per_page
        if page is not None:
            params['page'] = page

        kwargs_params = kwargs.pop('params', {})
        params.update(kwargs_params)

        kwargs['params'] = params

        response = self._get(f"files/checksum/{checksum}/", **kwargs)

        return self.parse_response(response, Files)
