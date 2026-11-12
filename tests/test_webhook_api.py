"""
TEST — API connectivity to webhook.site (or the production backend).

Send one sample telemetry payload to verify:
  - The Pi can reach the API endpoint
  - The JSON format is accepted correctly
  - The Authorization header is correct (if EFWS_API_KEY is set)

Usage: python3 tests/test_webhook_api.py
"""
import sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from communication.api_publisher import APIPublisher

print("=" * 60)
print("  TEST API Connectivity")
print("=" * 60)
print(f"deviceId    : {settings.DEVICE_ID}")
print(f"endpoint    : {settings.telemetry_endpoint()}\n")

if "webhook.site/xxxxxxxx" in settings.API_BASE_URL:
    print("[FAIL] EFWS_API_URL is still the placeholder in .env")
    print("Open https://webhook.site, copy 'Your unique URL', and put it in .env")
    sys.exit(1)

sample = {
    "deviceId":    settings.DEVICE_ID,
    "deviceToken": settings.DEVICE_TOKEN,
    "telemetry": [{
        "timestamp":            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "bme_temp_c": 25.0,
        "bme_humidity_pct": 65.0,
        "bme_pressure_hpa": 1012.0,
        "sps_depth_m": 0.2,
        "sps_pressure_bar": 0.0196,
        "wind_speed_ms": 3.2,
        "wind_dir": "NE",
        "flow_lpm": 5.0,
        "distance_m": 2.8,
        "battery_pct": 85.0,
        "rainfall": 0.0,
        "pm1": 6,
        "pm25": 8,
        "pm10": 11,
        "aqi": 26,
        "aqi_provisional": True,
    }]
}

api = APIPublisher()
ok = api.send_telemetry(sample)
api.close()

if ok:
    print("✅ Success! Check the webhook.site page — the payload should appear there.")
else:
    print("❌ Failed. Check the Pi's internet connection and EFWS_API_URL in .env")
    sys.exit(1)
