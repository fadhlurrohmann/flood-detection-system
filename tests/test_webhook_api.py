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
        "waterLevel":           0.2,
        "waterLevelCurrentMa":  5.067,
        "distanceM":            2.8,
        "flowRateLpm":          5.0,
        "flowTotalLiters":      10.0,
        "rainfallTotalMm":      20.0,
        "rainfallLastHour":     1.0,
        "batteryVoltage":      12.06,
        "batteryLevel":         85.0,
    }]
}

api = APIPublisher()
ok = api.send_telemetry(sample)
api.close()

if ok:
    print("✅ Success! Check the webhook.site page — the payload should appear there.")
else:
    print("❌ Failed. Check the Pi's internet connection and EFWS_API_URL in .env")
