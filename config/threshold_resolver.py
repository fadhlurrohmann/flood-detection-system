"""
Threshold resolver — priority ACTIVE threshold for evaluation alarm.

Aturan (according to requirement backend):
    1. If backend (via response /sensors/telemetry) ever sending
       'config' and a field in it NOT null -> use value that.
    2. If not yet ever exists 'config' at all, OR field specific in
       config latest is null/lost -> use value hardcoded local
       (config/thresholds.json) FOR FIELD THAT ONLY.

This per-field, not all-or-nothing -- exactly like example response API
that sending "waterDangerThreshold": null while field other terisi:
this means ONLY water that fallback to local, field other still use remote.

'remote_config' in here is dict RAW latest that received from
field "config" on response API (stored by APIPublisher.remote_config).
Module this not storing state what at all its own -- purely function merge.
"""
from typing import Any, Optional


def _pick(remote_value: Any, local_value: Any) -> Any:
    """Remote takes precedence if exists and not None; otherwise that use local."""
    return local_value if remote_value is None else remote_value


def resolve_active_thresholds(local: dict, remote_config: Optional[dict]) -> dict:
    """
    Combine hardcoded local thresholds with remote config (if exists),
    field per field. Always returns dict complete with shape that
    same like `local` (therefore caller/_evaluate not needs know its source).
    """
    remote = remote_config or {}

    resolved = dict(local)  # shallow copy enough, all field top-level scalar/dict small

    resolved["smokeDangerThreshold"] = _pick(
        remote.get("smokeDangerThreshold"), local["smokeDangerThreshold"]
    )
    resolved["temperatureDangerThreshold"] = _pick(
        remote.get("temperatureDangerThreshold"), local["temperatureDangerThreshold"]
    )
    resolved["humidityDangerThreshold"] = _pick(
        remote.get("humidityDangerThreshold"), local["humidityDangerThreshold"]
    )
    resolved["waterDangerThreshold"] = _pick(
        remote.get("waterDangerThreshold"), local["waterDangerThreshold"]
    )

    # soilMoistureDangerThreshold: nested dict {surface, deep} -- merge per sub-field also,
    # because API can only suatu when only mengisi one (mis. surface only).
    remote_soil = remote.get("soilMoistureDangerThreshold")
    if not isinstance(remote_soil, dict):
        remote_soil = {}
    local_soil = local["soilMoistureDangerThreshold"]
    resolved["soilMoistureDangerThreshold"] = {
        "surface": _pick(remote_soil.get("surface"), local_soil["surface"]),
        "deep":    _pick(remote_soil.get("deep"),    local_soil["deep"]),
    }

    # windDangerThreshold: NONE in contract API at all -- always local.
    resolved["windDangerThreshold"] = local["windDangerThreshold"]

    return resolved
