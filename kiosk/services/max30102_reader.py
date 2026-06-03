from __future__ import annotations

import time
from threading import Lock

from .filters import MovingAverageFilter, is_outlier

try:
    from smbus2 import SMBus
except ImportError:  # pragma: no cover - depends on runtime environment
    SMBus = None


MAX30102_I2C_ADDRESS = 0x57
DEFAULT_I2C_BUS = 1
OUTLIER_THRESHOLD = 50000

REG_INTR_ENABLE_1 = 0x02
REG_INTR_ENABLE_2 = 0x03
REG_FIFO_WR_PTR = 0x04
REG_OVF_COUNTER = 0x05
REG_FIFO_RD_PTR = 0x06
REG_FIFO_DATA = 0x07
REG_FIFO_CONFIG = 0x08
REG_MODE_CONFIG = 0x09
REG_SPO2_CONFIG = 0x0A
REG_LED1_PA = 0x0C
REG_LED2_PA = 0x0D
REG_PART_ID = 0xFF

EXPECTED_PART_IDS = {0x15, 0x11}

_lock = Lock()
_red_filter = MovingAverageFilter(window_size=5)
_ir_filter = MovingAverageFilter(window_size=5)
_last_red_value: int | None = None
_last_ir_value: int | None = None


def _error(message: str) -> dict:
    return {
        "red": None,
        "ir": None,
        "status": "error",
        "message": message,
    }


def _read_fifo_sample(bus: SMBus) -> tuple[int, int]:
    data = bus.read_i2c_block_data(MAX30102_I2C_ADDRESS, REG_FIFO_DATA, 6)
    red = ((data[0] << 16) | (data[1] << 8) | data[2]) & 0x3FFFF
    ir = ((data[3] << 16) | (data[4] << 8) | data[5]) & 0x3FFFF
    return red, ir


def _initialize_sensor(bus: SMBus) -> None:
    bus.write_byte_data(MAX30102_I2C_ADDRESS, REG_MODE_CONFIG, 0x40)
    time.sleep(0.05)
    bus.write_byte_data(MAX30102_I2C_ADDRESS, REG_INTR_ENABLE_1, 0xC0)
    bus.write_byte_data(MAX30102_I2C_ADDRESS, REG_INTR_ENABLE_2, 0x00)
    bus.write_byte_data(MAX30102_I2C_ADDRESS, REG_FIFO_WR_PTR, 0x00)
    bus.write_byte_data(MAX30102_I2C_ADDRESS, REG_OVF_COUNTER, 0x00)
    bus.write_byte_data(MAX30102_I2C_ADDRESS, REG_FIFO_RD_PTR, 0x00)
    bus.write_byte_data(MAX30102_I2C_ADDRESS, REG_FIFO_CONFIG, 0x0F)
    bus.write_byte_data(MAX30102_I2C_ADDRESS, REG_MODE_CONFIG, 0x03)
    bus.write_byte_data(MAX30102_I2C_ADDRESS, REG_SPO2_CONFIG, 0x27)
    bus.write_byte_data(MAX30102_I2C_ADDRESS, REG_LED1_PA, 0x24)
    bus.write_byte_data(MAX30102_I2C_ADDRESS, REG_LED2_PA, 0x24)


def read_max30102_raw(*, bus_number: int = DEFAULT_I2C_BUS) -> dict:
    global _last_red_value, _last_ir_value

    if SMBus is None:
        return _error("smbus2 n'est pas installe")

    try:
        with SMBus(bus_number) as bus:
            part_id = bus.read_byte_data(MAX30102_I2C_ADDRESS, REG_PART_ID)
            if part_id not in EXPECTED_PART_IDS:
                return _error("MAX30102 non detecte")

            _initialize_sensor(bus)
            time.sleep(0.05)
            red, ir = _read_fifo_sample(bus)
    except FileNotFoundError:
        return _error("Bus I2C introuvable")
    except OSError:
        return _error("MAX30102 non detecte")
    except Exception as exc:  # pragma: no cover - hardware specific
        return _error(str(exc) or "Lecture MAX30102 impossible")

    with _lock:
        if is_outlier(red, _last_red_value, OUTLIER_THRESHOLD):
            red = _last_red_value if _last_red_value is not None else red
        if is_outlier(ir, _last_ir_value, OUTLIER_THRESHOLD):
            ir = _last_ir_value if _last_ir_value is not None else ir

        _last_red_value = int(red)
        _last_ir_value = int(ir)
        filtered_red = int(round(_red_filter.add(red)))
        filtered_ir = int(round(_ir_filter.add(ir)))

    return {
        "red": filtered_red,
        "ir": filtered_ir,
        "status": "ok",
    }
