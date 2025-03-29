import json
import logging
import mimetypes
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Any

from pythonik.models.assets.assets import AssetCreate
from pythonik.models.base import PaginatedResponse
from pythonik.models.files.file import FileCreate, FileStatus, FileType
from pythonik.models.files.format import FormatCreate
from pythonik.models.mutation.metadata.mutate import UpdateMetadata, \
    MetadataValues
from pythonik.specs.assets import AssetSpec

from ..client import ExtendedPythonikClient as PythonikClient
from ..utils import calculate_md5, suppress_stdout, get_mountpoint

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GeneralException(Exception):
    """Base class for general or unknown errors."""


class IconikStorageGatewayRecipe:
    """
    Recipe for creating assets in iconik that mirrors ISG behavior.
    Handles all steps of asset creation with intelligent retry/resume.
    """

    def __init__(
        self,
        client: PythonikClient,
        storage_id: str,
        default_view_id: Optional[str] = None
    ):
        """
        Initialize the recipe with client and storage info.

        Args:
            client: Configured PythonikClient instance
            storage_id: ID of the storage to use
            default_view_id: Optional default metadata view ID
        """
        self.client = client
        self.storage_id = storage_id
        self.default_view_id = default_view_id

        # Cache storage info
        self._storage_settings = None
        self._storage_mount_point = None

    @property
    def storage_settings(self) -> Dict[str, Any]:
        """Cached storage settings dict."""
        if self._storage_settings is None:
            try:
                response = self.client.files().get_storage(self.storage_id)
                if response.response.ok:
                    storage_obj = response.data
                    self._storage_settings = storage_obj.settings
                    if not self._storage_settings:
                        self._storage_settings = {}
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
        """Get storage mount point."""
        if self._storage_mount_point is None:
            self._storage_mount_point = self.storage_settings.get(
                'mount_point', '/'
            )
        return self._storage_mount_point

    def get_relative_path(self, file_path: str) -> str:
        """
        Get path relative to storage mount point.

        Args:
            file_path: Absolute file path

        Returns:
            Path relative to storage mount point
        """
        abs_path = os.path.abspath(file_path)

        # If mount point is in the path, remove it to get the relative path
        if abs_path.startswith(self.mount_point):
            return abs_path[len(self.mount_point):].lstrip('/')

        # If not, return the original path
        return abs_path

    def check_for_duplicate_files(self, file_path: str) -> List[Dict]:
        """
        Check for duplicate files by checksum.

        Args:
            file_path: Path to the file

        Returns:
            List of file objects with the same checksum
        """
        try:
            # Use the extended get_files_by_checksum method from pythonikext
            # This method can accept either a checksum string or a file path
            response = self.client.files().get_files_by_checksum(file_path)

            if response.response.ok and response.data.objects:
                return response.data.objects
        except Exception as e:
            logger.error("Error checking for duplicate files: %s", str(e))

        return []

    @staticmethod
    def check_for_sidecar_metadata(file_path: str) -> Optional[Dict]:
        """
        Check for and parse sidecar metadata files.

        Args:
            file_path: Path to the media file

        Returns:
            Parsed metadata dictionary or None
        """
        # if not self.storage_settings.get("sidecar_metadata_required", False):
        #     return None

        file_stem, _ = os.path.splitext(file_path)
        logger.debug("file_stem: %s", file_stem)

        # ref: https://help.iconik.backlight.co/hc/en-us/articles/25027403438871-Sidecar-metadata
        possible_sidecar_paths = [
            f"{file_path}.json", f"{file_stem}.json", f"{file_path}.xml",
            f"{file_stem}.xml", f"{file_path}.csv", f"{file_stem}.csv"
        ]

        for sidecar_path in possible_sidecar_paths:
            if os.path.exists(sidecar_path):
                _, sidecar_ext = os.path.splitext(sidecar_path)
                logger.debug("sidecar_ext: %s", sidecar_ext)
                try:
                    with open(sidecar_path, 'r', encoding='utf-8') as fp:
                        if sidecar_ext.upper() in ["JSON", ".JSON"]:
                            return json.load(fp)
                        if sidecar_ext.upper() in ["XML", ".XML"]:
                            # TODO: Implement XML sidecars
                            logger.warning(
                                "XML sidecar detected but not currently supported"
                            )
                            return None
                        if sidecar_ext.upper() in ["CSV", ".CSV"]:
                            # TODO: Implement CSV sidecars
                            logger.warning(
                                "CSV sidecar detected but not currently supported"
                            )
                            return None
                except Exception as e:
                    logger.error(
                        "Error parsing sidecar file %s: %s", sidecar_path,
                        str(e)
                    )
        return None

    def format_metadata_values(self, metadata: Dict, view_id: str) -> Dict:
        """
        Format metadata into the structure iconik expects.

        Args:
            metadata: Raw metadata dictionary
            view_id: Metadata view ID

        Returns:
            Formatted metadata values dictionary
        """
        metadata_values = {}

        # Get view to understand field types
        try:
            view_response = self.client.metadata().get_view(view_id)
            if not view_response.response.ok:
                logger.warning(
                    "Failed to get metadata view: %s",
                    view_response.response.text
                )

                return metadata_values

            view_fields = {
                field.name: field
                for field in view_response.data.view_fields
            }

            for field_name, value in metadata.items():
                if field_name not in view_fields:
                    continue

                field_type = view_fields[field_name].field_type
                multi = view_fields[field_name].multi

                metadata_values[field_name] = {"field_values": []}

                # Handle various field types
                if value is None:
                    continue

                # Convert to list if multi-value field
                values = value if isinstance(value, list) and multi else [value]

                for field_value in values:
                    if field_value is None:
                        continue

                    # Handle boolean fields
                    if field_type == "boolean":
                        if isinstance(field_value, bool):
                            field_value = str(field_value).lower()
                        elif isinstance(field_value, str):
                            field_value = str(
                                field_value.lower() in
                                ['y', 'yes', 't', 'true', 'on', '1']
                            ).lower()

                    # Handle date fields
                    elif field_type == "date" and isinstance(field_value, str):
                        try:
                            # Try to parse date format
                            dt = datetime.fromisoformat(
                                field_value.replace('Z', '+00:00')
                            )
                            field_value = dt.strftime('%Y-%m-%d')
                        except ValueError:
                            pass

                    # Add the value
                    if field_value is not None:
                        metadata_values[field_name]["field_values"].append({
                            "value": field_value
                        })

        except Exception as e:
            logger.error("Error formatting metadata: %s", str(e))

        return metadata_values

    def has_mediainfo(self, asset_id: str, file_id: str) -> bool:
        """
        Check if mediainfo extraction has already been run.

        Args:
            asset_id: Asset ID
            file_id: File ID

        Returns:
            True if mediainfo exists, False otherwise
        """
        try:
            # Try to get mediainfo for the file
            mediainfo_url = self.client.files(
            ).gen_url(f"assets/{asset_id}/files/{file_id}/mediainfo")
            response = self.client.session.get(mediainfo_url)

            # If we get a successful response with data, mediainfo exists
            return response.ok and response.json().get('objects')
        except Exception as e:
            logger.error("Error checking mediainfo status: %s", str(e))
            # If we can't check, assume it doesn't exist
            return False

    def has_proxies(self, asset_id: str) -> bool:
        """
        Check if proxies already exist for this asset.

        Args:
            asset_id: Asset ID

        Returns:
            True if proxies exist, False otherwise
        """
        try:
            # Check for existing proxies
            proxy_response = self.client.files().get_asset_proxies(asset_id)

            # If we have proxies already, no need to generate more
            return proxy_response.response.ok and proxy_response.data.objects
        except Exception as e:
            logger.error("Error checking proxy status: %s", str(e))
            # If we can't check, assume they don't exist
            return False

    def has_keyframes(self, asset_id: str) -> bool:
        """
        Check if keyframes already exist for this asset.

        Args:
            asset_id: Asset ID

        Returns:
            True if keyframes exist, False otherwise
        """
        try:
            # Check for existing keyframes
            keyframes_response = self.client.files(
            ).get_asset_keyframes(asset_id)

            # If we have keyframes already, no need to generate more
            return keyframes_response.response.ok and keyframes_response.data.objects
        except Exception as e:
            logger.error("Error checking keyframes status: %s", str(e))
            # If we can't check, assume they don't exist
            return False

    def has_transcoding_history(self, asset_id: str) -> bool:
        """
        Check if there's already a transcoding history entry.

        Args:
            asset_id: Asset ID

        Returns:
            True if transcoding history exists, False otherwise
        """
        try:
            history_url = self.client.assets(
            ).gen_url(f"assets/{asset_id}/history/")
            response = self.client.session.get(history_url)

            if response.ok:
                history_entries = response.json().get('objects', [])
                for entry in history_entries:
                    # Check for transcode operations
                    if entry.get('operation_type') == 'TRANSCODE':
                        return True
            return False
        except Exception as e:
            logger.error("Error checking history: %s", str(e))
            return False

    def has_metadata(self, asset_id: str, view_id: str) -> bool:
        """
        Check if metadata already exists for this asset and view.

        Args:
            asset_id: Asset ID
            view_id: Metadata view ID

        Returns:
            True if metadata exists, False otherwise
        """
        try:
            # Get asset metadata for this view
            metadata_url = self.client.metadata(
            ).gen_url(f"assets/{asset_id}/views/{view_id}")
            response = self.client.session.get(metadata_url)

            # If we get a successful response
            if response.ok:
                metadata = response.json()
                # Check if there are any metadata values
                metadata_values = metadata.get('metadata_values', {})

                # If any field has values, we consider metadata to exist
                for field_values in metadata_values.values():
                    values = field_values.get('field_values', [])
                    if values and len(values) > 0:
                        return True

            return False
        except Exception as e:
            logger.error("Error checking metadata status: %s", str(e))
            # If we can't check, assume it doesn't exist
            return False

    # pylint: disable=too-many-positional-arguments
    def create_asset(
        self,
        file_path: str,
        external_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        view_id: Optional[str] = None,
        collection_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create an asset with associated format, file set, and file.

        Args:
            file_path: Path to the file
            external_id: Optional external ID (generated from path if None)
            metadata: Optional metadata to apply
            view_id: Optional metadata view ID (overrides default)
            collection_ids: Optional list of collection IDs to add the asset to

        Returns:
            Dictionary with details of the created objects
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Log the storage_settings here to avoid spamming the logs
        logger.debug("storage_settings: %s", self.storage_settings)

        # Get file details
        file_checksum = calculate_md5(file_path)
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        file_stem, _ = os.path.splitext(file_name)
        mount_point = get_mountpoint(file_path)
        title_includes_extension = self.storage_settings.get(
            'title_includes_extension', True
        )
        title = file_name if title_includes_extension else file_stem
        logger.debug("title: %s", title)

        # Get relative directory path
        directory_path = os.path.dirname(file_path)
        if directory_path.startswith(mount_point):
            directory_path = directory_path[len(mount_point):].lstrip('/')
        logger.debug("directory_path: %s", directory_path)

        # Generate external ID if not provided
        if not external_id:
            if self.storage_settings.get('filename_is_external_id', False):
                external_id = file_name
            else:
                # Using calculate_md5 from pythonikext
                external_id = f"{directory_path}/{file_checksum}"
        logger.debug("external_id: %s", external_id)

        # Get MIME type
        mime_type, _ = mimetypes.guess_type(file_name)

        # TODO: Fix 'Check ignored patterns'; thinking the issue is that the
        #  regex patterns are formatted with extra escape characters and
        #  delimiters that aren't needed in Python's regex implementation
        # Check ignored patterns
        scan_ignore = self.storage_settings.get('scan_ignore', [])
        for pattern in scan_ignore:
            if pattern.startswith('re:'):
                # Handle regex pattern
                regex = pattern[4:].rstrip('/')
                if re.search(regex, file_name):
                    raise ValueError(
                        f"File matches scan_ignore pattern: {pattern}"
                    )
            elif pattern.startswith('*'):
                # Handle wildcard pattern
                if file_name.endswith(pattern[1:]):
                    raise ValueError(
                        f"File matches scan_ignore pattern: {pattern}"
                    )

        # Check for sidecar metadata
        sidecar_metadata = self.check_for_sidecar_metadata(file_path)
        if self.storage_settings.get(
            'sidecar_metadata_required', False
        ) and sidecar_metadata is None:
            raise ValueError("Sidecar metadata required but not found")

        # Combine provided metadata with sidecar metadata
        if sidecar_metadata:
            logger.debug("sidecar_metadata: %s", sidecar_metadata)
            if metadata:
                # Merge, with provided metadata taking precedence
                merged_metadata = {**sidecar_metadata, **metadata}
                logger.debug("merged_metadata: %s", merged_metadata)
                metadata = merged_metadata
            else:
                metadata = sidecar_metadata
                logger.debug("metadata: %s", metadata)

        # Determine which metadata view to use
        metadata_view_id = view_id or self.default_view_id or self.storage_settings.get(
            'metadata_view_id'
        )
        logger.debug("metadata_view_id: %s", metadata_view_id)

        # Initialize result
        result = {
            "storage_id": self.storage_id,
            "file_path": file_path,
            "title": title,
            "external_id": external_id,
            "size": file_size,
            "mime_type": mime_type,
            "directory_path": directory_path,
            "metadata_view_id": metadata_view_id
        }

        # Check for duplicates if aggregation is enabled
        aggregate_identical = self.storage_settings.get(
            'aggregate_identical_files', False
        )
        aggregate_only_same_storage = self.storage_settings.get(
            'aggregate_only_on_same_storage', False
        )

        existing_file = None
        if aggregate_identical:
            duplicate_files = self.check_for_duplicate_files(file_path)

            if duplicate_files:
                for file_obj in duplicate_files:
                    # If aggregation is limited to same storage, check storage ID
                    if aggregate_only_same_storage and file_obj[
                        'storage_id'] != self.storage_id:
                        continue

                    existing_file = file_obj
                    break

        # Track what already existed before our operation
        asset_existed_before = False
        format_existed_before = False
        file_set_existed_before = False
        file_existed_before = False

        # STEP 1: Get or create asset
        asset_id = None
        if existing_file:
            asset_id = existing_file['asset_id']
            logger.info("Found existing asset with ID: %s", asset_id)
            result["asset_id"] = asset_id
            result["duplicate_detected"] = True
            asset_existed_before = True
        else:
            # Try to find by external_id first
            try:
                assets_url = self.client.assets().gen_url("assets")
                logger.debug("assets_url: %s", assets_url)

                params = {"external_id": external_id}
                response = self.client.session.get(assets_url, params=params)
                asset_response = AssetSpec.parse_response(
                    response, PaginatedResponse
                )

                if asset_response.response.ok and asset_response.data.objects:
                    asset = asset_response.data.objects[0]
                    asset_id = asset['id']
                    logger.info(
                        "Found existing asset with external ID %s: %s",
                        external_id, asset_id
                    )
                    result["asset_id"] = asset_id
                    asset_existed_before = True
            except Exception as e:
                logger.warning(
                    "Error looking up asset by external ID: %s", str(e)
                )
        # Create a new asset if not found
        if not asset_id:
            try:
                # Determine if default ACLs should be applied
                apply_default_acls = not (
                    self.storage_settings.get("acl_template_id")
                    or self.storage_settings.get("access_group_id")
                )

                # Create asset
                asset_model = AssetCreate(
                    title=title,
                    external_id=external_id,
                )

                asset_response = self.client.assets().create(
                    body=asset_model,
                    params={"apply_default_acls": apply_default_acls}
                )

                if not asset_response.response.ok:
                    raise GeneralException(
                        f"Failed to create asset: {asset_response.response.text}"
                    )

                asset_id = asset_response.data.id
                logger.info("Created new asset with ID: %s", asset_id)
                result["asset_id"] = asset_id

                # Apply ACLs if specified
                self._apply_acls(asset_id)

            except Exception as e:
                logger.error("Error creating asset: %s", str(e))
                raise

        # STEP 2: Get or create format (ORIGINAL)
        format_id = None
        format_response = self.client.files().get_asset_formats(asset_id)

        if format_response.response.ok and format_response.data.objects:
            for format_obj in format_response.data.objects:
                if format_obj.name == "ORIGINAL" and format_obj.status == "ACTIVE":
                    format_id = format_obj.id
                    logger.info("Found existing format with ID: %s", format_id)
                    format_existed_before = True
                    break

        if not format_id:
            try:
                format_model = FormatCreate(
                    name="ORIGINAL", storage_methods=["FILE"], is_online=True
                )

                format_response = self.client.files().create_asset_format(
                    asset_id, body=format_model
                )
                if not format_response.response.ok:
                    raise GeneralException(
                        f"Failed to create format: {format_response.response.text}"
                    )

                format_id = format_response.data.id
                logger.info("Created new format with ID: %s", format_id)
            except Exception as e:
                logger.error("Error creating format: %s", str(e))
                raise

        result["format_id"] = format_id

        # STEP 3: Get or create file set
        file_set_id = None
        file_sets_response = self.client.files().get_asset_filesets(asset_id)

        if file_sets_response.response.ok and file_sets_response.data.objects:
            for file_set in file_sets_response.data.objects:
                # Match file set by base directory, storage ID, and format
                if (
                    file_set.base_dir == directory_path
                    and file_set.storage_id == self.storage_id
                    and file_set.format_id == format_id
                    and file_set.status == "ACTIVE"
                ):
                    file_set_id = file_set.id
                    logger.info(
                        "Found existing file set with ID: %s", file_set_id
                    )
                    file_set_existed_before = True
                    break

        if not file_set_id:
            try:
                # Get format components if available
                component_ids = []
                if format_response.response.ok and hasattr(
                    format_response.data, 'components'
                ) and format_response.data.components:
                    component_ids = [
                        comp.id
                        for comp in format_response.data.components
                        if hasattr(comp, 'id')
                    ]

                file_set_model = {
                    'name': file_name,
                    'format_id': format_id,
                    'storage_id': self.storage_id,
                    'base_dir': directory_path,
                    'component_ids': []
                }

                # Only add component_ids if we actually have some
                if component_ids:
                    file_set_model['component_ids'].append(component_ids)

                logger.debug("FileSetSchema: %s", file_set_model)

                file_set_response = self.client.files().create_asset_file_sets(
                    asset_id, body=file_set_model
                )
                if not file_set_response.response.ok:
                    raise GeneralException(
                        f"Failed to create file set: {file_set_response.response.text}"
                    )

                file_set_id = file_set_response.data.id
                logger.info("Created new file set with ID: %s", file_set_id)
            except Exception as e:
                logger.error("Error creating file set: %s", str(e))
                raise

        result["file_set_id"] = file_set_id

        # STEP 4: Get or create file
        file_id = None
        if existing_file and existing_file['file_set_id'] == file_set_id:
            file_id = existing_file['id']
            logger.info("Using existing file with ID: %s", file_id)
            file_existed_before = True
        else:
            # Check if file already exists
            files_response = self.client.files().get_asset_files(asset_id)

            if files_response.response.ok and files_response.data.objects:
                for file_obj in files_response.data.objects:
                    if (
                        file_obj.file_set_id == file_set_id
                        and file_obj.format_id == format_id
                        and file_obj.name == file_name
                    ):
                        file_id = file_obj.id
                        logger.info("Found existing file with ID: %s", file_id)
                        file_existed_before = True
                        break

        if not file_id:
            try:
                file_model = FileCreate(
                    name=file_name,
                    original_name=file_name,
                    directory_path=directory_path,
                    file_set_id=file_set_id,
                    format_id=format_id,
                    storage_id=self.storage_id,
                    size=file_size,
                    type=FileType.FILE,
                    status=FileStatus.OPEN,
                    checksum=file_checksum
                )

                file_response = self.client.files().create_asset_file(
                    asset_id, body=file_model
                )
                if not file_response.response.ok:
                    raise GeneralException(
                        f"Failed to create file: {file_response.response.text}"
                    )

                file_id = file_response.data.id
                logger.info("Created new file with ID: %s", file_id)

                # Close the file
                update_data = {"status": "CLOSED"}
                close_response = self.client.files().partial_update_asset_file(
                    asset_id, file_id, body=update_data
                )

                if not close_response.response.ok:
                    logger.warning(
                        "Failed to close file: %s", close_response.response.text
                    )
            except Exception as e:
                logger.error("Error creating file: %s", str(e))
                raise

        result["file_id"] = file_id

        # STEP 5: Apply metadata if view_id is provided and no metadata exists
        if metadata_view_id and metadata:
            # Check if metadata already exists
            metadata_exists = self.has_metadata(asset_id, metadata_view_id)

            if metadata_exists:
                logger.info(
                    "Metadata already exists for asset ID: %s with view ID: %s, skipping update",
                    asset_id, metadata_view_id
                )
                result["metadata_applied"] = False
            else:
                try:
                    metadata_values = MetadataValues(
                        root=metadata.get('metadata_values')
                    )
                    logger.debug("metadata_values: %s", metadata_values)

                    # Update metadata
                    metadata_update = UpdateMetadata(
                        metadata_values=metadata_values
                    )
                    metadata_response = self.client.metadata(
                    ).update_asset_metadata(
                        asset_id=asset_id,
                        view_id=metadata_view_id,
                        metadata=metadata_update
                    )

                    if not metadata_response.response.ok:
                        logger.warning(
                            "Failed to update metadata: %s",
                            metadata_response.response.text
                        )
                    else:
                        logger.info(
                            "Applied metadata to asset with view ID: %s",
                            metadata_view_id
                        )
                    result["metadata_applied"] = metadata_response.response.ok

                except Exception as e:
                    logger.error("Error applying metadata: %s", str(e))
                    result["metadata_applied"] = False

        # STEP 6: Add to collections if specified
        if collection_ids:
            added_collections = []

            for collection_id in collection_ids:
                try:
                    # Add asset to collection
                    collection_url = self.client.assets(
                    ).gen_url(f"collections/{collection_id}/contents/")
                    logger.debug(collection_url)

                    collection_body = {
                        "object_id": asset_id,
                        "object_type": "assets"
                    }
                    response = self.client.session.post(
                        collection_url, json=collection_body
                    )

                    if response.ok:
                        added_collections.append(collection_id)
                        logger.info(
                            "Added asset to collection: %s", collection_id
                        )
                    else:
                        logger.warning(
                            "Failed to add asset to collection %s: %s",
                            collection_id, response.text
                        )
                except Exception as e:
                    logger.error(
                        "Error adding to collection %s: %s", collection_id,
                        str(e)
                    )
            result["added_collections"] = added_collections

        # STEP 7: Trigger metadata extraction and proxy generation if needed
        transcode_ignore = self.storage_settings.get('transcode_ignore', [])
        skip_transcoding = False

        for pattern in transcode_ignore:
            if pattern.startswith('*') and file_name.endswith(pattern[1:]):
                skip_transcoding = True
                break

        # Check if file already has transcoding history or existing proxies/mediainfo
        if not skip_transcoding:
            # Check if mediainfo extraction is needed
            mediainfo_exists = self.has_mediainfo(asset_id, file_id)
            logger.debug("mediainfo_exists: %s", mediainfo_exists)

            proxies_exist = self.has_proxies(asset_id)
            logger.debug("proxies_exist: %s", proxies_exist)

            keyframes_exist = self.has_keyframes(asset_id)
            logger.debug("keyframes_exist: %s", keyframes_exist)

            has_transcode_history = self.has_transcoding_history(asset_id)
            logger.debug("has_transcode_history: %s", has_transcode_history)

            if not mediainfo_exists and not has_transcode_history:
                # MediaInfo extraction
                try:
                    mediainfo_url = self.client.files(
                    ).gen_url(f"assets/{asset_id}/files/{file_id}/mediainfo")
                    logger.debug("mediainfo_url: %s", mediainfo_url)

                    mediainfo_payload = {"priority": 5}
                    mediainfo_response = self.client.session.post(
                        mediainfo_url, json=mediainfo_payload
                    )

                    if mediainfo_response.ok:
                        logger.info(
                            "Triggered mediainfo extraction for file ID: %s",
                            file_id
                        )
                        result["mediainfo_job"] = True
                    else:
                        logger.warning(
                            "Failed to trigger mediainfo extraction: %s",
                            mediainfo_response.text
                        )
                        result["mediainfo_job"] = False

                except Exception as e:
                    logger.error(
                        "Error triggering mediainfo extraction: %s", str(e)
                    )
                    result["mediainfo_job"] = False
            else:
                logger.info(
                    "Mediainfo already exists for file ID: %s, skipping extraction",
                    file_id
                )
                result["mediainfo_job"] = "skipped"

            # STEP 8: Proxy and keyframe generation based on storage settings
            if not proxies_exist and not keyframes_exist and not has_transcode_history:
                if self.storage_settings.get('local_proxy_creation', False):
                    # TODO: In a real implementation, you would handle local
                    #  proxy generation here
                    logger.info(
                        "Local proxy creation enabled but not implemented"
                    )
                else:
                    # Server-side proxy generation
                    try:
                        proxy_url = self.client.files().gen_url(
                            f"assets/{asset_id}/files/{file_id}/keyframes"
                        )
                        logger.debug("proxy_url: %s", proxy_url)

                        proxy_payload = {"priority": 5}
                        proxy_response = self.client.session.post(
                            proxy_url, json=proxy_payload
                        )

                        if proxy_response.ok:
                            logger.info(
                                "Triggered proxy/keyframe generation for file ID: %s",
                                file_id
                            )
                            result["proxy_job"] = True
                        else:
                            logger.warning(
                                "Failed to trigger proxy/keyframe generation: %s",
                                proxy_response.text
                            )
                            result["proxy_job"] = False

                    except Exception as e:
                        logger.error(
                            "Error triggering proxy/keyframe generation: %s",
                            str(e)
                        )
                        result["proxy_job"] = False
            else:
                logger.info(
                    "Proxies or keyframes already exist for asset ID: %s, skipping generation",
                    asset_id
                )
                result["proxy_job"] = "skipped"
        else:
            logger.info(
                "Skipping transcoding for %s (matches transcode_ignore pattern)",
                file_name
            )
            result["transcoding_skipped"] = True

        # Create asset history record based on what happened
        operation_description = "Asset synchronized with external system via the API"
        operation_type = "CUSTOM"

        # Determine if we should use a more specific history entry
        if not asset_existed_before:
            operation_description = "Initial asset creation"
            operation_type = "VERSION_CREATE"
        elif not format_existed_before:
            operation_description = "Add format ORIGINAL"
            operation_type = "ADD_FORMAT"
        elif not file_set_existed_before:
            operation_description = "File set added to asset"
            operation_type = "MODIFY_FILESET"
        elif not file_existed_before:
            operation_description = "File added to asset"
            operation_type = "MODIFY_FILESET"

        try:
            history_url = self.client.assets(
            ).gen_url(f"assets/{asset_id}/history/")
            logger.debug("history_url: %s", history_url)

            history_body = {
                "operation_description": operation_description,
                "operation_type": operation_type
            }
            history_response = self.client.session.post(
                history_url, json=history_body
            )

            if history_response.ok:
                logger.info("Created history record for asset: %s", asset_id)
                result["history_created"] = True
                result["history_operation_type"] = operation_type
            else:
                logger.warning(
                    "Failed to create history record: %s", history_response.text
                )
                result["history_created"] = False

        except Exception as e:
            logger.error("Error creating history record: %s", str(e))
            result["history_created"] = False

        return result

    def _apply_acls(self, asset_id: str) -> bool:
        """
        Apply access control settings based on storage configuration.

        Args:
            asset_id: Asset ID to apply ACLs to

        Returns:
            True if successful, False otherwise
        """
        acl_template_id = self.storage_settings.get("acl_template_id")
        logger.debug("acl_template_id: %s", acl_template_id)

        access_group_id = self.storage_settings.get("access_group_id")
        logger.debug("access_group_id: %s", access_group_id)

        if acl_template_id:
            try:
                # TODO: Apply template permissions to an object. From docs,
                #  should be `POST /API/acls/v1/acl/templates/{template_id}/{object_type}/{object_key}/`
                # Apply template
                # template_url = self.client.assets(
                # ).gen_url(f"acl_templates/{acl_template_id}/apply/{asset_id}")
                template_url = f"{self.client.base_url}/API/acls/v1/acl/templates/{acl_template_id}/asset/{asset_id}/"
                logger.debug("template_url: %s", template_url)

                response = self.client.session.post(template_url)

                if response.ok:
                    logger.info(
                        "Applied ACL template %s to asset %s", acl_template_id,
                        asset_id
                    )

                    return True
                logger.warning(
                    "Failed to apply ACL template: %s", response.text
                )
            except Exception as e:
                logger.error("Error applying ACL template: %s", str(e))

        elif access_group_id:
            try:
                # TODO: Update or create group acl for an object. From docs,
                #  should be `PUT /API/acls/v1/groups/{group_id}/acl/{object_type}/{object_key}/`
                # Apply group access
                # acl_url = self.client.assets(
                # ).gen_url(f"groups/{access_group_id}/acl/assets/{asset_id}/")
                acl_url = f"{self.client.base_url}/API/acls/v1/groups/{access_group_id}/acl/assets/{asset_id}/"
                logger.debug("acl_url: %s", acl_url)

                response = self.client.session.put(acl_url, json={})

                if response.ok:
                    logger.info(
                        "Applied access group %s to asset %s", access_group_id,
                        asset_id
                    )

                    return True
                logger.warning(
                    "Failed to apply access group: %s", response.text
                )
            except Exception as e:
                logger.error("Error applying access group: %s", str(e))

        return False


# Example usage
def main():
    """Example usage of the IconikStorageGatewayRecipe."""
    if os.environ.get("LOG_LEVEL", os.environ.get("PYTHON_LOG_LEVEL",
                                                  "INFO")).upper() == "DEBUG":
        logger.setLevel(logging.DEBUG)
        logging.debug("Debug logging is enabled")

    # Initialize client
    app_id = os.environ.get("APP_ID", os.environ.get("ICONIK_APP_ID"))
    auth_token = os.environ.get(
        "AUTH_TOKEN", os.environ.get("ICONIK_AUTH_TOKEN")
    )
    storage_id = os.environ.get(
        "STORAGE_ID", os.environ.get("ICONIK_STORAGE_ID")
    )
    client = PythonikClient(
        app_id=app_id,
        auth_token=auth_token,
        timeout=60,
        base_url="https://app.iconik.io"
    )

    # Initialize recipe
    recipe = IconikStorageGatewayRecipe(client, storage_id)

    # Create an asset
    file_path = os.environ.get("FILE_PATH")

    # Use suppress_stdout from pythonikext to hide verbose output
    with suppress_stdout():
        try:
            result = recipe.create_asset(file_path=file_path)

            print("Asset creation complete!")
            print(f"Asset ID: {result['asset_id']}")
            print(f"Format ID: {result['format_id']}")
            print(f"File Set ID: {result['file_set_id']}")
            print(f"File ID: {result['file_id']}")

            if result.get("mediainfo_job") == "skipped":
                print("Mediainfo extraction skipped - already exists")
            elif result.get("mediainfo_job") is True:
                print("Mediainfo extraction triggered")

            if result.get("proxy_job") == "skipped":
                print("Proxy/keyframe generation skipped - already exists")
            elif result.get("proxy_job") is True:
                print("Proxy/keyframe generation triggered")

            if result.get("transcoding_skipped"):
                print("Transcoding skipped - file matches ignore pattern")

            if result.get("history_created"):
                print(
                    f"History created with operation type: {result.get('history_operation_type', 'CUSTOM')}"
                )

        except Exception as e:
            print(f"Error creating asset: {str(e)}")


if __name__ == "__main__":
    main()
