# Changelog

All notable changes to the `pythonik-ext` package will be documented in
this file.

## [2025.4.1-beta] - 2025-04-10

### Added

- New `recipes` module with two powerful recipe implementations:
  - `collection_directory_mapping`: Creates a mirror of the file system
    directory structure in iconik collections
  - `file_ingest`: Creates assets in iconik with intelligent
    retry/resume capabilities
- New utility functions in `_internal_utils.py`:
  - `get_attribute()`: Safely retrieves attributes from objects or
    dictionaries
  - `has_attribute()`: Checks if an object has a specific attribute
  - `is_pydantic_model()`: Detects if an object is a Pydantic model
    instance
  - `normalize_pattern()`: Normalizes string patterns with escaped
    backslashes
- New `GeneralException` class in `exceptions.py` for generic error
  handling
- New `get_mount_point()` utility function in `utils.py` to detect
  filesystem mount points

### Changed

- Updated Python requirement from ">=3.9" to ">=3.11"
- Dropped support for Python 3.9 and 3.10
- Updated Ruff target-version from "py39" to "py311"
- Updated Pylint py-version from "3.9" to "3.11"

### Fixed

- Added E501 (line-too-long) to Ruff ignore list to reduce false
  positives
- Added E731 (lambda-assignment) to Ruff ignore list for better
  compatibility with legacy code

## [2025.4-beta] - 2025-04-01

Initial beta release of pythonik-ext with:

- Drop-in replacement for the standard pythonik client
- Enhanced logging with structured JSON support
- Extended file operations including checksum-based file lookup
- Improved error handling
- Better typing support
