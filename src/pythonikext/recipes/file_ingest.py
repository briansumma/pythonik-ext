"""
File ingest recipe for pythonik-ext
"""
import argparse
import fnmatch
import json
import logging
import mimetypes
import os
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pythonik.models.assets.assets import AssetCreate
from pythonik.models.base import PaginatedResponse
from pythonik.models.files.file import FileCreate, FileStatus, FileType
from pythonik.models.files.format import FormatCreate
from pythonik.models.mutation.metadata.mutate import (
    MetadataValues,
    UpdateMetadata,
)

from .._internal_utils import get_attribute, normalize_pattern
from .._logging import get_logger
from ..client import ExtendedPythonikClient as PythonikClient
from ..exceptions import GeneralException
from ..specs.assets import ExtendedAssetSpec as AssetSpec
from ..specs.assets import ExtendedSpecBase
from ..utils import calculate_md5
from .collection_directory_mapping import CollectionDirectoryMappingRecipe


logger = get_logger(__name__)


class FileIngestRecipe:
    """
    Recipe for creating assets in iconik that mirrors ISG behavior.
    Handles all steps of asset creation with intelligent retry/resume.
    """

    def __init__(
        self,
        client: PythonikClient,
        storage_id: str,
        default_view_id: Optional[str] = None,
        mount_mapping: Optional[str] = None
    ):
        """
        Initialize the recipe with client and storage info.

        Args:
            client: Configured PythonikClient instance
            storage_id: ID of the storage to use
            default_view_id: Optional default metadata view ID
            mount_mapping: Optional mount point mapping in format
                "local_path:remote_path"
        """
        self.client = client
        self.storage_id = storage_id
        self.default_view_id = default_view_id

        self._storage_settings = None
        self._storage_mount_point = None

        self.local_path = None
        self.remote_path = None

        if mount_mapping:
            parts = mount_mapping.split(':')
            if len(parts) == 2:
                self.local_path = parts[0]
                self.remote_path = parts[1]
                logger.info(
                    "Mount mapping configured: %s -> %s", self.local_path,
                    self.remote_path
                )
            else:
                logger.warning(
                    "Invalid mount mapping format: %s. Expected format: "
                    "local_path:remote_path", mount_mapping
                )

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

    def map_file_path(self, file_path: str) -> str:
        """
        Map local file path to remote path if mount mapping is configured.

        Args:
            file_path: Local file path

        Returns:
            Mapped file path for storage
        """
        abs_path = os.path.abspath(file_path)

        if self.local_path and self.remote_path and abs_path.startswith(
            self.local_path
        ):
            mapped_path = abs_path.replace(self.local_path, self.remote_path, 1)
            logger.debug("Mapped file path: %s -> %s", abs_path, mapped_path)
            return mapped_path

        return abs_path

    def check_for_duplicate_files(self, checksum_or_file: str) -> List[Dict]:
        """
        Check for duplicate files by checksum.

        Args:
            checksum_or_file: Either an MD5 checksum string or a path to a file

        Returns:
            List of file objects with the same checksum
        """
        try:
            response = self.client.files(
            ).get_files_by_checksum(checksum_or_file)

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
        file_stem, _ = os.path.splitext(file_path)
        logger.debug("file_stem: %s", file_stem)

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
                            logger.warning(
                                "XML sidecar detected but not currently supported"
                            )
                            return None
                        if sidecar_ext.upper() in ["CSV", ".CSV"]:
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

                if value is None:
                    continue

                values = value if isinstance(value, list) and multi else [value]

                for field_value in values:
                    if field_value is None:
                        continue

                    if field_type == "boolean":
                        if isinstance(field_value, bool):
                            field_value = str(field_value).lower()
                        elif isinstance(field_value, str):
                            field_value = str(
                                field_value.lower() in
                                ['y', 'yes', 't', 'true', 'on', '1']
                            ).lower()

                    elif field_type == "date" and isinstance(field_value, str):
                        try:
                            dt = datetime.fromisoformat(
                                field_value.replace('Z', '+00:00')
                            )
                            field_value = dt.strftime('%Y-%m-%d')
                        except ValueError:
                            pass

                    if field_value is not None:
                        metadata_values[field_name]["field_values"].append({
                            "value": field_value
                        })

        except Exception as e:
            logger.error("Error formatting metadata: %s", str(e))

        return metadata_values

    def has_been_deleted(self, object_id: str, object_type: str) -> bool:
        """
        Check if an object has been deleted but not yet purged.

        Args:
            object_id: Object ID
            object_type: Object Type, i.e., assets, collections, formats, or
                file_sets

        Returns:
            True if the object has been deleted (in trash), False otherwise
        """
        supported_object_types = [
            "assets", "collections", "formats", "file_sets"
        ]
        if object_type not in supported_object_types:
            raise ValueError(
                f"object_type must be one of: {supported_object_types}"
            )

        object_response = None
        if object_type == "assets":
            object_response = self.client.assets().get(object_id)
        elif object_type == "collections":
            object_response = self.client.collections().get(object_id)
        else:
            params = {"id": object_id}
            delete_queue_url = self.client.files(
            ).gen_url(f"delete_queue/{object_type}/")
            response = self.client.session.get(delete_queue_url, params=params)
            object_response = ExtendedSpecBase.parse_response(response)

        if object_response and object_response.response.ok:
            object_ = get_attribute(object_response, "data")
            is_deleted = get_attribute(object_, "status") in ["DELETED"]
            if is_deleted:
                logger.debug("Asset %s has been deleted", object_id)
            return is_deleted

        return False

    def has_mediainfo(self, asset_id: str, file_id: str) -> bool:
        """
        Check if mediainfo extraction has already been run.

        Args:
            asset_id: Asset ID
            file_id: File ID

        Returns:
            True if mediainfo exists, False otherwise
        """

        if self.has_been_deleted(asset_id, "assets"):
            return False

        try:
            file_response = self.client.files().get_asset_file(
                asset_id, file_id
            )
            if file_response.response.ok:
                format_id = file_response.data.format_id

                component_url = self.client.files(
                ).gen_url(f"assets/{asset_id}/formats/{format_id}/components/")
                logger.debug("component_url: %s", component_url)

                response = self.client.session.get(component_url)

                return response.ok and len(
                    response.json().get('objects', [])
                ) > 0

            logger.debug("No mediainfo found for file %s", file_id)
            return False
        except Exception as e:
            logger.error("Error checking mediainfo status: %s", str(e))
            return False

    def has_proxies(self, asset_id: str) -> bool:
        """
        Check if proxies already exist for this asset.

        Args:
            asset_id: Asset ID

        Returns:
            True if proxies exist, False otherwise
        """

        if self.has_been_deleted(asset_id, "assets"):
            return False

        try:
            proxy_response = self.client.files().get_asset_proxies(asset_id)

            return proxy_response.response.ok and len(
                proxy_response.data.objects
            ) > 0
        except Exception as e:
            logger.error("Error checking proxy status: %s", str(e))
            return False

    def has_keyframes(self, asset_id: str) -> bool:
        """
        Check if keyframes already exist for this asset.

        Args:
            asset_id: Asset ID

        Returns:
            True if keyframes exist, False otherwise
        """

        if self.has_been_deleted(asset_id, "assets"):
            return False

        try:
            keyframes_response = self.client.files(
            ).get_asset_keyframes(asset_id)

            return keyframes_response.response.ok and len(
                keyframes_response.data.objects
            ) > 0
        except Exception as e:
            logger.error("Error checking keyframes status: %s", str(e))
            return False

    def has_transcoding_history(self, asset_id: str) -> bool:
        """
        Check if there's already a transcoding history entry.

        Args:
            asset_id: Asset ID

        Returns:
            True if transcoding history exists, False otherwise
        """

        if self.has_been_deleted(asset_id, "assets"):
            return False

        try:
            history_url = self.client.assets(
            ).gen_url(f"assets/{asset_id}/history/")
            response = self.client.session.get(history_url)

            if response.ok:
                history_entries = response.json().get('objects', [])
                for entry in history_entries:
                    if entry.get('operation_type') == 'TRANSCODE':
                        return True
            return False
        except Exception as e:
            logger.error("Error checking history: %s", str(e))
            return False

    def has_mediainfo_metadata_history(self, asset_id: str) -> bool:
        """
        Check if there's already a metadata history entry whose user ID matches
        the system ID.

        Args:
            asset_id: Asset ID

        Returns:
            True if transcoding history exists, False otherwise
        """

        if self.has_been_deleted(asset_id, "assets"):
            return False

        try:
            history_url = self.client.assets(
            ).gen_url(f"assets/{asset_id}/history/")
            response = self.client.session.get(history_url)

            if response.ok:
                history_entries = response.json().get('objects', [])
                for entry in history_entries:
                    if entry.get('operation_type') == 'METADATA' and entry.get(
                        'system_domain_id'
                    ) == entry.get('user_id'):
                        return True
            return False
        except Exception as e:
            logger.error("Error checking history: %s", str(e))
            return False

    def has_metadata(
        self, asset_id: str, view_id: Optional[str] = None
    ) -> bool:
        """
        Check if metadata already exists for this asset and view.

        Args:
            asset_id: Asset ID
            view_id: Optional metadata view ID (if None, checks directly)

        Returns:
            True if metadata exists, False otherwise
        """

        if self.has_been_deleted(asset_id, "assets"):
            return False

        try:
            metadata_url = self.client.metadata().gen_url(
                f"assets/{asset_id}/views/{view_id}"
            ) if view_id else self.client.metadata(
            ).gen_url(f"assets/{asset_id}/")
            response = self.client.session.get(metadata_url)

            if response.ok:
                metadata = response.json()
                metadata_values = metadata.get(
                    'metadata_values', {}
                ) if view_id else metadata
                logger.debug(
                    "metadata_values: %s",
                    json.dumps(metadata_values, indent=4)
                )

                for field_values in metadata_values.values():
                    values = field_values.get(
                        'field_values', []
                    ) if view_id else field_values.get('values', [])
                    if values and len(values) > 0:
                        return True

            return False
        except Exception as e:
            logger.error("Error checking metadata status: %s", str(e))
            return False

    def _check_file_validity(
        self,
        file_path: str,
        md5sum: Optional[str] = None,
        allow_offline: bool = False
    ) -> Dict[str, Any]:
        """
        Check file validity and gather basic information.

        Args:
            file_path: Path to the file
            md5sum: Optional pre-calculated MD5 checksum to use
            allow_offline: Whether to allow files that are not accessible

        Returns:
            Dictionary with file info

        Raises:
            FileNotFoundError: If the file does not exist and allow_offline is
                False
            ValueError: If the file matches a scan_ignore pattern
        """
        file_checksum = md5sum
        file_size = 0
        file_exists = os.path.exists(file_path)

        if file_exists:
            logger.debug("File exists: %s", file_path)
            if not md5sum:
                file_checksum = calculate_md5(file_path)
                logger.debug("Calculated MD5 checksum: %s", file_checksum)
            file_size = os.path.getsize(file_path)
            logger.debug("File size: %s bytes", file_size)
        elif not allow_offline:
            logger.error(
                "File does not exist and allow_offline is False: %s", file_path
            )
            raise FileNotFoundError(f"File not found: {file_path}")
        else:
            logger.info(
                "File does not exist but allow_offline is True: %s", file_path
            )
            if not md5sum:
                logger.warning(
                    "No MD5 checksum provided for offline file. Using empty string."
                )
                file_checksum = ""

        file_name = os.path.basename(file_path)
        file_stem, file_ext = os.path.splitext(file_name)
        title_includes_extension = self.storage_settings.get(
            'title_includes_extension', True
        )
        title = file_name if title_includes_extension else file_stem
        logger.debug("Title: %s", title)

        path_mapping = self.map_file_path(file_path)
        logger.debug("Path mapping: %s", path_mapping)

        directory_path = os.path.dirname(path_mapping)
        if directory_path.startswith(self.mount_point):
            directory_path = directory_path[len(self.mount_point):].lstrip('/')
        logger.debug("Directory path: %s", directory_path)

        mime_type, _ = mimetypes.guess_type(file_name)
        logger.debug("MIME type: %s", mime_type)

        scan_include = self.storage_settings.get('scan_include', [])
        scan_ignore = self.storage_settings.get('scan_ignore', [])
        logger.debug("Scan include patterns: %s", scan_include)
        logger.debug("Scan ignore patterns: %s", scan_ignore)

        if scan_include:
            include_match = False
            for pattern in scan_include:
                if pattern.startswith('re:/') and pattern.endswith('/'):
                    regex = pattern.lstrip('re:/').rstrip('/')
                    logger.debug(
                        "Checking scan_include regex pattern: %s", regex
                    )
                    if re.search(regex, file_path) or re.search(
                        normalize_pattern(regex), file_path
                    ):
                        include_match = True
                        logger.debug(
                            "File matches scan_include regex pattern: %s",
                            pattern
                        )
                        break
                else:
                    logger.debug(
                        "Checking scan_include wildcard pattern: %s", pattern
                    )
                    if fnmatch.fnmatch(file_path, pattern):
                        include_match = True
                        logger.debug(
                            "File matches scan_include wildcard pattern: %s",
                            pattern
                        )
                        break

            if not include_match:
                logger.warning(
                    "File does not match any scan_include pattern: %s",
                    scan_include
                )
                raise ValueError(
                    f"File does not match any scan_include pattern: {scan_include}"
                )

        for pattern in scan_ignore:
            if pattern.startswith('re:/') and pattern.endswith('/'):
                regex = pattern.lstrip('re:/').rstrip('/')
                logger.debug("Checking scan_ignore regex pattern: %s", regex)
                if re.search(regex, file_path) or re.search(
                    normalize_pattern(regex), file_path
                ):
                    logger.warning(
                        "File matches scan_ignore regex pattern: %s", pattern
                    )
                    raise ValueError(
                        f"File matches scan_ignore pattern: {pattern}"
                    )
            else:
                logger.debug(
                    "Checking scan_ignore wildcard pattern: %s", pattern
                )
                if fnmatch.fnmatch(file_path, pattern):
                    logger.warning(
                        "File matches scan_ignore wildcard pattern: %s", pattern
                    )
                    raise ValueError(
                        f"File matches scan_ignore pattern: {pattern}"
                    )

        sidecar_metadata_required = self.storage_settings.get(
            'sidecar_metadata_required', False
        )
        logger.debug("Sidecar metadata required: %s", sidecar_metadata_required)

        # Only check for sidecar if the file exists, or we're not allowing
        # offline files
        sidecar_metadata = None
        if file_exists or not allow_offline:
            sidecar_metadata = self.check_for_sidecar_metadata(
                file_path
            ) if sidecar_metadata_required else None

            if sidecar_metadata_required and sidecar_metadata is None:
                logger.warning("Sidecar metadata required but not found")
                raise ValueError("Sidecar metadata required but not found")

        return {
            "storage_id": self.storage_id,
            "file_path": file_path,
            "title": title,
            "size": file_size,
            "file_name": file_name,
            "file_stem": file_stem,
            "file_extension": file_ext,
            "mime_type": mime_type,
            "directory_path": directory_path,
            "file_checksum": file_checksum,
            "sidecar_metadata": sidecar_metadata,
            "path_mapping": path_mapping,
            "file_exists": file_exists
        }

    def _resolve_external_id(self, file_info: Dict[str, Any]) -> str:
        """
        Resolve external ID based on settings and file info.

        Args:
            file_info: Dictionary with file information

        Returns:
            External ID string
        """
        if self.storage_settings.get('filename_is_external_id', False):
            external_id = get_attribute(file_info, "file_name")
        else:
            file_path = get_attribute(file_info, "file_path")
            external_id = file_path

        logger.debug("external_id: %s", external_id)
        return external_id

    @staticmethod
    def _merge_metadata(
        metadata: Optional[Dict], sidecar_metadata: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Merge provided metadata with sidecar metadata.

        Args:
            metadata: Provided metadata dictionary
            sidecar_metadata: Sidecar metadata dictionary

        Returns:
            Merged metadata dictionary or None
        """
        if not sidecar_metadata:
            return metadata

        if metadata:
            merged_metadata = {**sidecar_metadata, **metadata}
            logger.info("Merged metadata with metadata sidecar")
            logger.debug(
                "merged_metadata: %s", json.dumps(merged_metadata, indent=4)
            )
            return merged_metadata
        return sidecar_metadata

    def _find_existing_asset(
        self, external_id: str, file_info: Dict[str, Any]
    ) -> Tuple[Optional[str], bool]:
        """
        Find existing asset by checksum or external ID.

        Args:
            external_id: External ID
            file_info: Dictionary with file information

        Returns:
            Tuple of (asset_id, asset_existed_before)
        """
        aggregate_identical = self.storage_settings.get(
            'aggregate_identical_files', False
        )
        aggregate_only_same_storage = self.storage_settings.get(
            'aggregate_only_on_same_storage', False
        )

        file_checksum = get_attribute(file_info, "file_checksum")
        if aggregate_identical and file_checksum:
            duplicate_files = self.check_for_duplicate_files(file_checksum)

            if duplicate_files:
                for file_obj in duplicate_files:
                    if aggregate_only_same_storage and get_attribute(
                        file_obj, "storage_id"
                    ) != self.storage_id:
                        continue

                    asset_id = get_attribute(file_obj, "asset_id")
                    if self.has_been_deleted(asset_id, "assets"):
                        logger.debug("Asset %s has been deleted", asset_id)
                        continue

                    logger.info("Found existing asset with ID: %s", asset_id)
                    return asset_id, True

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
                asset_id = get_attribute(asset, "id")
                if self.has_been_deleted(asset_id, "assets"):
                    logger.debug(
                        "Asset with external ID %s has been deleted",
                        external_id
                    )
                    return None, False
                logger.info(
                    "Found existing asset with external ID %s: %s", external_id,
                    asset_id
                )
                return asset_id, True
        except Exception as e:
            logger.warning("Error looking up asset by external ID: %s", str(e))

        return None, False

    def _create_new_asset(
        self, file_info: Dict[str, Any], external_id: str
    ) -> str:
        """
        Create a new asset.

        Args:
            file_info: Dictionary with file information
            external_id: External ID

        Returns:
            Newly created asset ID

        Raises:
            GeneralException: If asset creation fails
        """
        try:
            apply_default_acls = not (
                self.storage_settings.get("acl_template_id")
                or self.storage_settings.get("access_group_id")
            )

            asset_model = AssetCreate(
                title=file_info["title"],
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

            self._apply_acls(asset_id)

            return asset_id
        except Exception as e:
            logger.error("Error creating asset: %s", str(e))
            raise

    def _ensure_format(self, asset_id: str) -> Tuple[str, bool]:
        """
        Ensure the format exists, creating it if necessary.

        Args:
            asset_id: Asset ID

        Returns:
            Tuple of (format_id, format_existed_before)

        Raises:
            GeneralException: If format creation fails
        """
        format_id = None
        format_existed_before = False

        format_response = None
        if not self.has_been_deleted(asset_id, "assets"):
            format_response = self.client.files().get_asset_formats(asset_id)

        if format_response and format_response.response.ok and format_response.data.objects:
            for format_obj in format_response.data.objects:
                if get_attribute(format_obj,
                                 "name") == "ORIGINAL" and get_attribute(
                                     format_obj, "status"
                                 ) == "ACTIVE":
                    format_id = get_attribute(format_obj, "id")
                    if self.has_been_deleted(format_id, "formats"):
                        logger.debug("Format %s has been deleted", format_id)
                        break
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

        return format_id, format_existed_before

    def _ensure_file_set(
        self, asset_id: str, format_id: str, file_info: Dict[str, Any]
    ) -> Tuple[str, bool]:
        """
        Ensure the file set exists, creating it if necessary.

        Args:
            asset_id: Asset ID
            format_id: Format ID
            file_info: Dictionary with file information

        Returns:
            Tuple of (file_set_id, file_set_existed_before)

        Raises:
            GeneralException: If file set creation fails
        """
        file_set_id = None
        file_set_existed_before = False

        file_sets_response = None
        if not self.has_been_deleted(asset_id, "assets"):
            file_sets_response = self.client.files(
            ).get_asset_filesets(asset_id)

        if file_sets_response and file_sets_response.response.ok and file_sets_response.data.objects:
            for file_set in file_sets_response.data.objects:
                if (
                    get_attribute(file_set, "base_dir")
                    == get_attribute(file_info, "directory_path")
                    and get_attribute(file_set, "storage_id") == self.storage_id
                    and get_attribute(file_set, "format_id") == format_id
                    and get_attribute(file_set, "status") == "ACTIVE"
                ):
                    file_set_id = get_attribute(file_set, "id")
                    if self.has_been_deleted(file_set_id, "file_sets"):
                        logger.debug("File set %s has been deleted", format_id)
                        break
                    logger.info(
                        "Found existing file set with ID: %s", file_set_id
                    )
                    file_set_existed_before = True
                    break

        if not file_set_id:
            try:
                component_ids = []
                if hasattr(file_sets_response, 'data') and hasattr(
                    file_sets_response.data, 'components'
                ) and file_sets_response.data.components:
                    component_ids = [
                        get_attribute(comp, "id")
                        for comp in file_sets_response.data.components
                        if hasattr(comp, 'id')
                    ]

                file_set_model = {
                    'name': get_attribute(file_info, "file_name"),
                    'format_id': format_id,
                    'storage_id': self.storage_id,
                    'base_dir': get_attribute(file_info, "directory_path"),
                    'component_ids': []
                }

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

        return file_set_id, file_set_existed_before

    def _ensure_file(
        self, asset_id: str, format_id: str, file_set_id: str,
        file_info: Dict[str, Any]
    ) -> Tuple[str, bool]:
        """
        Ensure the file exists, creating it if necessary.

        Args:
            asset_id: Asset ID
            format_id: Format ID
            file_set_id: File set ID
            file_info: Dictionary with file information

        Returns:
            Tuple of (file_id, file_existed_before)

        Raises:
            GeneralException: If file creation fails
        """
        file_id = None
        file_existed_before = False

        files_response = None
        if not self.has_been_deleted(asset_id, "assets"):
            files_response = self.client.files().get_asset_files(asset_id)

        if files_response and files_response.response.ok and files_response.data.objects:
            for file_obj in files_response.data.objects:
                if (
                    get_attribute(file_obj, "file_set_id") == file_set_id
                    and get_attribute(file_obj, "format_id") == format_id
                    and get_attribute(file_obj, "name")
                    == get_attribute(file_info, "file_name")
                ):
                    file_id = get_attribute(file_obj, "id")
                    if self.has_been_deleted(file_set_id, "file_sets"):
                        logger.debug("File %s has been deleted", file_id)
                        break
                    logger.info("Found existing file with ID: %s", file_id)
                    file_existed_before = True
                    break

        if not file_id:
            try:
                file_model = FileCreate(
                    name=get_attribute(file_info, "file_name"),
                    original_name=get_attribute(file_info, "file_name"),
                    directory_path=get_attribute(file_info, "directory_path"),
                    file_set_id=file_set_id,
                    format_id=format_id,
                    storage_id=self.storage_id,
                    size=get_attribute(file_info, "size"),
                    type=FileType.FILE,
                    status=FileStatus.OPEN,
                    checksum=get_attribute(file_info, "file_checksum")
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

        return file_id, file_existed_before

    def _apply_metadata(
        self,
        asset_id: str,
        metadata: Dict,
        view_id: Optional[str] = None
    ) -> bool:
        """
        Apply metadata to the asset.

        Args:
            asset_id: Asset ID
            metadata: Metadata to apply
            view_id: Optional view ID (if None, use direct method)

        Returns:
            True if metadata was applied successfully, False otherwise
        """
        metadata_view_id = view_id or self.default_view_id or self.storage_settings.get(
            'metadata_view_id'
        )
        logger.debug("metadata_view_id: %s", metadata_view_id)

        metadata_values = MetadataValues(root=metadata.get('metadata_values'))
        metadata_update = UpdateMetadata(metadata_values=metadata_values)
        metadata_exists = self.has_metadata(asset_id, metadata_view_id)

        if metadata_exists:
            logger.info(
                "Metadata already exists for asset ID: %s with view ID: %s, skipping update",
                asset_id, metadata_view_id
            )
            return False

        if not metadata_view_id:
            try:
                metadata_response = self.client.metadata().put_metadata_direct(
                    object_type="assets",
                    object_id=asset_id,
                    metadata=metadata_update
                )

                if not metadata_response.response.ok:
                    logger.warning(
                        "Failed to update metadata: %s",
                        metadata_response.response.text
                    )
                    return False
                logger.info("Applied metadata to asset successfully")
                return True

            except Exception as e:
                logger.error("Error applying metadata: %s", str(e))
                return False

        try:
            metadata_response = self.client.metadata().update_asset_metadata(
                asset_id=asset_id,
                view_id=metadata_view_id,
                metadata=metadata_update
            )

            if not metadata_response.response.ok:
                logger.warning(
                    "Failed to update metadata: %s",
                    metadata_response.response.text
                )
                return False
            logger.info(
                "Applied metadata to asset with view ID: %s", metadata_view_id
            )
            return True

        except Exception as e:
            logger.error("Error applying metadata: %s", str(e))
            return False

    def _add_to_collections(self, asset_id: str, collection_ids: List[str]) -> \
            List[str]:
        """
        Add asset to collections.

        Args:
            asset_id: Asset ID
            collection_ids: List of collection IDs

        Returns:
            List of collection IDs that were successfully added
        """
        added_collections = []

        for collection_id in collection_ids:
            try:
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
                    logger.info("Added asset to collection: %s", collection_id)
                else:
                    logger.warning(
                        "Failed to add asset to collection %s: %s",
                        collection_id, response.text
                    )
            except Exception as e:
                logger.error(
                    "Error adding to collection %s: %s", collection_id, str(e)
                )

        return added_collections

    def _trigger_transcoding(
        self,
        asset_id: str,
        file_id: str,
        file_info: Dict[str, Any],
        allow_offline: bool = False
    ) -> Dict[str, Any]:
        """
        Trigger transcoding processes for the asset.

        Args:
            asset_id: Asset ID
            file_id: File ID
            file_info: File information dictionary
            allow_offline: Whether to skip transcoding for offline files

        Returns:
            Dictionary with results of transcoding operations
        """
        result: Dict[str, Any] = {}

        # Check if file exists/is online
        file_exists = get_attribute(file_info, "file_exists", True)
        if allow_offline and not file_exists:
            logger.info(
                "Skipping transcoding for offline file: %s",
                get_attribute(file_info, "file_name")
            )
            result["transcoding_skipped"] = True
            result["offline_file"] = True
            return result

        transcode_ignore = self.storage_settings.get('transcode_ignore', [])
        transcode_include = self.storage_settings.get('transcode_include', [])
        skip_transcoding = False
        must_include = False

        file_path = get_attribute(file_info, "file_path")

        if transcode_include:
            must_include = True
            for pattern in transcode_include:
                if pattern.startswith('re:/') and pattern.endswith('/'):
                    regex = pattern.lstrip('re:/').rstrip('/')
                    if re.search(regex, file_path):
                        logger.info(
                            "File matches transcode_include pattern: %s",
                            pattern
                        )
                        must_include = False
                        break
                    if re.search(normalize_pattern(regex), file_path):
                        logger.info(
                            "File matches transcode_include pattern: %s",
                            pattern
                        )
                        must_include = False
                        break
                else:
                    if fnmatch.fnmatch(file_path, pattern):
                        logger.info(
                            "File matches transcode_include pattern: %s",
                            pattern
                        )
                        must_include = False
                        break

        if must_include:
            logger.info(
                "File does not match any transcode_include pattern, skipping: %s",
                file_path
            )
            skip_transcoding = True
        else:
            for pattern in transcode_ignore:
                if pattern.startswith('re:/') and pattern.endswith('/'):
                    regex = pattern.lstrip('re:/').rstrip('/')
                    if re.search(regex, file_path):
                        logger.info(
                            "File matches transcode_ignore pattern: %s", pattern
                        )
                        skip_transcoding = True
                        break
                    if re.search(normalize_pattern(regex), file_path):
                        logger.info(
                            "File matches transcode_ignore pattern: %s", pattern
                        )
                        skip_transcoding = True
                        break
                else:
                    if fnmatch.fnmatch(file_path, pattern):
                        logger.info(
                            "File matches transcode_ignore pattern: %s", pattern
                        )
                        skip_transcoding = True
                        break

        if skip_transcoding:
            logger.info(
                "Skipping transcoding for %s (matches transcode_ignore pattern)",
                get_attribute(file_info, "file_name")
            )
            result["transcoding_skipped"] = True
            return result

        mediainfo_exists = self.has_mediainfo(asset_id, file_id)
        logger.debug("mediainfo_exists: %s", mediainfo_exists)

        proxies_exist = self.has_proxies(asset_id)
        logger.debug("proxies_exist: %s", proxies_exist)

        keyframes_exist = self.has_keyframes(asset_id)
        logger.debug("keyframes_exist: %s", keyframes_exist)

        has_mediainfo_metadata_history = self.has_mediainfo_metadata_history(
            asset_id
        )
        logger.debug(
            "has_mediainfo_metadata_history: %s", has_mediainfo_metadata_history
        )

        if not mediainfo_exists or not has_mediainfo_metadata_history:
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

        self.storage_settings['local_proxy_creation'] = False

        if not result.get("mediainfo_job", False
                          ) and (not proxies_exist or not keyframes_exist):
            if self.storage_settings.get('local_proxy_creation', False):
                logger.info("Local proxy creation enabled but not implemented")
            else:
                try:
                    proxy_url = self.client.files(
                    ).gen_url(f"assets/{asset_id}/files/{file_id}/keyframes")
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

        return result

    # pylint: disable=too-many-positional-arguments
    def _create_history_record(
        self, asset_id: str, asset_existed: bool, format_existed: bool,
        file_set_existed: bool, file_existed: bool
    ) -> Dict[str, Any]:
        """
        Create a history record for the asset operation.

        Args:
            asset_id: Asset ID
            asset_existed: Whether the asset existed before
            format_existed: Whether the format existed before
            file_set_existed: Whether the file set existed before
            file_existed: Whether the file existed before

        Returns:
            Dictionary with history record results
        """
        result = {}

        operation_description = "Asset synchronized with external system via the API"
        operation_type = "CUSTOM"

        if not asset_existed:
            operation_description = "Initial asset creation"
            operation_type = "VERSION_CREATE"
        elif not format_existed:
            operation_description = "Add format ORIGINAL"
            operation_type = "ADD_FORMAT"
        elif not file_set_existed:
            operation_description = "File set added to asset"
            operation_type = "MODIFY_FILESET"
        elif not file_existed:
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

    def _ensure_collection_hierarchy(self, file_path: str) -> Optional[str]:
        """
        Ensure the collection hierarchy exists for the file's directory path
        if collection directory mapping is enabled.

        Args:
            file_path: Path to the file

        Returns:
            Collection ID of the leaf collection or None if collection mapping
                is disabled
        """
        # Check if collection directory mapping is enabled
        if not self.storage_settings.get(
            'enable_collection_directory_mapping', False
        ):
            logger.debug("Collection directory mapping is not enabled")
            return None

        try:
            # Create a recipe instance
            recipe = CollectionDirectoryMappingRecipe(
                client=self.client, storage_id=self.storage_id
            )

            # Get the directory path for the file
            directory_path = os.path.dirname(self.map_file_path(file_path))
            logger.debug(
                "Ensuring collection hierarchy for directory: %s",
                directory_path
            )

            # Ensure the collection hierarchy exists
            collection_id = recipe.ensure_collection_hierarchy(directory_path)
            if collection_id:
                logger.info(
                    "Created/found collection for directory path: %s -> %s",
                    directory_path, collection_id
                )
                return collection_id
            logger.warning(
                "Failed to create collection hierarchy for directory: %s",
                directory_path
            )
            return None
        except Exception as e:
            logger.error("Error ensuring collection hierarchy: %s", str(e))
            return None

    # pylint: disable=too-many-positional-arguments
    def create_asset(
        self,
        file_path: str,
        external_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        collection_ids: Optional[List[str]] = None,
        md5sum: Optional[str] = None,
        allow_offline: bool = False
    ) -> Dict[str, Any]:
        """
        Create an asset with associated format, file set, and file.

        Args:
            file_path: Path to the file
            external_id: Optional external ID (generated from path if None)
            metadata: Optional metadata to apply
            collection_ids: Optional list of collection IDs to add the asset to
            md5sum: Optional pre-calculated MD5 checksum to use
            allow_offline: Whether to allow files that are not accessible

        Returns:
            Dictionary with details of the created objects
        """
        # Check file validity with the new parameters
        file_info = self._check_file_validity(file_path, md5sum, allow_offline)

        if not external_id:
            external_id = self._resolve_external_id(file_info)
        file_info["external_id"] = external_id
        logger.debug("Using external ID: %s", external_id)

        if metadata and file_info.get("sidecar_metadata"):
            metadata = self._merge_metadata(
                metadata, file_info["sidecar_metadata"]
            )
            logger.debug("Merged provided metadata with sidecar metadata")
        elif file_info.get("sidecar_metadata"):
            metadata = file_info["sidecar_metadata"]
            logger.debug("Using sidecar metadata")

        result = {
            "storage_id": self.storage_id,
            "file_path": file_path,
            "title": file_info["title"],
            "external_id": external_id,
            "size": file_info["size"],
            "mime_type": file_info["mime_type"],
            "directory_path": file_info["directory_path"]
        }

        metadata_view_id = self.default_view_id or self.storage_settings.get(
            'metadata_view_id'
        )
        result["metadata_view_id"] = metadata_view_id
        logger.debug("Using metadata view ID: %s", metadata_view_id)

        # Ensure collection hierarchy if directory mapping is enabled
        if self.storage_settings.get(
            'enable_collection_directory_mapping', False
        ):
            collection_id = self._ensure_collection_hierarchy(file_path)
            if collection_id and collection_ids:
                # Add the collection ID to the list of collection IDs if not
                # already present
                if collection_id not in collection_ids:
                    collection_ids = list(
                        collection_ids
                    )  # Make a copy to avoid modifying the original
                    collection_ids.append(collection_id)
                    logger.debug(
                        "Added directory collection ID to collection IDs: %s",
                        collection_id
                    )
            elif collection_id:
                collection_ids = [collection_id]
                logger.debug("Set collection IDs to: %s", collection_ids)

        asset_id, asset_existed = self._find_existing_asset(
            external_id, file_info
        )
        if not asset_id:
            asset_id = self._create_new_asset(file_info, external_id)
            asset_existed = False
        result["asset_id"] = asset_id

        format_id, format_existed = self._ensure_format(asset_id)
        result["format_id"] = format_id

        file_set_id, file_set_existed = self._ensure_file_set(
            asset_id, format_id, file_info
        )
        result["file_set_id"] = file_set_id

        file_id, file_existed = self._ensure_file(
            asset_id, format_id, file_set_id, file_info
        )
        result["file_id"] = file_id

        if metadata:
            metadata_applied = self._apply_metadata(
                asset_id, metadata, metadata_view_id
            )
            result["metadata_applied"] = metadata_applied

        if collection_ids:
            added_collections = self._add_to_collections(
                asset_id, collection_ids
            )
            result["added_collections"] = added_collections

        transcoding_result = self._trigger_transcoding(
            asset_id, file_id, file_info, allow_offline
        )
        result.update(transcoding_result)

        history_result = self._create_history_record(
            asset_id, asset_existed, format_existed, file_set_existed,
            file_existed
        )
        result.update(history_result)

        return result


def _load_metadata(metadata_arg: str) -> Optional[Dict[str, Any]]:
    """
    Load metadata from an argument value.

    Args:
        metadata_arg: Metadata argument value which could be:
            - A raw JSON string if it doesn't start with @
            - A file path if it starts with @ followed by a path
            - Stdin indicator if it's @-

    Returns:
        Dictionary with metadata or None if the value is None or invalid

    Raises:
        ValueError: If the metadata string, file, or stdin doesn't contain
            valid JSON
    """
    if not metadata_arg:
        return None

    if not metadata_arg.startswith('@'):
        # Treat as raw JSON string
        try:
            return json.loads(metadata_arg)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON in metadata string: {str(e)}"
            ) from e

    # Handle file or stdin
    if metadata_arg == '@-':
        # Read from stdin
        logger.debug("Reading metadata from stdin")
        try:
            return json.load(sys.stdin)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from stdin: {str(e)}") from e

    # Handle file path
    file_path = metadata_arg[1:]  # Remove @ prefix
    if not os.path.exists(file_path):
        logger.warning("Metadata file %s not found", file_path)
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in metadata file: {str(e)}") from e


def _parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments for the file ingest recipe.

    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description='Iconik file ingest recipe for asset creation',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # positional arguments
    parser.add_argument(
        'file_path', help='Path to the file to be created as an asset'
    )

    # Authentication group
    auth_group = parser.add_argument_group('Authentication')
    auth_group.add_argument(
        '--app-id',
        required=False,
        help='Iconik App ID (or set ICONIK_APP_ID environment variable)'
    )
    auth_group.add_argument(
        '--auth-token',
        required=False,
        help='Iconik Auth Token (or set ICONIK_AUTH_TOKEN environment variable)'
    )
    auth_group.add_argument(
        '--base-url',
        default='https://app.iconik.io',
        help='Iconik API base URL'
    )

    # Storage group
    storage_group = parser.add_argument_group('Storage')
    storage_group.add_argument(
        '--storage-id',
        required=False,
        help='Storage ID (or set ICONIK_STORAGE_ID environment variable)'
    )
    storage_group.add_argument(
        '--mount-mapping',
        help=
        'Mount mapping in format "local_path:remote_path". Required when the file_path mount point is different from mount point configured in storage settings.'
    )

    # Asset options group with new options
    asset_group = parser.add_argument_group('Asset options')
    asset_group.add_argument(
        '--allow-offline-files',
        action='store_true',
        help=
        'Create asset, asset format, asset file set, etc. for offline files, but skip operations requiring the file be online, e.g., checksumming, metadata extraction (i.e., mediainfo), proxy, and keyframe creation'
    )
    asset_group.add_argument(
        '--external-id',
        help='Custom external ID for the asset (defaults to autogenerated)'
    )
    asset_group.add_argument(
        '--md5sum',
        help=
        'Instead of calculating a MD5 checksum, use the checksum provided. Useful when files are not currently accessible.'
    )
    asset_group.add_argument(
        '--view-id', help='Metadata view ID (defaults to storage settings)'
    )
    asset_group.add_argument(
        '--collection-id',
        action='append',
        dest='collection_ids',
        help='Collection ID to add asset to (can be specified multiple times)'
    )
    asset_group.add_argument(
        '--metadata',
        help=
        'JSON containing metadata to apply to the asset. If the argument does not start with @, the argument is treated as a raw string. If the argument starts with @ followed by a filename, the data is read from the specified file. If the argument is @-, the data is read from stdin (e.g., piped input or keyboard input).'
    )

    # Logging group
    log_group = parser.add_argument_group('Logging')
    log_group.add_argument(
        '--debug', action='store_true', help='Enable debug logging'
    )

    # Request group
    request_group = parser.add_argument_group('Request')
    request_group.add_argument(
        '--timeout',
        default=60,
        type=int,
        help='Maximum wait time (in seconds) for a request to complete'
    )

    # Parse arguments
    args = parser.parse_args()

    # Environment variable fallbacks
    if not args.app_id:
        args.app_id = os.environ.get("APP_ID", os.environ.get("ICONIK_APP_ID"))
        if not args.app_id:
            parser.error(
                "App ID must be provided via --app-id or ICONIK_APP_ID environment variable"
            )

    if not args.auth_token:
        args.auth_token = os.environ.get(
            "AUTH_TOKEN", os.environ.get("ICONIK_AUTH_TOKEN")
        )
        if not args.auth_token:
            parser.error(
                "Auth token must be provided via --auth-token or ICONIK_AUTH_TOKEN environment variable"
            )

    if not args.storage_id:
        args.storage_id = os.environ.get(
            "STORAGE_ID", os.environ.get("ICONIK_STORAGE_ID")
        )
        if not args.storage_id:
            parser.error(
                "Storage ID must be provided via --storage-id or ICONIK_STORAGE_ID environment variable"
            )

    return args


def main():
    """
    Command-line entry point for the FileIngestRecipe.

    Parses arguments, sets up logging, and executes the asset creation
    process with the specified parameters.
    """
    args = _parse_arguments()

    if args.debug:
        logging.basicConfig(
            format=
            '%(asctime)s - %(filename)s:%(lineno)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s'
        )
        logger.setLevel(logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    logger.debug("Starting file ingest with arguments: %s", args)

    client = PythonikClient(
        app_id=args.app_id,
        auth_token=args.auth_token,
        timeout=args.timeout,
        base_url=args.base_url
    )

    metadata = None
    if args.metadata:
        try:
            metadata = _load_metadata(args.metadata)
            logger.debug("Loaded metadata: %s", json.dumps(metadata, indent=2))
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)

    recipe = FileIngestRecipe(
        client=client,
        storage_id=args.storage_id,
        default_view_id=args.view_id,
        mount_mapping=args.mount_mapping
    )

    try:
        result = recipe.create_asset(
            file_path=args.file_path,
            external_id=args.external_id,
            metadata=metadata,
            collection_ids=args.collection_ids,
            md5sum=args.md5sum,
            allow_offline=args.allow_offline_files
        )

        print("\nAsset creation complete!")
        print(f"Asset ID: {get_attribute(result, 'asset_id')}")
        print(f"Format ID: {get_attribute(result, 'format_id')}")
        print(f"File Set ID: {get_attribute(result, 'file_set_id')}")
        print(f"File ID: {get_attribute(result, 'file_id')}")

        if result.get("metadata_applied") is True:
            print("Metadata successfully applied")

        if result.get("added_collections"):
            print(
                f"Added to collections: {', '.join(get_attribute(result, 'added_collections'))}"
            )

        if result.get("offline_file", False):
            print(
                "File processed in offline mode - no transcoding or checksum generation"
            )
        elif result.get("transcoding_skipped"):
            print("Transcoding skipped - file matches ignore pattern")
        else:
            if result.get("mediainfo_job") == "skipped":
                print("Mediainfo extraction skipped - already exists")
            elif result.get("mediainfo_job") is True:
                print("Mediainfo extraction triggered")

            if result.get("proxy_job") == "skipped":
                print("Proxy/keyframe generation skipped - already exists")
            elif result.get("proxy_job") is True:
                print("Proxy/keyframe generation triggered")

        if result.get("history_created"):
            print(
                f"History created with operation type: {result.get('history_operation_type', 'CUSTOM')}"
            )

    except Exception as e:
        logger.error("Error creating asset: %s", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
