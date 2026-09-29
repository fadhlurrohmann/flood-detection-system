"""Send one current-schema telemetry payload to the configured API."""
import os
import sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from communication.api_publisher import APIPublisher

print("=" * 60)
print("  API CONNECTIVITY TEST")
print("=" * 60)
print(f"deviceId    : {settings.DEVICE_ID}")
print(f"deviceToken : {settings.DEVICE_TOKEN}")
print(f"endpoint    : {settings.telemetry_endpoint()}\n")

if "webhook.site/xxxxxxxx" in settings.API_BASE_URL:
    print("[FAIL] EFWS_API_URL still placeholder in .env")
    print("Open https://webhook.site, copy 'Your unique URL', content to .env")
    sys.exit(1)

sample = {
    "deviceId":    settings.DEVICE_ID,
    "deviceToken": settings.DEVICE_TOKEN,
    "telemetry": [{
        "timestamp":            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "waterLevel": 1.8,
        "distanceM": 0.75,
        "soilMoisture": {"surface": 45.0, "deep": 55.0},
        "rainfallMm": 2.4,
    }]
}

api = APIPublisher()
ok = api.send_telemetry(sample)
api.close()

if ok:
    print("Success. Check the configured backend for the received payload.")
else:
    print("Failed. Check the Pi internet connection and EFWS_API_URL in .env.")
    sys.exit(1)
