"""
Tests for the CollectionDirectoryMappingRecipe class.
"""

import unittest
from unittest.mock import MagicMock, patch

from src.pythonikext.recipes.collection_directory_mapping import (
    CollectionDirectoryMappingRecipe,
)


class TestCollectionDirectoryMappingRecipe(unittest.TestCase):
    """Test suite for the CollectionDirectoryMappingRecipe class."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = MagicMock()
        self.client.session = MagicMock()
        self.client.base_url = "https://app.iconik.io"

        # Mock the storage settings response
        storage_obj = MagicMock()
        storage_obj.settings = {
            'enable_collection_directory_mapping': True,
            'mount_point': '/mnt/storage'
        }
        storage_obj.name = "Test Storage"

        storage_response = MagicMock()
        storage_response.response.ok = True
        storage_response.data = storage_obj

        self.client.files().get_storage.return_value = storage_response

        # Create recipe instance
        self.recipe = CollectionDirectoryMappingRecipe(
            client=self.client, storage_id="test-storage-id"
        )

        # Set up some test data
        self.test_storage_id = "test-storage-id"
        self.test_collection_id = "test-collection-id"
        self.test_path = "/mnt/storage/test/path"
        self.test_directory_name = "path"

    def test_init(self):
        """Test initialization of the recipe."""
        self.assertEqual(self.recipe.client, self.client)
        self.assertEqual(self.recipe.storage_id, "test-storage-id")
        self.assertIsNone(self.recipe.storage_root_path)
        self.assertIsNone(self.recipe._storage_settings)
        self.assertIsNone(self.recipe._storage_name)
        self.assertIsNone(self.recipe._storage_gateways_collection_id)
        self.assertIsNone(self.recipe._storage_root_collection_id)
        self.assertIsNone(self.recipe._mount_point)
        self.assertEqual(self.recipe._collection_cache, {})

    def test_storage_settings_property(self):
        """Test the storage_settings property."""
        # First access should fetch the settings
        settings = self.recipe.storage_settings
        self.assertEqual(settings['enable_collection_directory_mapping'], True)
        self.assertEqual(settings['mount_point'], '/mnt/storage')

        # Second access should use the cached value
        self.client.files().get_storage.reset_mock()
        _ = self.recipe.storage_settings
        self.client.files().get_storage.assert_not_called()

    def test_storage_settings_error_handling(self):
        """Test error handling in the storage_settings property."""
        # Reset the recipe to create a fresh instance
        self.recipe = CollectionDirectoryMappingRecipe(
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
        self.recipe = CollectionDirectoryMappingRecipe(
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
        storage_obj.settings = {
            'enable_collection_directory_mapping': True,
            'mount_point': '/new/mount'
        }
        storage_obj.name = "Test Storage"

        storage_response = MagicMock()
        storage_response.response.ok = True
        storage_response.data = storage_obj

        self.client.files().get_storage.return_value = storage_response

        # Reset cached values
        self.recipe._storage_settings = None
        self.recipe._mount_point = None

        self.assertEqual(self.recipe.mount_point, '/new/mount')

    def test_storage_name_property(self):
        """Test the storage_name property."""
        self.assertEqual(self.recipe.storage_name, "Test Storage")

        # Reset the recipe to create a fresh instance with no name
        self.recipe = CollectionDirectoryMappingRecipe(
            client=self.client, storage_id="test-storage-id"
        )

        # Mock a response with no name
        storage_obj = MagicMock()
        storage_obj.settings = {'enable_collection_directory_mapping': True}
        storage_obj.name = None

        storage_response = MagicMock()
        storage_response.response.ok = True
        storage_response.data = storage_obj

        self.client.files().get_storage.return_value = storage_response

        # Should return a default name with the storage ID
        self.assertEqual(self.recipe.storage_name, "Storage test-storage-id")

    def test_is_mapping_enabled(self):
        """Test the _is_mapping_enabled method."""
        # Should be enabled based on our fixture setup
        self.assertTrue(self.recipe._is_mapping_enabled())

        # Disable mapping and check again
        self.recipe._storage_settings = {
            'enable_collection_directory_mapping': False
        }
        self.assertFalse(self.recipe._is_mapping_enabled())

        # Test with missing setting
        self.recipe._storage_settings = {}
        self.assertFalse(self.recipe._is_mapping_enabled())

    @patch('src.pythonikext.recipes.collection_directory_mapping.get_attribute')
    def test_get_storage_gateways_collection_success(self, mock_get_attribute):
        """Test the _get_storage_gateways_collection method with success."""
        # Mock the collection search response
        collection = MagicMock()
        # Set the mock to return our test value when get_attribute is called
        mock_get_attribute.return_value = self.test_collection_id

        collection_data = MagicMock()
        collection_data.objects = [collection]

        collection_response = MagicMock()
        collection_response.response.ok = True
        collection_response.data = collection_data

        self.client.session.get.return_value = MagicMock()
        self.client.assets(
        ).gen_url.return_value = "https://app.iconik.io/collections"

        # Mock the parse_response method
        with patch(
            'src.pythonikext.recipes.collection_directory_mapping.CollectionSpec.parse_response',
            return_value=collection_response
        ):
            # Call the method
            result = self.recipe._get_storage_gateways_collection()

            # Verify the result
            self.assertEqual(result, self.test_collection_id)

            # Verify the search parameters
            self.client.assets().gen_url.assert_called_with("collections")
            self.client.session.get.assert_called_once()

            # Verify the collection ID was cached
            self.assertEqual(
                self.recipe._storage_gateways_collection_id,
                self.test_collection_id
            )

    def test_get_storage_gateways_collection_not_found(self):
        """Test the _get_storage_gateways_collection method when collection not found."""
        # Mock empty search results
        collection_data = MagicMock()
        collection_data.objects = []

        collection_response = MagicMock()
        collection_response.response.ok = True
        collection_response.data = collection_data

        self.client.session.get.return_value = MagicMock()
        self.client.assets(
        ).gen_url.return_value = "https://app.iconik.io/collections"

        # Mock the parse_response method
        with patch(
            'src.pythonikext.recipes.collection_directory_mapping.CollectionSpec.parse_response',
            return_value=collection_response
        ):
            # Call the method
            result = self.recipe._get_storage_gateways_collection()

            # Verify the result
            self.assertIsNone(result)

    def test_get_storage_gateways_collection_error(self):
        """Test the _get_storage_gateways_collection method with API error."""
        collection_response = MagicMock()
        collection_response.response.ok = False

        self.client.session.get.return_value = MagicMock()
        self.client.assets(
        ).gen_url.return_value = "https://app.iconik.io/collections"

        # Mock the parse_response method
        with patch(
            'src.pythonikext.recipes.collection_directory_mapping.CollectionSpec.parse_response',
            return_value=collection_response
        ):
            # Call the method
            result = self.recipe._get_storage_gateways_collection()

            # Verify the result
            self.assertIsNone(result)

    def test_get_storage_gateways_collection_exception(self):
        """Test the _get_storage_gateways_collection method with exception."""
        self.client.assets().gen_url.side_effect = Exception("API error")

        # Call the method
        result = self.recipe._get_storage_gateways_collection()

        # Verify the result
        self.assertIsNone(result)

    def test_get_storage_gateways_collection_cached(self):
        """Test that _get_storage_gateways_collection uses cached value."""
        # Set the cached value
        self.recipe._storage_gateways_collection_id = self.test_collection_id

        # Call the method
        result = self.recipe._get_storage_gateways_collection()

        # Verify the cached value was returned
        self.assertEqual(result, self.test_collection_id)

        # Verify no API calls were made
        self.client.assets().gen_url.assert_not_called()
        self.client.session.get.assert_not_called()

    @patch('src.pythonikext.recipes.collection_directory_mapping.get_attribute')
    def test_get_storage_root_collection_success(self, mock_get_attribute):
        """Test the _get_storage_root_collection method with success."""
        # Set up the storage gateways ID
        self.recipe._storage_gateways_collection_id = "storage-gateways-id"

        # Mock the collection search response
        collection = MagicMock()
        mock_get_attribute.return_value = self.test_collection_id

        collection_data = MagicMock()
        collection_data.objects = [collection]

        contents_response = MagicMock()
        contents_response.response.ok = True
        contents_response.data = collection_data

        self.client.session.get.return_value = MagicMock()
        self.client.collections(
        ).gen_url.return_value = "https://app.iconik.io/collections/contents"

        # Mock the parse_response method
        with patch(
            'src.pythonikext.recipes.collection_directory_mapping.AssetSpec.parse_response',
            return_value=contents_response
        ):
            # Call the method
            result = self.recipe._get_storage_root_collection()

            # Verify the result
            self.assertEqual(result, self.test_collection_id)

            # Verify the collection ID was cached
            self.assertEqual(
                self.recipe._storage_root_collection_id, self.test_collection_id
            )

            # Verify it was added to the collection cache
            expected_external_id = f"{self.test_storage_id}/"
            self.assertEqual(
                self.recipe._collection_cache[expected_external_id],
                self.test_collection_id
            )

    def test_get_storage_root_collection_no_gateways(self):
        """Test _get_storage_root_collection with no storage gateways."""
        # Mock _get_storage_gateways_collection to return None
        with patch.object(
            self.recipe, '_get_storage_gateways_collection', return_value=None
        ):
            # Call the method
            result = self.recipe._get_storage_root_collection()

            # Verify the result
            self.assertIsNone(result)

    def test_create_storage_root_collection_success(self):
        """Test the _create_storage_root_collection method with success."""
        # Set up the storage gateways ID
        with patch.object(
            self.recipe,
            '_get_storage_gateways_collection',
            return_value="storage-gateways-id"
        ):
            # Mock the collection creation response
            collection_data = MagicMock()
            collection_data.id = self.test_collection_id

            collection_response = MagicMock()
            collection_response.response.ok = True
            collection_response.data = collection_data

            self.client.collections().create.return_value = collection_response

            # Call the method
            result = self.recipe._create_storage_root_collection()

            # Verify the result
            self.assertEqual(result, self.test_collection_id)

            # Verify the collection ID was cached
            self.assertEqual(
                self.recipe._storage_root_collection_id, self.test_collection_id
            )

            # Verify it was added to the collection cache
            expected_external_id = f"{self.test_storage_id}/"
            self.assertEqual(
                self.recipe._collection_cache[expected_external_id],
                self.test_collection_id
            )

            # Verify the correct model was used
            self.client.collections().create.assert_called_once()
            args, kwargs = self.client.collections().create.call_args

            self.assertEqual(kwargs['body']['title'], self.recipe.storage_name)
            self.assertEqual(kwargs['body']['parent_id'], "storage-gateways-id")
            self.assertEqual(
                kwargs['body']['external_id'], f"{self.test_storage_id}/"
            )
            self.assertEqual(kwargs['body']['storage_id'], self.test_storage_id)
            self.assertEqual(kwargs['params'], {"apply_default_acls": "False"})

    def test_create_storage_root_collection_no_gateways(self):
        """Test _create_storage_root_collection with no storage gateways."""
        # Mock _get_storage_gateways_collection to return None
        with patch.object(
            self.recipe, '_get_storage_gateways_collection', return_value=None
        ):
            # Call the method
            result = self.recipe._create_storage_root_collection()

            # Verify the result
            self.assertIsNone(result)

            # Verify no API calls were made
            self.client.collections().create.assert_not_called()

    def test_ensure_storage_root_collection_exists(self):
        """Test _ensure_storage_root_collection when collection exists."""
        # Mock _get_storage_root_collection to return a collection ID
        with patch.object(
            self.recipe,
            '_get_storage_root_collection',
            return_value=self.test_collection_id
        ):
            # Call the method
            result = self.recipe._ensure_storage_root_collection()

            # Verify the result
            self.assertEqual(result, self.test_collection_id)

    def test_ensure_storage_root_collection_creates(self):
        """Test _ensure_storage_root_collection when collection needs to be created."""
        # Mock _get_storage_root_collection to return None
        with patch.object(
            self.recipe, '_get_storage_root_collection', return_value=None
        ):
            # Mock _create_storage_root_collection to return a collection ID
            with patch.object(
                self.recipe,
                '_create_storage_root_collection',
                return_value=self.test_collection_id
            ):
                # Call the method
                result = self.recipe._ensure_storage_root_collection()

                # Verify the result
                self.assertEqual(result, self.test_collection_id)

    @patch('os.path.basename')
    @patch('src.pythonikext.recipes.collection_directory_mapping.get_attribute')
    def test_get_collection_by_path_root(
        self, mock_get_attribute, mock_basename
    ):
        """Test _get_collection_by_path for root path."""
        # Mock _ensure_storage_root_collection to return a collection ID
        with patch.object(
            self.recipe,
            '_ensure_storage_root_collection',
            return_value=self.test_collection_id
        ):
            # Call the method for root path
            result = self.recipe._get_collection_by_path("/")

            # Verify the result
            self.assertEqual(result, self.test_collection_id)

            # Call the method for empty path
            result = self.recipe._get_collection_by_path("")

            # Verify the result
            self.assertEqual(result, self.test_collection_id)

    @patch('os.path.basename')
    @patch('src.pythonikext.recipes.collection_directory_mapping.get_attribute')
    def test_get_collection_by_path_mount_point(
        self, mock_get_attribute, mock_basename
    ):
        """Test _get_collection_by_path for mount point path."""
        # Set up the mount point
        self.recipe._mount_point = "/mnt/storage"

        # Mock _ensure_storage_root_collection to return a collection ID
        with patch.object(
            self.recipe,
            '_ensure_storage_root_collection',
            return_value=self.test_collection_id
        ):
            # Call the method for mount point path
            result = self.recipe._get_collection_by_path("/mnt/storage")

            # Verify the result
            self.assertEqual(result, self.test_collection_id)

    @patch('os.path.basename')
    def test_get_collection_by_path_cached(self, mock_basename):
        """Test _get_collection_by_path uses cache."""
        # Set up the cache
        external_id = f"{self.test_storage_id}/test/path"
        self.recipe._collection_cache[external_id] = self.test_collection_id

        # Set up the storage root collection ID
        self.recipe._storage_root_collection_id = "root-collection-id"

        # Mock basename to return the directory name
        mock_basename.return_value = "path"

        # Call the method
        result = self.recipe._get_collection_by_path("test/path")

        # Verify the result
        self.assertEqual(result, self.test_collection_id)

        # Verify no search was performed
        self.client.search().search.assert_not_called()

    def test_map_directory_structure_disabled(self):
        """Test map_directory_structure when mapping is disabled."""
        # Disable mapping
        with patch.object(
            self.recipe, '_is_mapping_enabled', return_value=False
        ):
            # Call the method
            result = self.recipe.map_directory_structure()

            # Verify the result
            self.assertFalse(result["success"])
            self.assertEqual(
                result["error"],
                "Collection directory mapping is not enabled for this storage"
            )

    def test_map_directory_structure_no_root(self):
        """Test map_directory_structure when root collection can't be created."""
        # Enable mapping but make root collection creation fail
        with patch.object(
            self.recipe, '_is_mapping_enabled', return_value=True
        ):
            with patch.object(
                self.recipe,
                '_ensure_storage_root_collection',
                return_value=None
            ):
                # Call the method
                result = self.recipe.map_directory_structure()

                # Verify the result
                self.assertFalse(result["success"])
                self.assertEqual(
                    result["error"], "Failed to ensure storage root collection"
                )

    def test_ensure_collection_hierarchy_disabled(self):
        """Test ensure_collection_hierarchy when mapping is disabled."""
        # Disable mapping
        with patch.object(
            self.recipe, '_is_mapping_enabled', return_value=False
        ):
            # Call the method
            result = self.recipe.ensure_collection_hierarchy("/test/path")

            # Verify the result
            self.assertIsNone(result)

    @patch('os.path.dirname')
    def test_ensure_collection_hierarchy_creates_directory(self, mock_dirname):
        """Test ensure_collection_hierarchy creates directory entry."""
        # Enable mapping
        with patch.object(
            self.recipe, '_is_mapping_enabled', return_value=True
        ):
            # Mock directory creation
            with patch.object(
                self.recipe, 'create_directory_entry', return_value=MagicMock()
            ):
                # Mock path normalization
                mock_dirname.return_value = self.test_path

                # Mock _ensure_collection_path
                with patch.object(
                    self.recipe,
                    '_ensure_collection_path',
                    return_value=self.test_collection_id
                ):
                    # Call the method
                    result = self.recipe.ensure_collection_hierarchy(
                        self.test_path
                    )

                    # Verify the result
                    self.assertEqual(result, self.test_collection_id)

                    # Verify directory was created
                    self.recipe.create_directory_entry.assert_called_once_with(
                        self.test_path
                    )

    def test_create_directory_entry_success(self):
        """Test create_directory_entry with success."""
        # Mock directory checking
        files_data = MagicMock()
        files_data.objects = []

        files_response = MagicMock()
        files_response.response.ok = True
        files_response.data = files_data

        # Mock directory creation
        create_data = MagicMock()

        create_response = MagicMock()
        create_response.response.ok = True
        create_response.data = create_data

        # Mock API calls
        self.client.files().gen_url.return_value = "https://app.iconik.io/files"

        with patch(
            'src.pythonikext.recipes.collection_directory_mapping.AssetSpec.parse_response',
            side_effect=[files_response, create_response]
        ):
            # Mock os.path functions
            with patch(
                'os.path.basename', return_value=self.test_directory_name
            ):
                with patch('os.path.dirname', return_value="/mnt/storage/test"):
                    # Call the method
                    result = self.recipe.create_directory_entry(self.test_path)

                    # Verify the result
                    self.assertEqual(result, create_data)

                    # Verify the correct API calls were made
                    self.assertEqual(self.client.session.post.call_count, 1)

                    # Verify the correct model was used
                    args, kwargs = self.client.session.post.call_args
                    body = kwargs['json']

                    self.assertEqual(body["name"], self.test_directory_name)
                    self.assertEqual(
                        body["original_name"], self.test_directory_name
                    )
                    self.assertEqual(
                        body["directory_path"], "/mnt/storage/test"
                    )
                    self.assertEqual(body["type"], "DIRECTORY")

    def test_create_directory_entry_already_exists(self):
        """Test create_directory_entry when directory already exists."""
        # Mock directory already exists
        dir_obj = MagicMock()

        files_data = MagicMock()
        files_data.objects = [dir_obj]

        files_response = MagicMock()
        files_response.response.ok = True
        files_response.data = files_data

        # Mock API calls
        self.client.files().gen_url.return_value = "https://app.iconik.io/files"

        with patch(
            'src.pythonikext.recipes.collection_directory_mapping.AssetSpec.parse_response',
            return_value=files_response
        ):
            # Call the method
            result = self.recipe.create_directory_entry(self.test_path)

            # Verify the result
            self.assertEqual(result, dir_obj)

            # Verify no creation was attempted
            self.client.session.post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
