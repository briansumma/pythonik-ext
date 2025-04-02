# pythonik-ext

Extensions and enhancements for the
[pythonik](https://pypi.org/project/nsa-pythonik/) client library.

## Installation

```
pip install pythonik-ext
```

For JSON logging support:

```
pip install pythonik-ext[logging]
```

For all optional dependencies:

```
pip install pythonik-ext[all]
```

## Features

- Drop-in replacement for the standard pythonik client
- Enhanced logging (uses Python logging instead of print statements)
  - Structured JSON logging (with optional dependency)
  - Environment variable configuration
  - Consistent formatting and log levels
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

### Logging Configuration

The package includes enhanced logging capabilities that replace the
print statements in the original library with proper Python logging:

```python
from pythonikext import configure_logging, LogConfig, get_logger

# Get a logger for your module
logger = get_logger(__name__)

# Configure with defaults (INFO level, text format)
configure_logging()

# Or with custom settings
config = LogConfig(
    level="DEBUG",
    format_="text",  # or "json" if python-json-logger is installed
    app_name="my-app",
    extra_fields={"environment": "production"}
)
configure_logging(config)

# Use the logger
logger.info("Starting operation")
logger.debug("Processing file: %s", filename)
```

### Environment Variable Configuration

You can also configure logging using environment variables:

```bash
export PYTHONIK_LOG_LEVEL=DEBUG
export PYTHONIK_LOG_FORMAT=json  # requires python-json-logger
export PYTHONIK_APP_NAME=my-app
```

### Suppressing Print Statements

To completely suppress the print statements from the original library:

```python
from pythonikext import suppress_stdout

# Suppress all print statements in this block
with suppress_stdout():
    client = ExtendedPythonikClient(...)
    response = client.assets().get(...)
```

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
