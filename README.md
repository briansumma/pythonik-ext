# pythonik-ext

Extensions and enhancements for the
[pythonik](https://pypi.org/project/nsa-pythonik/) client library.

## Installation

```
pip install pythonik-ext
```

## Features

- Drop-in replacement for the standard pythonik client
- Enhanced logging (uses Python logging instead of print statements)
- Additional functionality:
  - File checksum utilities for finding files by MD5
  - Improved error handling
  - Better typing support

## Usage

### Basic Usage

```python
from pythonikext import ExtendedPythonikClient

# Create a client (same interface as the original)
client = ExtendedPythonikClient(app_id="your_app_id",
                                auth_token="your_auth_token", timeout=10)

# Use familiar methods
asset = client.assets().get(asset_id="1234567890abcdef")
```

### New Functionality

```python
from pythonikext import ExtendedPythonikClient

client = ExtendedPythonikClient(app_id="your_app_id",
                                auth_token="your_auth_token", timeout=10)

# Get files by checksum string
response = client.files().get_files_by_checksum(
    "d41d8cd98f00b204e9800998ecf8427e")

# Or use a file path - it calculates the checksum for you
response = client.files().get_files_by_checksum("path/to/your/file.txt")
```

### Using Just the Extended Specs

```python
from pythonik.client import PythonikClient
from pythonikext.specs.files import ExtendedFilesSpec

# Use the original client
client = PythonikClient(app_id="your_app_id", auth_token="your_auth_token")

# Create an extended files spec
extended_files = ExtendedFilesSpec(client.session,
                                   timeout=client.timeout,
                                   base_url=client.base_url)

# Use extended functionality
response = extended_files.get_files_by_checksum("path/to/your/file.txt")
```

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
