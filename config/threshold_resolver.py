"""Merge backend threshold overrides with the local fallback configuration."""
from typing import Any, Optional


def _pick(remote_value: Any, local_value: Any) -> Any:
    """Use a non-null remote value; otherwise retain the local fallback."""
    return local_value if remote_value is None else remote_value


def _merge(local_value: Any, remote_value: Any) -> Any:
    """Recursively merge dictionaries while treating null as no override."""
    if not isinstance(local_value, dict):
        return _pick(remote_value, local_value)

    remote_dict = remote_value if isinstance(remote_value, dict) else {}
    return {
        key: _merge(value, remote_dict.get(key))
        for key, value in local_value.items()
    }


def resolve_active_thresholds(local: dict, remote_config: Optional[dict]) -> dict:
    """Return the local shape with non-null remote values applied per field."""
    remote = remote_config if isinstance(remote_config, dict) else {}
    return _merge(local, remote)
