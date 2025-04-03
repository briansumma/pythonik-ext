from typing import Any

from .exceptions import GeneralException


def get_attribute(obj: Any, attr: str, default: Any = None) -> Any:
    """
    Safely retrieves an attribute from an object, handling both
    dictionaries and class instances with dot notation.

    Args:
        obj: The object to retrieve the attribute from.
        attr: The name of the attribute to retrieve.
        default: The value to return if attribute is not found.

    Returns:
        The value of the attribute if found, otherwise the default value.
    """
    if obj is None:
        return default

    if isinstance(obj, dict):
        return obj.get(attr, default)

    try:
        return getattr(obj, attr, default)
    except (AttributeError, TypeError):
        return default


def has_attribute(obj: Any, attr: str) -> bool:
    """
    Checks if an object has a specific attribute, handling both
    dictionaries and class instances.

    Args:
        obj: The object to check for the attribute.
        attr: The name of the attribute to check.

    Returns:
        True if the attribute exists, False otherwise.
    """
    if obj is None:
        return False

    if isinstance(obj, dict):
        return attr in obj

    try:
        return hasattr(obj, attr)
    except TypeError:
        return False


def is_pydantic_model(obj: Any) -> bool:
    """
    Checks if an object is a Pydantic model instance.

    Args:
        obj: The object to check.

    Returns:
        True if the object is a Pydantic model instance, False otherwise.
    """
    # Check for common Pydantic model attributes/methods
    if obj is None:
        return False

    try:
        # Pydantic v1
        has_dict_method = hasattr(obj, 'dict') and callable(
            getattr(obj, 'dict', None)
        )
        # Pydantic v2
        has_model_dump = hasattr(obj, 'model_dump') and callable(
            getattr(obj, 'model_dump', None)
        )

        # Check for schema-related attributes that are common in Pydantic models
        has_schema_attrs = hasattr(obj, '__fields__'
                                   ) or hasattr(obj, 'model_fields')

        return (has_dict_method or has_model_dump) and has_schema_attrs
    except GeneralException:
        return False


def normalize_pattern(pattern: str) -> str:
    """
    Normalize a string pattern that may contain double backslashes
    from JSON deserialization.

    This is useful for handling patterns extracted from JSON configuration
    where backslashes are escaped, resulting in double backslashes when
    deserialized into Python strings.

    Args:
        pattern: The string pattern, possibly with double backslashes

    Returns:
        Normalized pattern with single backslashes

    Examples:
        >>> normalize_pattern(r"\\d+")  # From JSON: "\\d+"
        '\\d+'
        >>> normalize_pattern("C:\\\\Users\\\\file.txt")
        'C:\\Users\\file.txt'
    """
    if not pattern or '\\' not in pattern:
        return pattern

    # Replace double backslashes with single backslashes
    return pattern.replace('\\\\', '\\')
