# Contributing to pythonik-ext

Thank you for your interest in contributing to pythonik-ext! This
document provides guidelines and instructions for contributing to this
project.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and
inclusive environment for everyone.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone git@github.com:briansumma/pythonik-ext.git
   cd pythonik-ext
   ```
3. **Set up your environment**:
   ```bash
   # Create a virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows, use: venv\Scripts\activate

   # Install package with development dependencies
   pip install -e ".[dev]"
   ```

## Development Workflow

1. **Create a new branch** for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. **Make your changes** and ensure they follow our coding standards
3. **Run tests** to ensure your changes don't break existing
   functionality:
   ```bash
   pytest
   ```
4. **Lint your code** to ensure it meets our style guidelines:
   ```bash
   # Run all linters
   ruff check .
   pylint --fail-under=9 src/
   yapf --diff --recursive src/
   ```
5. **Format your code**:
   ```bash
   # Format Python files
   yapf --in-place --recursive src/

   # Format Markdown files
   prettier --prose-wrap always --print-width 72 --write *.md
   ```

## Coding Standards

This project uses the following tools for ensuring code quality:

### Linting and Style

- **Ruff**: Fast Python linter for enforcing style consistency
- **Pylint**: Comprehensive linter for catching bugs and enforcing best
  practices
- **YAPF**: Code formatter for consistent Python style
- **Prettier**: For formatting Markdown files

All configurations for these tools are stored in the `pyproject.toml`
file.

### Style Guidelines

- Use meaningful variable and function names
- Write docstrings for all public methods and classes
- Maintain 80 character line limit
- Follow PEP 8 naming conventions (snake_case for functions and
  variables, PascalCase for classes)
- Include type hints where practical

## Pull Request Process

1. **Update the README.md** if needed with details of changes to the
   interface
2. **Ensure all tests pass** and linting checks don't report errors
3. **Push your changes** to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
4. **Create a Pull Request** against the `main` branch of the original
   repository
5. **Add a clear description of the changes** in your PR, including:
    - What problem does it solve?
    - How does it solve the problem?
    - Are there any side effects or dependencies?
6. **Address review comments** if requested by maintainers

## Release Process

Releases are managed by the core maintainers. If you believe a new
release is needed, please open an issue to discuss.

### Calendar-Based Versioning

We use `YYYY.M[.P][-modifier.N]` where:

- `YYYY` - Four-digit year
- `M` - Month number (1-12)
- `P` - (Optional) Sequential patch number
- `modifier` - (Optional) Pre-release identifier (alpha/beta/rc)
- `N` - (Optional) Pre-release sequence number

Examples:

```
2024.3-alpha.1  -> First alpha release (March)
2024.3-alpha.2  -> Second alpha release
2024.3-beta.1   -> First beta release
2024.3-rc.1     -> First release candidate
2024.3          -> Final March release
2024.3.1        -> March patch 1
2024.4          -> April release
```

### Pre-release Types

- `alpha`: Early development versions
    - Major changes still expected
    - Core functionality may be incomplete
    - For internal testing only

- `beta`: Feature complete versions
    - All core features implemented
    - May have known issues
    - Ready for external testing

- `rc`: Release candidates
    - Feature and API frozen
    - No known blocking issues
    - Final testing before release

## Setting Up Your Development Environment

### Recommended IDE Setup

We recommend using PyCharm with the following plugins:

- Python Community Edition
- Prettier
- .env file support
- Ruff
- YAPF

### IDE Configuration for External Tools

#### PyCharm External Tool for YAPF

- **Name**: YAPF Format
- **Program**: `yapf`
- **Arguments**: `--in-place --recursive --print-modified $FilePath$`
- **Working directory**: `$ProjectFileDir$`

#### PyCharm External Tool for Prettier

- **Name**: Prettier Format
- **Program**: `prettier`
- **Arguments**:
  `--prose-wrap always --print-width 72 --write --ignore-unknown $FilePath$`
- **Working directory**: `$ProjectFileDir$`

## Additional Resources

- [pythonik Documentation](https://github.com/path/to/pythonik/docs)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [Conventional Commits](https://www.conventionalcommits.org/)

## Questions?

If you have any questions or need help, please open an issue on GitHub
or contact the maintainers directly.

Thank you for contributing to pythonik-ext!
