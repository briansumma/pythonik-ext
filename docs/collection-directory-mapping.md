# Collection Directory Mapping Recipe

The Collection Directory Mapping Recipe creates a mirror of the file
system directory structure in iconik collections. This is particularly
useful when you have a storage with the
`enable_collection_directory_mapping` setting enabled.

## Overview

This recipe allows you to automatically create and maintain collections
in iconik that match your file system's directory structure. When a file
is ingested from a specific directory path, the corresponding collection
hierarchy is created, ensuring your media assets are organized in
collections that reflect their file system location.

## Features

- Creates collections that mirror your file system directory structure
- Intelligently caches collection IDs to improve performance
- Handles existing collections to avoid duplication
- Creates directory entries in the storage if needed
- Command-line interface for easy automation

## Usage

### Python API

```python
from pythonikext import ExtendedPythonikClient
from pythonikext.recipes.collection_directory_mapping import CollectionDirectoryMappingRecipe

# Create the client
client = ExtendedPythonikClient(
    app_id="your_app_id",
    auth_token="your_auth_token",
    timeout=30
)

# Create the recipe instance
recipe = CollectionDirectoryMappingRecipe(
    client=client,
    storage_id="your_storage_id",
    storage_root_path="/optional/root/path"  # Optional
)

# Map an entire directory structure
result = recipe.map_directory_structure()
if result["success"]:
    print(f"Mapped {len(result['mapped_collections'])} directories to collections")
else:
    print(f"Mapping failed: {result.get('error')}")

# Or ensure a specific path exists as a collection hierarchy
collection_id = recipe.ensure_collection_hierarchy("/path/to/directory")
if collection_id:
    print(f"Created/found collection for path with ID: {collection_id}")
```

### Command Line Interface

The recipe also provides a command-line interface:

```bash
python -m pythonikext.recipes.collection_directory_mapping \
    --app-id your_app_id \
    --auth-token your_auth_token \
    --storage-id your_storage_id \
    --root-path /optional/root/path \
    --base-url https://app.iconik.io \
    --timeout 30 \
    --debug
```

#### Command Line Arguments

- `--storage-id`: (Required) ID of the storage to map directories for
- `--root-path`: (Optional) Root path to start mapping from, defaults to
  storage mount point
- `--app-id`: (Required) Iconik App ID
- `--auth-token`: (Required) Iconik Auth Token
- `--base-url`: (Optional) Iconik API base URL (default:
  https://app.iconik.io)
- `--timeout`: (Optional) Request timeout in seconds (default: 30)
- `--debug`: (Optional) Enable debug logging

## Storage Configuration

For this recipe to work, the storage in iconik must have the
`enable_collection_directory_mapping` setting enabled. This can be
configured in the iconik web interface under Storage settings.

## Implementation Details

The recipe works by:

1. Finding the "Storage Gateways" root collection in iconik
2. Creating a storage root collection if it doesn't exist
3. For each directory path:
   - Checking if a corresponding collection exists
   - Creating it if it doesn't
   - Recursively processing subdirectories

All collection operations are cached to improve performance when
processing large directory structures.
