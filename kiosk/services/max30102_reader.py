from __future__ import annotations

import math
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
DEFAULT_SAMPLE_COUNT = 100
DEFAULT_SAMPLE_DELAY_SECONDS = 0.04
DEFAULT_SAMPLE_RATE_HZ = 25.0

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
        "heart_rate": None,
        "spo2": None,
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


def _filter_signal_samples(samples: list[int], *, threshold: int = OUTLIER_THRESHOLD) -> list[int]:
    if not samples:
        return []

    filtered: list[int] = []
    last_value: int | None = None
    for sample in samples:
        if is_outlier(sample, last_value, threshold) and last_value is not None:
            filtered.append(last_value)
            continue
        filtered.append(int(sample))
        last_value = int(sample)
    return filtered


def _mean(values: list[float] | list[int]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def estimate_heart_rate(ir_samples: list[int], *, sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ) -> int | None:
    if len(ir_samples) < 20 or sample_rate_hz <= 0:
        return None

    baseline = _mean(ir_samples)
    centered = [sample - baseline for sample in ir_samples]
    peak_threshold = max(500.0, max(centered) * 0.5 if centered else 500.0)
    min_peak_distance = max(1, int(sample_rate_hz * 0.4))

    peaks: list[int] = []
    last_peak_index = -min_peak_distance

    for index in range(1, len(centered) - 1):
        current_value = centered[index]
        if current_value < peak_threshold:
            continue
        if current_value <= centered[index - 1] or current_value < centered[index + 1]:
            continue
        if index - last_peak_index < min_peak_distance:
            continue
        peaks.append(index)
        last_peak_index = index

    if len(peaks) < 2:
        return None

    intervals = [peaks[i] - peaks[i - 1] for i in range(1, len(peaks))]
    average_interval = _mean(intervals)
    if average_interval <= 0:
        return None

    bpm = 60.0 * sample_rate_hz / average_interval
    if bpm < 30 or bpm > 220:
        return None
    return int(round(bpm))


def estimate_spo2(red_samples: list[int], ir_samples: list[int]) -> int | None:
    if len(red_samples) < 20 or len(ir_samples) < 20 or len(red_samples) != len(ir_samples):
        return None

    red_dc = _mean(red_samples)
    ir_dc = _mean(ir_samples)
    if red_dc <= 0 or ir_dc <= 0:
        return None

    red_ac = math.sqrt(_mean([(sample - red_dc) ** 2 for sample in red_samples]))
    ir_ac = math.sqrt(_mean([(sample - ir_dc) ** 2 for sample in ir_samples]))
    if red_ac <= 0 or ir_ac <= 0:
        return None

    ratio = (red_ac / red_dc) / (ir_ac / ir_dc)
    spo2 = 110 - 25 * ratio
    if spo2 < 70 or spo2 > 100:
        return None
    return int(round(spo2))


def _read_sensor_window(
    bus: SMBus,
    *,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
    sample_delay_seconds: float = DEFAULT_SAMPLE_DELAY_SECONDS,
) -> tuple[list[int], list[int]]:
    red_samples: list[int] = []
    ir_samples: list[int] = []

    for _ in range(max(1, sample_count)):
        red, ir = _read_fifo_sample(bus)
        red_samples.append(red)
        ir_samples.append(ir)
        if sample_delay_seconds > 0:
            time.sleep(sample_delay_seconds)

    return _filter_signal_samples(red_samples), _filter_signal_samples(ir_samples)


def read_max30102_raw(
    *,
    bus_number: int = DEFAULT_I2C_BUS,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
    sample_delay_seconds: float = DEFAULT_SAMPLE_DELAY_SECONDS,
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
) -> dict:
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
            red_samples, ir_samples = _read_sensor_window(
                bus,
                sample_count=sample_count,
                sample_delay_seconds=sample_delay_seconds,
            )
    except FileNotFoundError:
        return _error("Bus I2C introuvable")
    except OSError:
        return _error("MAX30102 non detecte")
    except Exception as exc:  # pragma: no cover - hardware specific
        return _error(str(exc) or "Lecture MAX30102 impossible")

    if not red_samples or not ir_samples:
        return _error("Aucun echantillon MAX30102 valide")

    heart_rate = estimate_heart_rate(ir_samples, sample_rate_hz=sample_rate_hz)
    spo2 = estimate_spo2(red_samples, ir_samples)
    red = red_samples[-1]
    ir = ir_samples[-1]

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
        "heart_rate": heart_rate,
        "spo2": spo2,
        "status": "ok",
    }
