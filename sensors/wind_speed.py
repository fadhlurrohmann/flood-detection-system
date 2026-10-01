"""RS485 Modbus RTU driver for a wind-speed anemometer."""

from config import settings


class WindSpeedSensor:
	"""Read wind speed in metres per second from a Modbus register.

	Register address and scaling vary by anemometer model. Configure them with
	EFWS_ANEM_SPEED_REGISTER and EFWS_ANEM_SPEED_SCALE from its datasheet.
	"""

	def __init__(self, port=None, slave_id=None, instrument=None):
		self.port = port if port is not None else settings.ANEMOMETER_PORT
		self.slave_id = (
			slave_id if slave_id is not None else settings.ANEMOMETER_SLAVE_ID
		)

		if instrument is None:
			try:
				import minimalmodbus
			except ImportError as error:
				raise RuntimeError(
					"minimalmodbus is required for the RS485 wind sensor"
				) from error

			instrument = minimalmodbus.Instrument(self.port, self.slave_id)

		self.instrument = instrument
		self.instrument.mode = "rtu"
		self.instrument.serial.baudrate = settings.ANEMOMETER_BAUDRATE
		self.instrument.serial.timeout = 1
		self.instrument.clear_buffers_before_each_transaction = True

	def read(self):
		"""Return wind speed in m/s using the configured Modbus register."""
		raw_speed = self.instrument.read_register(
			settings.ANEMOMETER_SPEED_REGISTER,
			number_of_decimals=0,
			functioncode=settings.ANEMOMETER_FUNCTION_CODE,
			signed=False,
		)
		return {
			"speed_ms": round(raw_speed * settings.ANEMOMETER_SPEED_SCALE, 3)
		}

	def close(self):
		"""Release the serial port."""
		self.instrument.serial.close()
