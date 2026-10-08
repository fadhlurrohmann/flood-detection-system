"""
Threshold resolver — priority of the ACTIVE threshold for alarm evaluation.

Rules (per the backend requirement):
    1. If the backend (via the /sensors/telemetry response) has ever sent a
       'config' and a field inside it is NOT null -> use that value.
    2. If there has never been any 'config', OR a given field in the latest
       config is null/missing -> use the local hardcoded value
       (config/thresholds.json) FOR THAT FIELD ONLY.

This is per-field, not all-or-nothing -- exactly like the example API response
that sends "waterDangerThreshold": null while the other fields are filled:
it means ONLY water falls back to local, the other fields still use remote.

'remote_config' here is the RAW dict last received from the "config" field
of the API response (stored by APIPublisher.remote_config).
This module keeps no state of its own -- it is a pure merge function.
"""
from typing import Any, Optional


def _pick(remote_value: Any, local_value: Any) -> Any:
    """Remote wins if present and not None; otherwise use local."""
    return local_value if remote_value is None else remote_value


def resolve_active_thresholds(local: dict, remote_config: Optional[dict]) -> dict:
    """
    Merge the hardcoded local thresholds with the remote config (if any),
    field by field. Always returns a complete dict with the same shape
    as `local` (so the caller/_evaluate does not need to know where it came from).
    """
    remote = remote_config or {}

    resolved = dict(local)  # a shallow copy is enough, all top-level fields are scalars/small dicts

    resolved["waterDangerThreshold"] = _pick(
        remote.get("waterDangerThreshold"), local["waterDangerThreshold"]
    )
    # rainfallDangerThreshold is not in thresholds.json yet -- if the backend also
    # has not sent it, the result is None and _evaluate does not trigger a rain alarm.
    resolved["rainfallDangerThreshold"] = _pick(
        remote.get("rainfallDangerThreshold"), local.get("rainfallDangerThreshold")
    )

    return resolved
