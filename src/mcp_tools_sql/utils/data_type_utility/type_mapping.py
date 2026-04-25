"""Map configuration type strings to Python types."""

from datetime import datetime

TYPE_MAP: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "datetime": datetime,
}


def resolve_python_type(type_name: str) -> type:
    """Resolve a configuration type string to its Python type.

    Args:
        type_name: Type string from configuration (e.g. "str", "int").

    Returns:
        The corresponding Python type.

    Raises:
        ValueError: If the type name is not recognized.
    """
    try:
        return TYPE_MAP[type_name]
    except KeyError:
        valid = ", ".join(sorted(TYPE_MAP))
        msg = f"Unknown type {type_name!r}. Valid types: {valid}"
        raise ValueError(msg) from None
