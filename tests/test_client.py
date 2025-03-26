"""Tests for the ExtendedPythonikClient class."""

import unittest
from unittest.mock import patch

from src.pythonikext import ExtendedPythonikClient
from src.pythonikext.specs.files import ExtendedFilesSpec


class TestExtendedPythonikClient(unittest.TestCase):
    """Test suite for the ExtendedPythonikClient class."""

    @patch('pythonik.client.Session')
    def test_files_returns_extended_spec(self, mock_session):
        """Test that files() returns an instance of ExtendedFilesSpec."""
        # Arrange
        client = ExtendedPythonikClient(
            app_id="test", auth_token="test", timeout=10
        )

        # Act
        result = client.files()

        # Assert
        self.assertIsInstance(result, ExtendedFilesSpec)


if __name__ == '__main__':
    unittest.main()
