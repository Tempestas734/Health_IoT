from __future__ import annotations

import os
import re
import unicodedata
from threading import Lock
from typing import Any

from .filters import MovingAverageFilter, is_outlier

try:
    import serial
    from serial import SerialException
except ImportError:  # pragma: no cover - exercised via runtime environment
    serial = None

    class SerialException(Exception):
        pass


DISTANCE_PATTERN = re.compile(r"DISTANCE\s*[:=]\s*(\d+)", re.IGNORECASE)
RECEIVED_DISTANCE_MM_PATTERN = re.compile(
    r"Received\s+distance\s*[:=]\s*(\d+)\s*mm",
    re.IGNORECASE,
)
FRENCH_DISTANCE_TOKEN = r"mesur(?:ee|e)"
FRENCH_HEIGHT_TOKEN = r"estim(?:ee|e)"
FRENCH_DISTANCE_CM_PATTERN = re.compile(
    rf"Distance\s+{FRENCH_DISTANCE_TOKEN}\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?)\s*cm",
    re.IGNORECASE,
)
FRENCH_DISTANCE_AND_HEIGHT_PATTERN = re.compile(
    rf"Distance\s+{FRENCH_DISTANCE_TOKEN}\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?)\s*cm(?:\s*[|;,-]\s*|\s+)Taille\s+{FRENCH_HEIGHT_TOKEN}\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?)\s*cm",
    re.IGNORECASE,
)
HEIGHT_CM_PATTERN = re.compile(
    r"HEIGHT_CM\s*[=:]\s*([0-9]+(?:[.,][0-9]+)?)",
    re.IGNORECASE,
)
ERROR_PATTERN = re.compile(r"DISTANCE_ERROR|erreur|error|timeout", re.IGNORECASE)
INFO_PATTERN = re.compile(
    r"detecte|detected|pret|ready|boot|initiali[sz]|connecte|connected",
    re.IGNORECASE,
)
DEFAULT_OUTLIER_THRESHOLD_MM = 500
DEFAULT_SENSOR_HEIGHT_MM = 2000
DEFAULT_CALIBRATION_MM = 0
MIN_VALID_HEIGHT_MM = 500
MAX_VALID_HEIGHT_MM = 2200

_height_filter = MovingAverageFilter(window_size=5)
_last_distance_mm: int | None = None
_lock = Lock()


def _normalize_serial_line(line: str) -> str:
    normalized = unicodedata.normalize("NFKD", line or "")
    ascii_line = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_line.replace(",", ".").strip()


def _serial_port() -> str:
    default_port = "COM3" if os.name == "nt" else "/dev/ttyACM0"
    return os.getenv("HEIGHT_SENSOR_PORT", default_port)


def _serial_baud_rate() -> int:
    try:
        return int(os.getenv("HEIGHT_SENSOR_BAUD", "9600"))
    except ValueError:
        return 9600


def _serial_timeout() -> float:
    try:
        return float(os.getenv("HEIGHT_SENSOR_TIMEOUT", "1"))
    except ValueError:
        return 1.0


def _sensor_height_mm() -> int:
    try:
        return int(os.getenv("HEIGHT_SENSOR_HEIGHT_MM", str(DEFAULT_SENSOR_HEIGHT_MM)))
    except ValueError:
        return DEFAULT_SENSOR_HEIGHT_MM


def _calibration_mm() -> int:
    try:
        return int(os.getenv("HEIGHT_SENSOR_CALIBRATION_MM", str(DEFAULT_CALIBRATION_MM)))
    except ValueError:
        return DEFAULT_CALIBRATION_MM


def _outlier_threshold_mm() -> int:
    try:
        return int(
            os.getenv(
                "HEIGHT_SENSOR_OUTLIER_THRESHOLD_MM",
                str(DEFAULT_OUTLIER_THRESHOLD_MM),
            )
        )
    except ValueError:
        return DEFAULT_OUTLIER_THRESHOLD_MM


def parse_height_measurement(line: str) -> tuple[float | None, float | None]:
    normalized = _normalize_serial_line(line)
    if not normalized:
        return None, None

    french_measurement_match = FRENCH_DISTANCE_AND_HEIGHT_PATTERN.search(normalized)
    if french_measurement_match:
        return (
            float(french_measurement_match.group(1)) * 10.0,
            float(french_measurement_match.group(2)) * 10.0,
        )

    height_match = HEIGHT_CM_PATTERN.search(normalized)
    if height_match:
        return None, float(height_match.group(1)) * 10.0

    return parse_height_line(normalized), None


