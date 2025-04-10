"""
Tests for the FileIngestRecipe class.
"""

import unittest
from unittest.mock import MagicMock, patch

from src.pythonikext.exceptions import GeneralException
from src.pythonikext.recipes.file_ingest import FileIngestRecipe, _load_metadata


class TestFileIngestRecipe(unittest.TestCase):
    """Test suite for the FileIngestRecipe class."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = MagicMock()
        self.client.session = MagicMock()
        self.client.base_url = "https://app.iconik.io"

        # Mock the storage settings response
        storage_obj = MagicMock()
        storage_obj.settings = {
            'mount_point': '/mnt/storage',
            'scan_include': ['*.mp4', '*.mov'],
            'scan_ignore': ['*tmp*', 're:/\\.backup/'],
            'transcode_include': ['*.mp4'],
            'transcode_ignore': ['*proxy*'],
            'title_includes_extension': True,
            'aggregate_identical_files': False,
            'enable_collection_directory_mapping': True
        }

        storage_response = MagicMock()
        storage_response.response.ok = True
        storage_response.data = storage_obj

        self.client.files().get_storage.return_value = storage_response

        # Create recipe instance
        self.recipe = FileIngestRecipe(
            client=self.client,
            storage_id="test-storage-id",
            default_view_id="test-view-id",
            mount_mapping="/local/path:/remote/path"
        )

        # Set up some test data
        self.test_storage_id = "test-storage-id"
        self.test_asset_id = "test-asset-id"
        self.test_format_id = "test-format-id"
        self.test_file_set_id = "test-file-set-id"
        self.test_file_id = "test-file-id"
        self.test_file_path = "/local/path/test/video.mp4"
        self.test_file_name = "video.mp4"
        self.test_directory_path = "test"
        self.test_checksum = "d41d8cd98f00b204e9800998ecf8427e"

    def test_init(self):
        """Test initialization of the recipe."""
        self.assertEqual(self.recipe.client, self.client)
        self.assertEqual(self.recipe.storage_id, "test-storage-id")
        self.assertEqual(self.recipe.default_view_id, "test-view-id")
        self.assertIsNone(self.recipe._storage_settings)
        self.assertIsNone(self.recipe._storage_mount_point)
        self.assertEqual(self.recipe.local_path, "/local/path")
        self.assertEqual(self.recipe.remote_path, "/remote/path")

    def test_storage_settings_property(self):
        """Test the storage_settings property."""
        # First access should fetch the settings
        settings = self.recipe.storage_settings
        self.assertEqual(settings['mount_point'], '/mnt/storage')
        self.assertEqual(settings['scan_include'], ['*.mp4', '*.mov'])

        # Second access should use the cached value
        self.client.files().get_storage.reset_mock()
        _ = self.recipe.storage_settings
        self.client.files().get_storage.assert_not_called()

    def test_storage_settings_error_handling(self):
        """Test error handling in the storage_settings property."""
        # Reset the recipe to create a fresh instance
        self.recipe = FileIngestRecipe(
            client=self.client, storage_id="test-storage-id"
        )

        # Mock an error response
        error_response = MagicMock()
        error_response.response.ok = False
        error_response.response.text = "Error fetching storage"
        self.client.files().get_storage.return_value = error_response

        # Should return an empty dict on error
        self.assertEqual(self.recipe.storage_settings, {})

    def test_storage_settings_exception_handling(self):
        """Test exception handling in the storage_settings property."""
        # Reset the recipe to create a fresh instance
        self.recipe = FileIngestRecipe(
            client=self.client, storage_id="test-storage-id"
        )

        # Mock an exception
        self.client.files().get_storage.side_effect = Exception("API error")

        # Should return an empty dict on exception
        self.assertEqual(self.recipe.storage_settings, {})

    def test_mount_point_property(self):
        """Test the mount_point property."""
        self.assertEqual(self.recipe.mount_point, '/mnt/storage')

        # Change the setting and verify it's reflected
        storage_obj = MagicMock()
        storage_obj.settings = {'mount_point': '/new/mount'}

        storage_response = MagicMock()
        storage_response.response.ok = True
        storage_response.data = storage_obj

        self.client.files().get_storage.return_value = storage_response

        # Reset cached values
        self.recipe._storage_settings = None
        self.recipe._storage_mount_point = None

        self.assertEqual(self.recipe.mount_point, '/new/mount')

    def test_map_file_path_with_mapping(self):
        """Test map_file_path with mount mapping."""
        # With mapping that matches
        mapped_path = self.recipe.map_file_path(self.test_file_path)
        self.assertEqual(mapped_path, "/remote/path/test/video.mp4")

        # With mapping that doesn't match
        unmapped_path = self.recipe.map_file_path("/other/path/file.mp4")
        self.assertEqual(unmapped_path, "/other/path/file.mp4")

    def test_map_file_path_without_mapping(self):
        """Test map_file_path without mount mapping."""
        # Reset the recipe to remove mapping
        self.recipe = FileIngestRecipe(
            client=self.client, storage_id="test-storage-id"
        )

        # Should return the original path
        mapped_path = self.recipe.map_file_path(self.test_file_path)
        self.assertEqual(mapped_path, self.test_file_path)

    @patch('src.pythonikext.recipes.file_ingest.calculate_md5')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.path.basename')
    @patch('os.path.dirname')
    @patch('os.path.splitext')
    @patch('mimetypes.guess_type')
    @patch('re.search')
    @patch('fnmatch.fnmatch')
    def test_check_file_validity_success(
        self, mock_fnmatch, mock_re_search, mock_guess_type, mock_splitext,
        mock_dirname, mock_basename, mock_getsize, mock_exists,
        mock_calculate_md5
    ):
        """Test _check_file_validity with valid file."""
        # Set up mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 1024
        mock_basename.return_value = self.test_file_name
        mock_dirname.return_value = "/remote/path/test"
        mock_splitext.return_value = ("video", ".mp4")
        mock_guess_type.return_value = ("video/mp4", None)
        mock_calculate_md5.return_value = self.test_checksum

        # Set up fnmatch to only match include patterns but not ignore patterns
        def fnmatch_side_effect(path, pattern):
            if pattern in ['*.mp4', '*.mov']:  # scan_include patterns
                return True
            return False  # Don't match scan_ignore patterns

        mock_fnmatch.side_effect = fnmatch_side_effect
        mock_re_search.return_value = False  # Don't match regex patterns

        # Mock map_file_path
        with patch.object(
            self.recipe,
            'map_file_path',
            return_value="/remote/path/test/video.mp4"
        ):
            # Mock mount_point to allow directory path stripping
            self.recipe._storage_mount_point = "/remote/path"

            # Call the method
            result = self.recipe._check_file_validity(self.test_file_path)

            # Verify the result
            self.assertEqual(result["file_path"], self.test_file_path)
            self.assertEqual(result["title"], self.test_file_name)
            self.assertEqual(result["size"], 1024)
            self.assertEqual(result["file_name"], self.test_file_name)
            self.assertEqual(result["file_stem"], "video")
            self.assertEqual(result["file_extension"], ".mp4")
            self.assertEqual(result["mime_type"], "video/mp4")
            self.assertEqual(result["directory_path"], "test")
            self.assertEqual(result["file_checksum"], self.test_checksum)
            self.assertEqual(
                result["path_mapping"], "/remote/path/test/video.mp4"
            )
            self.assertTrue(result["file_exists"])

    @patch('os.path.exists')
    def test_check_file_validity_offline(self, mock_exists):
        """Test _check_file_validity with offline file."""
        # Set up mocks
        mock_exists.return_value = False

        # Call the method with allow_offline=True
        result = self.recipe._check_file_validity(
            self.test_file_path, md5sum=self.test_checksum, allow_offline=True
        )

        # Verify the result
        self.assertEqual(result["file_path"], self.test_file_path)
        self.assertEqual(result["size"], 0)
        self.assertEqual(result["file_checksum"], self.test_checksum)
        self.assertFalse(result["file_exists"])

    @patch('os.path.exists')
    def test_check_file_validity_offline_not_allowed(self, mock_exists):
        """Test _check_file_validity with offline file not allowed."""
        # Set up mocks
        mock_exists.return_value = False

        # Should raise FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            self.recipe._check_file_validity(self.test_file_path)

    @patch('src.pythonikext.recipes.file_ingest.calculate_md5')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.path.basename')
    @patch('os.path.dirname')
    @patch('os.path.splitext')
    @patch('mimetypes.guess_type')
    @patch('re.search')
    @patch('fnmatch.fnmatch')
    def test_check_file_validity_scan_include_match(
        self, mock_fnmatch, mock_re_search, mock_guess_type, mock_splitext,
        mock_dirname, mock_basename, mock_getsize, mock_exists,
        mock_calculate_md5
    ):
        """Test _check_file_validity with scan_include matching."""
        # Set up mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 1024
        mock_basename.return_value = self.test_file_name
        mock_dirname.return_value = "/remote/path/test"
        mock_splitext.return_value = ("video", ".mp4")
        mock_guess_type.return_value = ("video/mp4", None)
        mock_calculate_md5.return_value = self.test_checksum

        # Set up fnmatch to only match include patterns but not ignore patterns
        def fnmatch_side_effect(path, pattern):
            if pattern in ['*.mp4', '*.mov']:  # scan_include patterns
                return True
            return False  # Don't match scan_ignore patterns

        mock_fnmatch.side_effect = fnmatch_side_effect
        mock_re_search.return_value = False  # Don't match regex patterns

        # Mock map_file_path
        with patch.object(
            self.recipe,
            'map_file_path',
            return_value="/remote/path/test/video.mp4"
        ):
            # Call the method
            result = self.recipe._check_file_validity(self.test_file_path)

            # Verify the result
            self.assertEqual(result["file_path"], self.test_file_path)
            self.assertEqual(result["file_checksum"], self.test_checksum)

    @patch('src.pythonikext.recipes.file_ingest.calculate_md5')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.path.basename')
    @patch('os.path.dirname')
    @patch('os.path.splitext')
    @patch('mimetypes.guess_type')
    @patch('re.search')
    @patch('fnmatch.fnmatch')
    def test_check_file_validity_scan_include_no_match(
        self, mock_fnmatch, mock_re_search, mock_guess_type, mock_splitext,
        mock_dirname, mock_basename, mock_getsize, mock_exists,
        mock_calculate_md5
    ):
        """Test _check_file_validity with scan_include not matching."""
        # Set up mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 1024
        mock_basename.return_value = self.test_file_name
        mock_dirname.return_value = "/remote/path/test"
        mock_splitext.return_value = ("video", ".mp4")
        mock_guess_type.return_value = ("video/mp4", None)
        mock_calculate_md5.return_value = self.test_checksum
        mock_fnmatch.return_value = False  # Don't match scan_include pattern
        mock_re_search.return_value = False  # Don't match regex pattern

        # Should raise ValueError for not matching scan_include
        with self.assertRaises(ValueError):
            self.recipe._check_file_validity(self.test_file_path)

    @patch('src.pythonikext.recipes.file_ingest.calculate_md5')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.path.basename')
    @patch('os.path.dirname')
    @patch('os.path.splitext')
    @patch('mimetypes.guess_type')
    @patch('re.search')
    @patch('fnmatch.fnmatch')
    def test_check_file_validity_scan_ignore_match(
        self, mock_fnmatch, mock_re_search, mock_guess_type, mock_splitext,
        mock_dirname, mock_basename, mock_getsize, mock_exists,
        mock_calculate_md5
    ):
        """Test _check_file_validity with scan_ignore matching."""
        # Set up mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 1024
        mock_basename.return_value = "video.tmp.mp4"  # Matches scan_ignore
        mock_dirname.return_value = "/remote/path/test"
        mock_splitext.return_value = ("video.tmp", ".mp4")
        mock_guess_type.return_value = ("video/mp4", None)
        mock_calculate_md5.return_value = self.test_checksum

        # Set up fnmatch to match both include and ignore patterns
        def fnmatch_side_effect(path, pattern):
            if pattern == "*.mp4":  # scan_include pattern
                return True
            if pattern == "*tmp*":  # scan_ignore pattern
                return True
            return False

        mock_fnmatch.side_effect = fnmatch_side_effect

        # Should raise ValueError for matching scan_ignore
        with self.assertRaises(ValueError):
            self.recipe._check_file_validity("/remote/path/test/video.tmp.mp4")

    def test_resolve_external_id_from_filename(self):
        """Test _resolve_external_id with filename_is_external_id=True."""
        # Set up storage settings
        self.recipe._storage_settings = {'filename_is_external_id': True}

        # Set up file info
        file_info = {
            "file_path": self.test_file_path,
            "file_name": self.test_file_name
        }

        # Call the method
        result = self.recipe._resolve_external_id(file_info)

        # Verify the result
        self.assertEqual(result, self.test_file_name)

    def test_resolve_external_id_from_path(self):
        """Test _resolve_external_id with filename_is_external_id=False."""
        # Set up storage settings
        self.recipe._storage_settings = {'filename_is_external_id': False}

        # Set up file info
        file_info = {
            "file_path": self.test_file_path,
            "file_name": self.test_file_name
        }

        # Call the method
        result = self.recipe._resolve_external_id(file_info)

        # Verify the result
        self.assertEqual(result, self.test_file_path)

    def test_merge_metadata_both(self):
        """Test _merge_metadata with both metadata sources."""
        metadata = {"title": "Test Title", "description": "Test Description"}
        sidecar_metadata = {
            "keywords": ["test", "video"],
            "created_date": "2025-01-01"
        }

        # Call the method
        result = self.recipe._merge_metadata(metadata, sidecar_metadata)

        # Verify the result
        self.assertEqual(result["title"], "Test Title")
        self.assertEqual(result["description"], "Test Description")
        self.assertEqual(result["keywords"], ["test", "video"])
        self.assertEqual(result["created_date"], "2025-01-01")

    def test_merge_metadata_only_provided(self):
        """Test _merge_metadata with only provided metadata."""
        metadata = {"title": "Test Title", "description": "Test Description"}

        # Call the method
        result = self.recipe._merge_metadata(metadata, None)

        # Verify the result
        self.assertEqual(result, metadata)

    def test_merge_metadata_only_sidecar(self):
        """Test _merge_metadata with only sidecar metadata."""
        sidecar_metadata = {
            "keywords": ["test", "video"],
            "created_date": "2025-01-01"
        }

        # Call the method
        result = self.recipe._merge_metadata(None, sidecar_metadata)

        # Verify the result
        self.assertEqual(result, sidecar_metadata)

    def test_merge_metadata_none(self):
        """Test _merge_metadata with no metadata."""
        # Call the method
        result = self.recipe._merge_metadata(None, None)

        # Verify the result
        self.assertIsNone(result)

    def test_find_existing_asset_by_external_id(self):
        """Test _find_existing_asset with existing asset by external ID."""
        # Mock the asset search response
        asset = MagicMock()
        asset.id = self.test_asset_id

        asset_data = MagicMock()
        asset_data.objects = [asset]

        asset_response = MagicMock()
        asset_response.response.ok = True
        asset_response.data = asset_data

        # Mock API calls
        self.client.assets(
        ).gen_url.return_value = "https://app.iconik.io/assets"

        with patch(
            'src.pythonikext.recipes.file_ingest.AssetSpec.parse_response',
            return_value=asset_response
        ):
            # Mock has_been_deleted to return False
            with patch.object(
                self.recipe, 'has_been_deleted', return_value=False
            ):
                # Call the method
                asset_id, asset_existed = self.recipe._find_existing_asset(
                    "test_external_id", {"file_checksum": self.test_checksum}
                )

                # Verify the result
                self.assertEqual(asset_id, self.test_asset_id)
                self.assertTrue(asset_existed)

    def test_find_existing_asset_by_checksum(self):
        """Test _find_existing_asset with existing asset by checksum."""
        # Enable checksum-based lookup
        self.recipe._storage_settings = {'aggregate_identical_files': True}

        # Mock the file lookup by checksum
        file_obj = MagicMock()
        file_obj.asset_id = self.test_asset_id
        file_obj.storage_id = self.test_storage_id

        with patch.object(
            self.recipe, 'check_for_duplicate_files', return_value=[file_obj]
        ):
            # Mock has_been_deleted to return False
            with patch.object(
                self.recipe, 'has_been_deleted', return_value=False
            ):
                # Call the method
                asset_id, asset_existed = self.recipe._find_existing_asset(
                    "test_external_id", {"file_checksum": self.test_checksum}
                )

                # Verify the result
                self.assertEqual(asset_id, self.test_asset_id)
                self.assertTrue(asset_existed)

    def test_find_existing_asset_not_found(self):
        """Test _find_existing_asset with no existing asset."""
        # Mock empty search results
        asset_data = MagicMock()
        asset_data.objects = []

        asset_response = MagicMock()
        asset_response.response.ok = True
        asset_response.data = asset_data

        # Mock API calls
        self.client.assets(
        ).gen_url.return_value = "https://app.iconik.io/assets"

        with patch(
            'src.pythonikext.recipes.file_ingest.AssetSpec.parse_response',
            return_value=asset_response
        ):
            # Mock check_for_duplicate_files to return empty list
            with patch.object(
                self.recipe, 'check_for_duplicate_files', return_value=[]
            ):
                # Call the method
                asset_id, asset_existed = self.recipe._find_existing_asset(
                    "test_external_id", {"file_checksum": self.test_checksum}
                )

                # Verify the result
                self.assertIsNone(asset_id)
                self.assertFalse(asset_existed)

    def test_create_new_asset_success(self):
        """Test _create_new_asset with success."""
        # Mock the asset creation response
        asset_data = MagicMock()
        asset_data.id = self.test_asset_id

        asset_response = MagicMock()
        asset_response.response.ok = True
        asset_response.data = asset_data

        # Mock API calls
        self.client.assets().create.return_value = asset_response

        # Mock _apply_acls
        with patch.object(self.recipe, '_apply_acls', return_value=True):
            # Call the method
            asset_id = self.recipe._create_new_asset({
                "title": self.test_file_name
            }, "test_external_id")

            # Verify the result
            self.assertEqual(asset_id, self.test_asset_id)

            # Verify the correct model was used
            self.client.assets().create.assert_called_once()
            args, kwargs = self.client.assets().create.call_args

            self.assertEqual(kwargs['body'].title, self.test_file_name)
            self.assertEqual(kwargs['body'].external_id, "test_external_id")

    def test_create_new_asset_error(self):
        """Test _create_new_asset with error response."""
        # Mock the asset creation response
        asset_response = MagicMock()
        asset_response.response.ok = False
        asset_response.response.text = "Error creating asset"

        # Mock API calls
        self.client.assets().create.return_value = asset_response

        # Should raise GeneralException
        with self.assertRaises(GeneralException):
            self.recipe._create_new_asset({"title": self.test_file_name},
                                          "test_external_id")

    def test_ensure_format_exists(self):
        """Test _ensure_format when format exists."""
        # Mock the format search response
        format_obj = MagicMock()
        format_obj.id = self.test_format_id
        format_obj.name = "ORIGINAL"
        format_obj.status = "ACTIVE"

        format_data = MagicMock()
        format_data.objects = [format_obj]

        format_response = MagicMock()
        format_response.response.ok = True
        format_response.data = format_data

        # Mock API calls
        self.client.files().get_asset_formats.return_value = format_response

        # Mock has_been_deleted to return False
        with patch.object(self.recipe, 'has_been_deleted', return_value=False):
            # Call the method
            format_id, format_existed = self.recipe._ensure_format(
                self.test_asset_id
            )

            # Verify the result
            self.assertEqual(format_id, self.test_format_id)
            self.assertTrue(format_existed)

            # Verify no creation was attempted
            self.client.files().create_asset_format.assert_not_called()

    def test_ensure_format_creates(self):
        """Test _ensure_format when format needs to be created."""
        # Mock empty format search response
        format_data = MagicMock()
        format_data.objects = []

        format_response = MagicMock()
        format_response.response.ok = True
        format_response.data = format_data

        # Mock format creation response
        create_data = MagicMock()
        create_data.id = self.test_format_id

        create_response = MagicMock()
        create_response.response.ok = True
        create_response.data = create_data

        # Mock API calls
        self.client.files().get_asset_formats.return_value = format_response
        self.client.files().create_asset_format.return_value = create_response

        # Mock has_been_deleted to return False
        with patch.object(self.recipe, 'has_been_deleted', return_value=False):
            # Call the method
            format_id, format_existed = self.recipe._ensure_format(
                self.test_asset_id
            )

            # Verify the result
            self.assertEqual(format_id, self.test_format_id)
            self.assertFalse(format_existed)

            # Verify the correct model was used
            self.client.files().create_asset_format.assert_called_once()
            args, kwargs = self.client.files().create_asset_format.call_args

            self.assertEqual(args[0], self.test_asset_id)
            self.assertEqual(kwargs['body'].name, "ORIGINAL")
            self.assertEqual(kwargs['body'].storage_methods, ["FILE"])
            self.assertTrue(kwargs['body'].is_online)

    def test_ensure_format_create_error(self):
        """Test _ensure_format when format creation fails."""
        # Mock empty format search response
        format_data = MagicMock()
        format_data.objects = []

        format_response = MagicMock()
        format_response.response.ok = True
        format_response.data = format_data

        # Mock format creation error response
        create_response = MagicMock()
        create_response.response.ok = False
        create_response.response.text = "Error creating format"

        # Mock API calls
        self.client.files().get_asset_formats.return_value = format_response
        self.client.files().create_asset_format.return_value = create_response

        # Mock has_been_deleted to return False
        with patch.object(self.recipe, 'has_been_deleted', return_value=False):
            # Should raise GeneralException
            with self.assertRaises(GeneralException):
                self.recipe._ensure_format(self.test_asset_id)

    def test_ensure_file_set_exists(self):
        """Test _ensure_file_set when file set exists."""
        # Mock the file set search response
        file_set = MagicMock()
        file_set.id = self.test_file_set_id
        file_set.storage_id = self.test_storage_id
        file_set.format_id = self.test_format_id
        file_set.base_dir = self.test_directory_path
        file_set.status = "ACTIVE"

        file_set_data = MagicMock()
        file_set_data.objects = [file_set]

        file_set_response = MagicMock()
        file_set_response.response.ok = True
        file_set_response.data = file_set_data

        # Mock API calls
        self.client.files().get_asset_filesets.return_value = file_set_response

        # Mock has_been_deleted to return False
        with patch.object(self.recipe, 'has_been_deleted', return_value=False):
            # Call the method
            file_set_id, file_set_existed = self.recipe._ensure_file_set(
                self.test_asset_id, self.test_format_id, {
                    "directory_path": self.test_directory_path,
                    "file_name": self.test_file_name
                }
            )

            # Verify the result
            self.assertEqual(file_set_id, self.test_file_set_id)
            self.assertTrue(file_set_existed)

            # Verify no creation was attempted
            self.client.files().create_asset_file_sets.assert_not_called()

    def test_load_metadata_from_string(self):
        """Test _load_metadata from a JSON string."""
        # Valid JSON string
        metadata_str = '{"title": "Test Title", "description": "Test Description"}'
        result = _load_metadata(metadata_str)

        self.assertEqual(result["title"], "Test Title")
        self.assertEqual(result["description"], "Test Description")

        # Invalid JSON string
        with self.assertRaises(ValueError):
            _load_metadata('{invalid json}')

    @patch('os.path.exists')
    def test_load_metadata_from_file(self, mock_exists):
        """Test _load_metadata from a file."""
        # Set up mocks
        mock_exists.return_value = True

        # Mock open to return file with valid JSON
        mock_open = unittest.mock.mock_open(
            read_data='{"title": "Test Title", "description": "Test Description"}'
        )

        with patch('builtins.open', mock_open):
            # Call with file path
            result = _load_metadata('@/path/to/metadata.json')

            # Verify the result
            self.assertEqual(result["title"], "Test Title")
            self.assertEqual(result["description"], "Test Description")

            # Verify file was opened correctly
            mock_open.assert_called_once_with(
                '/path/to/metadata.json', 'r', encoding='utf-8'
            )

    @patch('os.path.exists')
    def test_load_metadata_file_not_found(self, mock_exists):
        """Test _load_metadata with non-existent file."""
        # Set up mocks
        mock_exists.return_value = False

        # Should return None for non-existent file
        result = _load_metadata('@/path/to/nonexistent.json')

        self.assertIsNone(result)

    @patch('os.path.exists')
    def test_load_metadata_from_file_invalid_json(self, mock_exists):
        """Test _load_metadata from a file with invalid JSON."""
        # Set up mocks
        mock_exists.return_value = True

        # Mock open to return file with invalid JSON
        mock_open = unittest.mock.mock_open(read_data='{invalid json}')

        with patch('builtins.open', mock_open):
            # Should raise ValueError for invalid JSON
            with self.assertRaises(ValueError):
                _load_metadata('@/path/to/metadata.json')

    def test_has_been_deleted_asset(self):
        """Test has_been_deleted for asset."""
        # Mock the asset get response
        asset_data = MagicMock()
        asset_data.status = "DELETED"

        asset_response = MagicMock()
        asset_response.response.ok = True
        asset_response.data = asset_data

        # Mock API calls
        self.client.assets().get.return_value = asset_response

        # Call the method
        result = self.recipe.has_been_deleted(self.test_asset_id, "assets")

        # Verify the result
        self.assertTrue(result)

        # Test with active asset
        asset_data.status = "ACTIVE"
        result = self.recipe.has_been_deleted(self.test_asset_id, "assets")
        self.assertFalse(result)

    def test_has_been_deleted_unsupported_type(self):
        """Test has_been_deleted with unsupported object type."""
        # Should raise ValueError
        with self.assertRaises(ValueError):
            self.recipe.has_been_deleted(self.test_asset_id, "unsupported_type")

    def test_create_asset_integration(self):
        """Test create_asset method with mocked components."""
        # Set up the mocks for file existence and validity
        with patch.object(
            self.recipe,
            '_check_file_validity',
            return_value={
                "file_path": self.test_file_path,
                "title": self.test_file_name,
                "size": 1024,
                "file_name": self.test_file_name,
                "file_stem": "video",
                "file_extension": ".mp4",
                "mime_type": "video/mp4",
                "directory_path": self.test_directory_path,
                "file_checksum": self.test_checksum,
                "path_mapping": "/remote/path/test/video.mp4",
                "file_exists": True
            }
        ):
            # Mock _find_existing_asset to return no existing asset
            with patch.object(
                self.recipe, '_find_existing_asset', return_value=(None, False)
            ):
                # Mock _create_new_asset to return a new asset ID
                with patch.object(
                    self.recipe,
                    '_create_new_asset',
                    return_value=self.test_asset_id
                ):
                    # Mock _ensure_format
                    with patch.object(
                        self.recipe,
                        '_ensure_format',
                        return_value=(self.test_format_id, False)
                    ):
                        # Mock _ensure_file_set
                        with patch.object(
                            self.recipe,
                            '_ensure_file_set',
                            return_value=(self.test_file_set_id, False)
                        ):
                            # Mock _ensure_file
                            with patch.object(
                                self.recipe,
                                '_ensure_file',
                                return_value=(self.test_file_id, False)
                            ):
                                # Mock _trigger_transcoding
                                with patch.object(
                                    self.recipe,
                                    '_trigger_transcoding',
                                    return_value={"mediainfo_job": True}
                                ):
                                    # Mock _create_history_record
                                    with patch.object(
                                        self.recipe,
                                        '_create_history_record',
                                        return_value={"history_created": True}
                                    ):
                                        # Call the method
                                        result = self.recipe.create_asset(
                                            file_path=self.test_file_path
                                        )

                                        # Verify the result
                                        self.assertEqual(
                                            result["asset_id"],
                                            self.test_asset_id
                                        )
                                        self.assertEqual(
                                            result["format_id"],
                                            self.test_format_id
                                        )
                                        self.assertEqual(
                                            result["file_set_id"],
                                            self.test_file_set_id
                                        )
                                        self.assertEqual(
                                            result["file_id"], self.test_file_id
                                        )
                                        self.assertTrue(result["mediainfo_job"])
                                        self.assertTrue(
                                            result["history_created"]
                                        )


if __name__ == '__main__':
    unittest.main()
