"""Tests for the ExtendedFilesSpec class."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.pythonikext import calculate_md5
from src.pythonikext.specs.files import ExtendedFilesSpec


class TestExtendedFilesSpec(unittest.TestCase):
    """Test suite for the ExtendedFilesSpec class."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = MagicMock()
        self.client.session = MagicMock()
        self.client.timeout = 10
        self.client.base_url = "https://app.iconik.io"

        self.files_spec = ExtendedFilesSpec(
            self.client.session, self.client.timeout, self.client.base_url
        )

    @patch('src.pythonikext.specs.files.calculate_md5')
    @patch('src.pythonikext.specs.files.Path')
    def test_get_files_by_checksum_with_file_path(
        self, mock_path, mock_calculate_md5
    ):
        """Test get_files_by_checksum with a file path."""
        # Arrange
        file_path = "path/to/file.txt"
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path.return_value = mock_path_instance

        expected_checksum = "d41d8cd98f00b204e9800998ecf8427e"
        mock_calculate_md5.return_value = expected_checksum

        self.files_spec._get = MagicMock()
        self.files_spec.parse_response = MagicMock()

        # Act
        self.files_spec.get_files_by_checksum(file_path)

        # Assert
        mock_path.assert_called_once_with(file_path)
        mock_path_instance.exists.assert_called_once()
        mock_calculate_md5.assert_called_once_with(
            mock_path_instance, chunk_size=8192
        )
        self.files_spec._get.assert_called_once_with(
            f"files/checksum/{expected_checksum}/", params={}
        )

    def test_get_files_by_checksum_with_checksum_string(self):
        """Test get_files_by_checksum with a checksum string."""
        # Arrange
        checksum = "d41d8cd98f00b204e9800998ecf8427e"

        self.files_spec._get = MagicMock()
        self.files_spec.parse_response = MagicMock()

        # Act
        self.files_spec.get_files_by_checksum(checksum)

        # Assert
        self.files_spec._get.assert_called_once_with(
            f"files/checksum/{checksum}/", params={}
        )

    def test_get_files_by_checksum_with_invalid_checksum(self):
        """Test get_files_by_checksum with an invalid checksum."""
        # Arrange
        invalid_checksum = "invalid_checksum"

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid MD5 checksum format"):
            self.files_spec.get_files_by_checksum(invalid_checksum)

    def test_calculate_md5_function(self):
        """Test the calculate_md5 utility function."""
        # This is a real test that creates a temporary file
        import tempfile

        # Create a temporary file with known content
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"hello world")
            temp_path = temp_file.name

        try:
            # Calculate MD5 of the file
            md5_hash = calculate_md5(temp_path)

            # Expected MD5 for "hello world"
            expected_md5 = "5eb63bbbe01eeed093cb22bb8f5acdc3"

            # Assert
            self.assertEqual(md5_hash, expected_md5)
        finally:
            # Clean up
            Path(temp_path).unlink()


if __name__ == '__main__':
    unittest.main()