def parse_height_line(line: str) -> float | None:
    normalized = _normalize_serial_line(line)
    if not normalized:
        return None

    distance_match = DISTANCE_PATTERN.search(normalized)
    if distance_match:
        return float(int(distance_match.group(1)))

    received_distance_match = RECEIVED_DISTANCE_MM_PATTERN.search(normalized)
    if received_distance_match:
        return float(int(received_distance_match.group(1)))

    french_distance_match = FRENCH_DISTANCE_CM_PATTERN.search(normalized)
    if french_distance_match:
        return float(french_distance_match.group(1)) * 10.0

    height_match = HEIGHT_CM_PATTERN.search(normalized)
    if height_match:
        height_cm = float(height_match.group(1))
        return float((_sensor_height_mm() + _calibration_mm()) - (height_cm * 10.0))

    return None


def distance_to_height_mm(
    distance_mm: float | int,
    *,
    sensor_height_mm: int | None = None,
) -> int | None:
    try:
        measured_distance = int(round(float(distance_mm)))
    except (TypeError, ValueError):
        return None

    ceiling_height = sensor_height_mm if sensor_height_mm is not None else _sensor_height_mm()
    estimated_height = ceiling_height - measured_distance + _calibration_mm()
    if estimated_height < MIN_VALID_HEIGHT_MM or estimated_height > MAX_VALID_HEIGHT_MM:
        return None
    return estimated_height


def read_height_measurement(*, max_lines: int = 12) -> dict[str, Any]:
    global _last_distance_mm

    port = _serial_port()
    sensor_height_mm = _sensor_height_mm()
    outlier_threshold_mm = _outlier_threshold_mm()
    last_error_line = ""
    last_observed_line = ""

    if serial is None:
        return {
            "status": "error",
            "message": "pyserial n'est pas installe.",
            "height_mm": None,
            "height_cm": None,
            "distance_mm": None,
            "source_line": "",
            "port": port,
        }

    try:
        with serial.Serial(port, _serial_baud_rate(), timeout=_serial_timeout()) as connection:
            for _ in range(max_lines):
                raw_line = connection.readline()
                if not raw_line:
                    continue

                decoded_line = raw_line.decode("utf-8", errors="ignore").strip()
                if not decoded_line:
                    continue

                last_observed_line = decoded_line

                if ERROR_PATTERN.search(decoded_line):
                    last_error_line = decoded_line
                    continue

                if INFO_PATTERN.search(_normalize_serial_line(decoded_line)):
                    continue

                distance_mm, direct_height_mm = parse_height_measurement(decoded_line)
                if distance_mm is not None or direct_height_mm is not None:
                    with _lock:
                        rounded_distance = int(round(distance_mm)) if distance_mm is not None else None
                        if (
                            rounded_distance is not None
                            and is_outlier(rounded_distance, _last_distance_mm, outlier_threshold_mm)
                        ):
                            fallback_height_mm = distance_to_height_mm(
                                _last_distance_mm,
                                sensor_height_mm=sensor_height_mm,
                            )
                            return {
                                "status": "waiting",
                                "message": "Mesure ignoree: variation de distance trop brusque.",
                                "height_mm": fallback_height_mm,
                                "height_cm": (
                                    round(fallback_height_mm / 10, 1)
                                    if fallback_height_mm is not None
                                    else None
                                ),
                                "distance_mm": _last_distance_mm,
                                "source_line": decoded_line,
                                "port": port,
                            }

                        filtered_distance = None
                        if rounded_distance is not None:
                            _last_distance_mm = rounded_distance
                            filtered_distance = int(round(_height_filter.add(rounded_distance)))

                        estimated_height_mm = (
                            int(round(direct_height_mm))
                            if direct_height_mm is not None
                            else distance_to_height_mm(
                                filtered_distance,
                                sensor_height_mm=sensor_height_mm,
                            )
                        )

                    if estimated_height_mm is None:
                        return {
                            "status": "error",
                            "message": "Distance invalide pour la configuration actuelle du capteur.",
                            "height_mm": None,
                            "height_cm": None,
                            "distance_mm": filtered_distance,
                            "source_line": decoded_line,
                            "port": port,
                        }

                    return {
                        "status": "ok",
                        "message": "Lecture de taille recue depuis Arduino.",
                        "height_mm": estimated_height_mm,
                        "height_cm": round(estimated_height_mm / 10, 1),
                        "distance_mm": filtered_distance,
                        "source_line": decoded_line,
                        "port": port,
                    }

    except (OSError, SerialException) as exc:
        return {
            "status": "error",
            "message": str(exc) or "Arduino non connecte",
            "height_mm": None,
            "height_cm": None,
            "distance_mm": None,
            "source_line": "",
            "port": port,
        }

    if last_error_line:
        return {
            "status": "error",
            "message": "Arduino non connecte ou capteur en erreur.",
            "height_mm": None,
            "height_cm": None,
            "distance_mm": None,
            "source_line": last_error_line,
            "port": port,
        }

    return {
        "status": "waiting",
        "message": "Aucune lecture valide recue pour le moment.",
        "height_mm": None,
        "height_cm": None,
        "distance_mm": None,
        "source_line": last_observed_line,
        "port": port,
    }
