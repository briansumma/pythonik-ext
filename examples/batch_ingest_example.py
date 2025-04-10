#!/usr/bin/env python3
"""
Example script demonstrating how to use both the collection_directory_mapping
and file_ingest recipes together for a complete workflow.

This script:
1. Sets up directory mapping for a storage
2. Processes a batch of files, adding them to their respective collections

Usage:
    python example_batch_ingest.py --config config.json /path/to/media/directory

Where config.json contains:
{
    "app_id": "your_app_id",
    "auth_token": "your_auth_token",
    "storage_id": "your_storage_id",
    "base_url": "https://app.iconik.io",
    "metadata_view_id": "optional_view_id",
    "mount_mapping": "/local/path:/remote/path"
}
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

from pythonikext import (
    ExtendedPythonikClient,
    LogConfig,
    configure_logging,
    get_logger,
)
from pythonikext.recipes.collection_directory_mapping import (
    CollectionDirectoryMappingRecipe,
)
from pythonikext.recipes.file_ingest import FileIngestRecipe

# Configure logging
configure_logging(LogConfig(level="INFO", format_="text"))
logger = get_logger(__name__)


def find_media_files(directory: str, extensions: Set[str]) -> List[str]:
    """
    Find all media files with the specified extensions in the directory tree.
    
    Args:
        directory: Root directory to search
        extensions: Set of file extensions to include (lowercase, with dot)
    
    Returns:
        List of file paths matching the criteria
    """
    media_files = []

    for root, _, files in os.walk(directory):
        for filename in files:
            _, extension = os.path.splitext(filename)
            if extension.lower() in extensions:
                media_files.append(os.path.join(root, filename))

    return media_files


def ensure_collection_mapping(
    client: ExtendedPythonikClient, storage_id: str, root_path: str
) -> Dict[str, str]:
    """
    Ensure the storage has directory mapping set up for the given root path.
    
    Args:
        client: ExtendedPythonikClient instance
        storage_id: Storage ID
        root_path: Root path to map
    
    Returns:
        Dictionary mapping directory paths to collection IDs
    """
    logger.info("Setting up collection directory mapping")

    recipe = CollectionDirectoryMappingRecipe(
        client=client, storage_id=storage_id, storage_root_path=root_path
    )

    # Check if mapping is enabled
    # pylint: disable=protected-access
    if not recipe._is_mapping_enabled():
        logger.warning(
            "Collection directory mapping is not enabled for storage %s. "
            "Collections will not be automatically created.", storage_id
        )
        return {}

    # Map the directory structure
    result = recipe.map_directory_structure(root_path)

    if result["success"]:
        logger.info(
            "Successfully mapped %d directories to collections",
            len(result.get("mapped_collections", {}))
        )
        return result.get("mapped_collections", {})
    logger.error(
        "Failed to map directory structure: %s",
        result.get("error", "Unknown error")
    )
    return result.get("partial_mapping", {})


# pylint: disable=too-many-positional-arguments
def ingest_files(
    client: ExtendedPythonikClient,
    storage_id: str,
    files: List[str],
    metadata_view_id: Optional[str] = None,
    mount_mapping: Optional[str] = None,
    collection_map: Optional[Dict[str, str]] = None
) -> Tuple[int, int]:
    """
    Ingest a list of files into iconik.
    
    Args:
        client: ExtendedPythonikClient instance
        storage_id: Storage ID
        files: List of file paths to ingest
        metadata_view_id: Optional metadata view ID
        mount_mapping: Optional mount mapping string (local:remote)
        collection_map: Optional map of directory paths to collection IDs
    
    Returns:
        Tuple of (successful_count, failed_count)
    """
    recipe = FileIngestRecipe(
        client=client,
        storage_id=storage_id,
        default_view_id=metadata_view_id,
        mount_mapping=mount_mapping
    )

    success_count = 0
    fail_count = 0

    for i, file_path in enumerate(files):
        logger.info(
            "Processing file %d of %d: %s", i + 1, len(files), file_path
        )

        try:
            # Get collection IDs for this file if we have a mapping
            collection_ids = []

            if collection_map:
                # Find the closest parent directory with a mapped collection
                dir_path = os.path.dirname(file_path)

                while dir_path:
                    if dir_path in collection_map:
                        collection_ids.append(collection_map[dir_path])
                        break

                    # Try parent directory
                    parent_dir = os.path.dirname(dir_path)
                    if parent_dir == dir_path:  # Reached root
                        break
                    dir_path = parent_dir

            # Basic metadata from filename
            file_basename = os.path.basename(file_path)
            file_stem, _ = os.path.splitext(file_basename)

            metadata = {
                "metadata_values": {
                    "title": {
                        "field_values": [{
                            "value": file_stem
                        }]
                    },
                    "filename": {
                        "field_values": [{
                            "value": file_basename
                        }]
                    }
                }
            }

            # Create the asset
            result = recipe.create_asset(
                file_path=file_path,
                metadata=metadata,
                collection_ids=collection_ids if collection_ids else None
            )

            if "asset_id" in result:
                logger.info(
                    "Successfully created asset: %s", result["asset_id"]
                )
                success_count += 1
            else:
                logger.error("Failed to create asset: %s", file_path)
                fail_count += 1

            # Small delay to avoid rate limiting
            time.sleep(0.5)

        except Exception as e:
            logger.exception("Error processing file %s: %s", file_path, str(e))
            fail_count += 1

    return success_count, fail_count


def load_config(config_path: str) -> Dict:
    """Load configuration from JSON file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error("Error loading config file: %s", str(e))
        sys.exit(1)


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Batch ingest media files with collection mapping'
    )

    parser.add_argument(
        'directory', help='Directory containing media files to process'
    )

    parser.add_argument(
        '--config', required=True, help='Path to JSON configuration file'
    )

    parser.add_argument(
        '--extensions',
        default='.mp4,.mov,.mxf,.avi,.jpg,.jpeg,.png,.tif,.tiff,.doc,.docx,.pdf',  # pylint: disable=line-too-long
        help='Comma-separated list of file extensions to process'
    )

    parser.add_argument(
        '--skip-mapping',
        action='store_true',
        help='Skip collection mapping and only ingest files'
    )

    parser.add_argument(
        '--debug', action='store_true', help='Enable debug logging'
    )

    args = parser.parse_args()

    # Set up logging level
    if args.debug:
        configure_logging(LogConfig(level="DEBUG"))
        logger.setLevel(logging.DEBUG)

    # Load configuration
    config = load_config(args.config)

    # Create client
    client = ExtendedPythonikClient(
        app_id=config.get("app_id"),
        auth_token=config.get("auth_token"),
        timeout=config.get("timeout", 60),
        base_url=config.get("base_url", "https://app.iconik.io")
    )

    # Convert extensions to a set for faster lookups
    extensions = {
        ext.lower() if ext.startswith('.') else f'.{ext.lower()}'
        for ext in args.extensions.split(',')
    }

    logger.info("Searching for media files in: %s", args.directory)
    media_files = find_media_files(args.directory, extensions)
    logger.info("Found %d media files to process", len(media_files))

    # Set up collection mapping if enabled
    collection_map = {}
    if not args.skip_mapping:
        collection_map = ensure_collection_mapping(
            client, config.get("storage_id"), args.directory
        )

    # Process files
    success_count, fail_count = ingest_files(
        client,
        config.get("storage_id"),
        media_files,
        metadata_view_id=config.get("metadata_view_id"),
        mount_mapping=config.get("mount_mapping"),
        collection_map=collection_map
    )

    logger.info(
        "Processing complete. Successful: %d, Failed: %d", success_count,
        fail_count
    )


if __name__ == "__main__":
    main()
