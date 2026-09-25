"""
Threshold resolver — prioritas AKTIF threshold for evaluasi alarm.

Aturan (sesuai requirement backend):
    1. If backend (via response /sensors/telemetry) pernah sending
       'config' dan sebuah field di dalamnya TIDAK null -> use value itu.
    2. If belum pernah ada 'config' sama sekali, OR field tertentu di
       config terakhir bernilai null/hilang -> use value hardcoded local
       (config/thresholds.json) FOR FIELD ITU SAJA.

Ini per-field, not all-or-nothing -- persis seperti contoh response API
that sending "waterDangerThreshold": null sementara field lain terisi:
artinya ONLY water that fallback ke local, field lain tetap use remote.

'remote_config' di sini adalah dict RAW terakhir that received from
field "config" pada response API (disimpan oleh APIPublisher.remote_config).
Module ini not menyimpan state apa pun sendiri -- murni fungsi merge.
"""
from typing import Any, Optional


def _pick(remote_value: Any, local_value: Any) -> Any:
    """Remote menang if ada dan not None; selain itu use local."""
    return local_value if remote_value is None else remote_value


def resolve_active_thresholds(local: dict, remote_config: Optional[dict]) -> dict:
    """
    Gabungkan hardcoded local thresholds with remote config (if ada),
    field per field. Selalu mengembalikan dict lengkap with bentuk that
    sama seperti `local` (jadi caller/_evaluate not perlu tahu asalnya).
    """
    remote = remote_config or {}

    resolved = dict(local)  # shallow copy cukup, all field top-level scalar/dict kecil

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

    # soilMoistureDangerThreshold: nested dict {surface, deep} -- merge per sub-field juga,
    # because API bisa saja suatu when only mengisi wrong satu (mis. surface saja).
    remote_soil = remote.get("soilMoistureDangerThreshold")
    if not isinstance(remote_soil, dict):
        remote_soil = {}
    local_soil = local["soilMoistureDangerThreshold"]
    resolved["soilMoistureDangerThreshold"] = {
        "surface": _pick(remote_soil.get("surface"), local_soil["surface"]),
        "deep":    _pick(remote_soil.get("deep"),    local_soil["deep"]),
    }

    # windDangerThreshold: NONE di kontrak API sama sekali -- selalu local.
    resolved["windDangerThreshold"] = local["windDangerThreshold"]

    return resolved
