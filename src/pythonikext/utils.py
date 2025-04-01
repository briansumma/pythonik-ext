"""Utility functions for the pythonikext package."""

import hashlib
import os
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import NoReturn, Union


@contextmanager
def suppress_stdout() -> NoReturn:
    """A context manager that redirects stdout to /dev/null."""
    with open(os.devnull, 'w') as fnull:  # pylint: disable=unspecified-encoding
        with redirect_stdout(fnull) as out:
            yield out


def calculate_md5(file_path: Union[str, Path], chunk_size: int = 8192) -> str:
    """
    Calculate MD5 checksum of a file by reading it in chunks.
    
    Args:
        file_path: Path to the file (string or Path object)
        chunk_size: Size of chunks to read (default 8192 bytes / 8KB)
        
    Returns:
        str: MD5 checksum as a hexadecimal string
        
    Raises:
        FileNotFoundError: If the file does not exist
        ValueError: If the path is not a file
        PermissionError: If permission is denied when accessing the file
        IOError: For other I/O errors
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    md5_hash = hashlib.md5()

    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                md5_hash.update(chunk)
    except PermissionError as e:
        raise PermissionError(
            f"Permission denied when reading file: {file_path}"
        ) from e
    except IOError as e:
        raise IOError(f"Error reading file {file_path}: {str(e)}") from e

    return md5_hash.hexdigest()
