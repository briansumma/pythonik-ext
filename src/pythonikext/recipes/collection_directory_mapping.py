"""
Collection directory mapping recipe for pythonik-ext

This recipe implements the collection directory mapping functionality that
creates a mirror of the file system directory structure in iconik collections
when the storage setting 'enable_collection_directory_mapping' is enabled.
"""
import argparse
import datetime
import logging
import os
import urllib.parse
from typing import Any, Dict, List, Optional

from pythonik.models.base import PaginatedResponse

from .._internal_utils import get_attribute
from .._logging import get_logger
from ..client import ExtendedPythonikClient as PythonikClient
from ..specs.assets import ExtendedAssetSpec as AssetSpec
from ..specs.collection import ExtendedCollectionSpec as CollectionSpec


logger = get_logger(__name__)

# Constants
STORAGE_GATEWAYS_EXTERNAL_ID = "ebb41a68-e4cb-11e7-af85-f45c89b15ba1"


class CollectionDirectoryMappingRecipe:
    """
    Recipe for managing the collection directory mapping feature.

    This recipe creates a mirror of the file system directory structure in
    iconik collections when the 'enable_collection_directory_mapping' setting
    is enabled for a storage.
    """

    def __init__(
        self,
        client: PythonikClient,
        storage_id: str,
        storage_root_path: Optional[str] = None,
    ):
        """
        Initialize the recipe with client and storage info.

        Args:
            client: Configured PythonikClient instance
            storage_id: ID of the storage to use
            storage_root_path: Optional root path for the storage (if not
                specified, will be determined from storage settings)
        """
        self.client = client
        self.storage_id = storage_id
        self.storage_root_path = storage_root_path

        self._storage_settings = None
        self._storage_name = None
        self._storage_gateways_collection_id = None
        self._storage_root_collection_id = None
        self._mount_point = None
        self._collection_cache = {}  # cache collection IDs by external_id

    @property
    def storage_settings(self) -> Dict[str, Any]:
        """Cached storage settings dict."""
        if self._storage_settings is None:
            try:
                response = self.client.files().get_storage(self.storage_id)
                if response.response.ok:
                    storage_obj = response.data
                    self._storage_settings = storage_obj.settings or {}
                    self._storage_name = storage_obj.name
                else:
                    logger.warning(
                        "Failed to fetch storage settings: %s",
                        response.response.text
                    )
                    self._storage_settings = {}
            except Exception as e:
                logger.error("Error fetching storage settings: %s", str(e))
                self._storage_settings = {}

        return self._storage_settings

    @property
    def mount_point(self) -> str:
        """Get storage mount point from settings."""
        if self._mount_point is None:
            self._mount_point = self.storage_settings.get('mount_point', '/')
        return self._mount_point

    @property
    def storage_name(self) -> str:
        """Get storage name."""
        if self._storage_name is None:
            # Trigger loading storage settings which also loads the name
            _ = self.storage_settings
        return self._storage_name or f"Storage {self.storage_id}"

    def _is_mapping_enabled(self) -> bool:
        """Check if collection directory mapping is enabled for this storage."""
        return self.storage_settings.get(
            'enable_collection_directory_mapping', False
        )

    def _get_storage_gateways_collection(self) -> Optional[str]:
        """
        Get the ID of the "Storage Gateways" root collection.

        Returns:
            Collection ID or None if not found
        """
        if self._storage_gateways_collection_id is not None:
            return self._storage_gateways_collection_id

        params = {
            "external_id": STORAGE_GATEWAYS_EXTERNAL_ID,
            "is_root": "True"
        }

        try:
            collections_url = self.client.assets().gen_url("collections")
            logger.debug("collections_url: %s", collections_url)

            response = self.client.session.get(collections_url, params=params)
            collection_response = CollectionSpec.parse_response(
                response, PaginatedResponse
            )

            if collection_response.response.ok and collection_response.data.objects and len(
                collection_response.data.objects
            ) > 0:
                collection = collection_response.data.objects[0]
                self._storage_gateways_collection_id = get_attribute(
                    collection, "id"
                )
                logger.info(
                    "Found Storage Gateways collection with ID: %s",
                    self._storage_gateways_collection_id
                )
                return self._storage_gateways_collection_id

            logger.warning("Storage Gateways collection not found")
            return None
        except Exception as e:
            logger.error(
                "Error finding Storage Gateways collection: %s", str(e)
            )
            return None

    def _get_storage_root_collection(self) -> Optional[str]:
        """
        Get the ID of the storage root collection.

        Returns:
            Collection ID or None if not found
        """
        if self._storage_root_collection_id is not None:
            return self._storage_root_collection_id

        storage_gateways_id = self._get_storage_gateways_collection()
        if not storage_gateways_id:
            logger.warning(
                "Cannot find storage root collection without Storage Gateways ID"
            )
            return None

        # The storage root collection has an external_id of "storage_id/"
        external_id = f"{self.storage_id}/"

        params = {"page": 1, "per_page": 100, "object_types": "collections"}

        try:
            # Check if the storage collection exists as a child of Storage
            # Gateways
            contents_url = self.client.collections(
            ).gen_url(f"collections/{storage_gateways_id}/contents/")
            contents_params = {**params, "external_id": external_id}
            contents_response = self.client.session.get(
                contents_url, params=contents_params
            )
            contents_data = AssetSpec.parse_response(
                contents_response, PaginatedResponse
            )

            if (
                contents_data.response.ok and contents_data.data
                and get_attribute(contents_data.data, "objects")
                and len(contents_data.data.objects) > 0
            ):
                collection = contents_data.data.objects[0]
                self._storage_root_collection_id = get_attribute(
                    collection, "id"
                )
                logger.info(
                    "Found storage root collection with ID: %s",
                    self._storage_root_collection_id
                )
                # Add to cache
                self._collection_cache[external_id
                                       ] = self._storage_root_collection_id
                return self._storage_root_collection_id

            logger.info("Storage root collection not found, will create it")
            return None
        except Exception as e:
            logger.error("Error finding storage root collection: %s", str(e))
            return None

    def _create_storage_root_collection(self) -> Optional[str]:
        """
        Create the storage root collection.

        Returns:
            Collection ID or None if creation failed
        """
        storage_gateways_id = self._get_storage_gateways_collection()
        if not storage_gateways_id:
            logger.warning(
                "Cannot create storage root collection without Storage Gateways ID"
            )
            return None

        collection_model = {
            "title": self.storage_name,
            "parent_id": storage_gateways_id,
            "external_id": f"{self.storage_id}/",
            "storage_id": self.storage_id
        }

        try:
            response = self.client.collections().create(
                body=collection_model, params={"apply_default_acls": "False"}
            )

            if response.response.ok:
                collection_id = get_attribute(response.data, "id")
                logger.info(
                    "Created storage root collection with ID: %s", collection_id
                )
                self._storage_root_collection_id = collection_id
                # Add to cache
                self._collection_cache[f"{self.storage_id}/"] = collection_id
                return collection_id

            logger.warning(
                "Failed to create storage root collection: %s",
                response.response.text
            )
            return None
        except Exception as e:
            logger.error("Error creating storage root collection: %s", str(e))
            return None

    def _ensure_storage_root_collection(self) -> Optional[str]:
        """
        Ensure the storage root collection exists, creating it if necessary.

        Returns:
            Collection ID or None if it doesn't exist and can't be created
        """
        collection_id = self._get_storage_root_collection()

        if not collection_id:
            collection_id = self._create_storage_root_collection()

        return collection_id

    def _get_collection_by_path(
        self, path: str, parent_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Get collection ID for a specific path.

        Args:
            path: Path in the storage
            parent_id: Optional parent collection ID

        Returns:
            Collection ID or None if not found
        """
        if not path or path == "/":
            return self._ensure_storage_root_collection()

        # Normalize path - remove storage mount point if present
        if self.mount_point and path.startswith(self.mount_point):
            path = path[len(self.mount_point):]
        path = path.strip('/')

        if not path:
            return self._ensure_storage_root_collection()

        # Check cache first
        storage_root_id = self._ensure_storage_root_collection()
        if not storage_root_id:
            return None

        # Build the external ID based on path
        external_id = f"{self.storage_id}/"
        if parent_id:
            # If we have a parent, we need to include that in the external ID
            external_id = f"{self.storage_id}/{parent_id}/"

        if path:
            external_id = f"{external_id}{path}"

        # Check cache first
        if external_id in self._collection_cache:
            return self._collection_cache[external_id]

        # Search for the collection
        folder_name = os.path.basename(path)
        search_body = {
            "doc_types": ["collections"],
            "filter": {
                "operator": "AND",
                "terms": [{
                    "name": "parent_id",
                    "value": parent_id or storage_root_id
                }],
                "filters": [{
                    "operator": "OR",
                    "terms": [{
                        "name": "external_id",
                        "value": external_id
                    }, {
                        "name": "title.lower",
                        "value": folder_name.lower()
                    }]
                }]
            }
        }

        try:
            search_response = self.client.search().search(
                search_body,
                params={
                    "page": 1,
                    "per_page": 100,
                    "save_search_history": "False"
                }
            )

            if (
                search_response.response.ok and search_response.data
                and get_attribute(search_response.data, "objects")
                and len(search_response.data.objects) > 0
            ):
                collection = search_response.data.objects[0]
                collection_id = get_attribute(collection, "id")
                logger.debug(
                    "Found collection for path '%s': %s", path, collection_id
                )
                # Add to cache
                self._collection_cache[external_id] = collection_id
                return collection_id

            logger.debug("Collection for path '%s' not found", path)
            return None
        except Exception as e:
            logger.error(
                "Error finding collection for path '%s': %s", path, str(e)
            )
            return None

    def _create_collection(self, path: str, parent_id: str) -> Optional[str]:
        """
        Create a collection for a specific path.

        Args:
            path: Path in the storage
            parent_id: Parent collection ID

        Returns:
            Collection ID or None if creation failed
        """
        folder_name = os.path.basename(path)

        # Build the external ID based on path
        external_id = f"{self.storage_id}/"
        if parent_id and parent_id != self._storage_root_collection_id:
            # Get the parent's external ID to construct the new one
            for cached_ext_id, cached_id in self._collection_cache.items():
                if cached_id == parent_id:
                    external_id = f"{cached_ext_id}/{folder_name}"
                    break
            else:
                # If we can't find the parent's external ID, use a simpler
                # approach
                external_id = f"{self.storage_id}/{parent_id}/{folder_name}"
        else:
            # Directly under storage root
            external_id = f"{self.storage_id}/{folder_name}"

        collection_model = {
            "title": folder_name,
            "parent_id": parent_id,
            "external_id": external_id,
            "storage_id": self.storage_id
        }

        try:
            response = self.client.collections().create(
                body=collection_model, params={"apply_default_acls": "False"}
            )

            if response.response.ok:
                collection_id = get_attribute(response.data, "id")
                logger.info(
                    "Created collection for path '%s' with ID: %s", path,
                    collection_id
                )
                # Add to cache
                self._collection_cache[external_id] = collection_id
                return collection_id

            logger.warning(
                "Failed to create collection for path '%s': %s", path,
                response.response.text
            )
            return None
        except Exception as e:
            logger.error(
                "Error creating collection for path '%s': %s", path, str(e)
            )
            return None

    def _ensure_collection_path(self, path: str) -> Optional[str]:
        """
        Ensure a collection path exists, creating it if necessary.

        Args:
            path: Path in the storage

        Returns:
            Collection ID of the leaf collection or None if it can't be created
        """
        if not path or path == "/":
            return self._ensure_storage_root_collection()

        # Normalize path - remove storage mount point if present
        if self.mount_point and path.startswith(self.mount_point):
            path = path[len(self.mount_point):]
        path = path.strip('/')

        if not path:
            return self._ensure_storage_root_collection()

        # Split path into components and ensure each level exists
        path_parts = path.split('/')
        current_path = ""
        parent_id = self._ensure_storage_root_collection()

        if not parent_id:
            logger.warning(
                "Cannot create collection path without root collection"
            )
            return None

        current_id = parent_id

        for i, _ in enumerate(path_parts):
            current_path = "/".join(path_parts[:i + 1])

            # Try to get the collection for this path
            collection_id = self._get_collection_by_path(
                current_path, parent_id
            )

            if not collection_id:
                # Collection doesn't exist, create it
                collection_id = self._create_collection(current_path, parent_id)

                if not collection_id:
                    logger.warning(
                        "Failed to create collection for path '%s'",
                        current_path
                    )
                    return None

            parent_id = collection_id
            current_id = collection_id

        return current_id

    def _get_directory_files(self, path: str) -> List[Dict[str, Any]]:
        """
        Get list of directories at the given path.

        Args:
            path: Path in the storage

        Returns:
            List of directory objects
        """
        # Normalize path - remove storage mount point if present
        if self.mount_point and path.startswith(self.mount_point):
            path = path[len(self.mount_point):]
        path = path.strip('/')

        # URL encode path
        _ = urllib.parse.quote_plus(path)

        try:
            files_url = self.client.files(
            ).gen_url(f"storages/{self.storage_id}/files/")
            params = {"path": path, "path_separator": "/", "type": "DIRECTORY"}
            files_response = self.client.session.get(files_url, params=params)
            files_data = AssetSpec.parse_response(
                files_response, PaginatedResponse
            )

            if (
                files_data.response.ok and files_data.data
                and get_attribute(files_data.data, "objects")
            ):
                return files_data.data.objects

            logger.debug("No directories found at path '%s'", path)
            return []
        except Exception as e:
            logger.error(
                "Error getting directories at path '%s': %s", path, str(e)
            )
            return []

    def create_directory_entry(self, path: str, is_directory: bool = True) -> \
            Optional[Dict[str, Any]]:
        """
        Create a directory entry in the storage if it doesn't exist.

        Args:
            path: Path in the storage
            is_directory: Whether the entry is a directory

        Returns:
            Directory object if created, None otherwise
        """
        # Normalize path
        if self.mount_point and path.startswith(self.mount_point):
            path = path[len(self.mount_point):]
        path = path.strip('/')

        if not path:
            logger.warning("Cannot create root directory entry")
            return None

        # Check if the directory already exists
        try:
            files_url = self.client.files(
            ).gen_url(f"storages/{self.storage_id}/files/")
            params = {
                "path": path,
                "path_separator": "/",
                "type": "DIRECTORY" if is_directory else "FILE"
            }
            files_response = self.client.session.get(files_url, params=params)
            files_data = AssetSpec.parse_response(
                files_response, PaginatedResponse
            )

            if (
                files_data.response.ok and files_data.data
                and get_attribute(files_data.data, "objects")
                and len(files_data.data.objects) > 0
            ):
                # Directory already exists
                return files_data.data.objects[0]
        except Exception as e:
            logger.error("Error checking if directory exists: %s", str(e))
            return None

        # Directory doesn't exist, create it
        folder_name = os.path.basename(path)
        directory_path = os.path.dirname(path)

        try:
            # Create the directory
            directory_model = {
                "name": folder_name,
                "original_name": folder_name,
                "directory_path": directory_path,
                "type": "DIRECTORY" if is_directory else "FILE",
                "file_date_created": datetime.datetime.now().isoformat(),
                "file_date_modified": datetime.datetime.now().isoformat()
            }

            create_url = self.client.files(
            ).gen_url(f"storages/{self.storage_id}/files/")
            create_response = self.client.session.post(
                create_url, json=directory_model
            )
            create_data = AssetSpec.parse_response(
                create_response, PaginatedResponse
            )

            if create_data.response.ok:
                logger.info("Created directory entry for path '%s'", path)
                return create_data.data
            logger.warning(
                "Failed to create directory entry: %s",
                create_data.response.text
            )
            return None
        except Exception as e:
            logger.error("Error creating directory entry: %s", str(e))
            return None

    def ensure_collection_hierarchy(self, path: str) -> Optional[str]:
        """
        Ensure the collection hierarchy exists for a given path.

        This method:
        1. Checks if the directory exists in the storage
        2. Creates it if it doesn't exist
        3. Ensures the collection path exists

        Args:
            path: Path in the storage

        Returns:
            Collection ID of the leaf collection or None if it can't be created
        """
        if not self._is_mapping_enabled():
            logger.warning(
                "Collection directory mapping is not enabled for storage %s",
                self.storage_id
            )
            return None

        # Create directory entry if it doesn't exist
        if path and path != "/" and path != self.mount_point:
            self.create_directory_entry(path)

        # Ensure collection hierarchy
        return self._ensure_collection_path(path)

    def map_directory_structure(self,
                                root_path: Optional[str] = None
                                ) -> Dict[str, Any]:
        """
        Map the directory structure to collections.

        Args:
            root_path: Optional root path to start mapping from

        Returns:
            Dictionary with results of the mapping
        """
        if not self._is_mapping_enabled():
            logger.warning(
                "Collection directory mapping is not enabled for storage %s",
                self.storage_id
            )
            return {
                "success": False,
                "error": "Collection directory mapping is not enabled for this storage"
            }

        # Use provided root_path or storage_root_path or mount_point
        root_path = root_path or self.storage_root_path or self.mount_point or "/"

        # Normalize path
        if self.mount_point and root_path.startswith(self.mount_point):
            root_path = root_path[len(self.mount_point):]
        root_path = root_path.strip('/')

        # Convert empty string to root
        if not root_path:
            root_path = "/"

        logger.info("Mapping directory structure from root path: %s", root_path)

        # Ensure storage root collection exists
        storage_root_id = self._ensure_storage_root_collection()
        if not storage_root_id:
            return {
                "success": False,
                "error": "Failed to ensure storage root collection"
            }

        # Map directories recursively
        mapped_collections = {}

        try:
            self._map_directory_recursive(
                root_path,
                storage_root_id,
                mapped_collections,
                current_depth=0,
                max_depth=10
            )

            return {"success": True, "mapped_collections": mapped_collections}
        except Exception as e:
            logger.error("Error mapping directory structure: %s", str(e))
            return {
                "success": False,
                "error": str(e),
                "partial_mapping": mapped_collections
            }

    # pylint: disable=too-many-positional-arguments
    def _map_directory_recursive(
        self,
        path: str,
        parent_id: str,
        mapped_collections: Dict[str, Any],
        current_depth: int = 0,
        max_depth: int = 10
    ) -> None:
        """
        Recursively map directories to collections.

        Args:
            path: Current path
            parent_id: Parent collection ID
            mapped_collections: Dictionary to store mapping results
            current_depth: Current recursion depth
            max_depth: Maximum recursion depth
        """
        if current_depth >= max_depth:
            logger.warning("Max recursion depth reached for path '%s'", path)
            return

        # Normalize path for display
        display_path = path if path != "/" else "<root>"

        # Get or create collection for current path, using parent_id for context
        collection_id = None
        if current_depth == 0:
            # For the root level, ensure the path exists
            collection_id = self._ensure_collection_path(path)
        else:
            # For deeper levels, first try to get the collection
            collection_id = self._get_collection_by_path(path, parent_id)

            # If not found, create it
            if not collection_id:
                collection_id = self._create_collection(path, parent_id)

        if not collection_id:
            logger.warning("Failed to ensure collection for path '%s'", path)
            return

        # Store the mapping
        mapped_collections[path] = collection_id
        logger.info(
            "Mapped path '%s' to collection ID: %s", display_path, collection_id
        )

        # Get directories at current path
        directories = self._get_directory_files(path)

        # Recursively map subdirectories
        for directory in directories:
            dir_name = get_attribute(directory, "name")
            if not dir_name:
                continue

            sub_path = path + "/" + dir_name if path != "/" else dir_name

            # Recursively map this directory
            self._map_directory_recursive(
                sub_path, collection_id, mapped_collections, current_depth + 1,
                max_depth
            )


def main():
    """
    Command-line entry point for the CollectionDirectoryMappingRecipe.
    
    Usage:
        python -m pythonikext.recipes.collection_directory_mapping \
            --app-id <app_id> \
            --auth-token <auth_token> \
            --storage-id <storage_id> \
            [--root-path <root_path>] \
            [--base-url <base_url>] \
            [--timeout <timeout>] \
            [--debug]
    """

    parser = argparse.ArgumentParser(
        description='Collection Directory Mapping Recipe for iconik',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        '--storage-id', required=True, help='Storage ID to map directories for'
    )

    parser.add_argument(
        '--root-path',
        help='Root path to start mapping from (defaults to storage mount point)'
    )

    auth_group = parser.add_argument_group('Authentication')
    auth_group.add_argument('--app-id', required=True, help='Iconik App ID')
    auth_group.add_argument(
        '--auth-token', required=True, help='Iconik Auth Token'
    )
    auth_group.add_argument(
        '--base-url',
        default='https://app.iconik.io',
        help='Iconik API base URL'
    )

    parser.add_argument(
        '--timeout', type=int, default=30, help='Request timeout in seconds'
    )

    parser.add_argument(
        '--debug', action='store_true', help='Enable debug logging'
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create client
    client = PythonikClient(
        app_id=args.app_id,
        auth_token=args.auth_token,
        timeout=args.timeout,
        base_url=args.base_url
    )

    # Create recipe
    recipe = CollectionDirectoryMappingRecipe(
        client=client,
        storage_id=args.storage_id,
        storage_root_path=args.root_path
    )

    # Map directory structure
    result = recipe.map_directory_structure()

    # Print results
    if result["success"]:
        print("\nDirectory mapping complete!")
        print(
            f"Mapped {len(result['mapped_collections'])} directories to collections"
        )

        if args.debug:
            print("\nMapped collections:")
            for path, collection_id in result["mapped_collections"].items():
                print(f"  {path or '<root>'} -> {collection_id}")
    else:
        print(
            f"\nDirectory mapping failed: {result.get('error', 'Unknown error')}"
        )

        if "partial_mapping" in result:
            print(
                f"Partially mapped {len(result['partial_mapping'])} directories"
            )

            if args.debug:
                print("\nPartially mapped collections:")
                for path, collection_id in result["partial_mapping"].items():
                    print(f"  {path or '<root>'} -> {collection_id}")


if __name__ == "__main__":
    main()
