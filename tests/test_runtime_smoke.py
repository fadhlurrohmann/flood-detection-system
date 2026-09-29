"""Software-only smoke tests for the paths needed by a direct mock run."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("EFWS_RUN_MODE", "mock")

from sensors import mcp3008
from config.threshold_resolver import resolve_active_thresholds
from sensors.mock_sensors import MockPressureWater, MockRainfall, MockSoilMoisture


class FakeSPI:
    def __init__(self):
        self.max_speed_hz = None
        self.mode = None
        self.last_command = None

    def open(self, bus, device):
        self.bus = bus
        self.device = device

    def xfer2(self, command):
        self.last_command = command
        return [0, 2, 0]  # raw value 512

    def close(self):
        pass


def main():
    fake_spi = FakeSPI()
    original_spidev = mcp3008.spidev
    mcp3008.spidev = SimpleNamespace(SpiDev=lambda: fake_spi)
    try:
        adc = mcp3008.MCP3008(vref=3.3)
        assert adc.read_raw(2) == 512
        assert fake_spi.last_command == [1, 160, 0]
        assert adc.read_voltage(2) == 1.6516
    finally:
        mcp3008.spidev = original_spidev

    pressure = MockPressureWater().read()
    soil = MockSoilMoisture().read()
    rainfall = MockRainfall().read()

    assert {"current_ma", "depth_m", "pressure_bar"} <= pressure.keys()
    assert {"surface", "deep"} <= soil.keys()
    assert "rainfall_mm" in rainfall

    local_thresholds = {
        "waterDangerThreshold": 0.5,
        "soilMoistureDangerThreshold": {"surface": 10, "deep": 10},
    }
    resolved = resolve_active_thresholds(
        local_thresholds,
        {
            "waterDangerThreshold": None,
            "soilMoistureDangerThreshold": {"surface": 15},
        },
    )
    assert resolved["waterDangerThreshold"] == 0.5
    assert resolved["soilMoistureDangerThreshold"] == {"surface": 15, "deep": 10}
    print("Runtime smoke tests passed.")


if __name__ == "__main__":
    main()
