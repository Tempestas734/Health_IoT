from __future__ import annotations

import os
import re
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


DISTANCE_PATTERN = re.compile(r"DISTANCE\s*:\s*(\d+)", re.IGNORECASE)
ERROR_PATTERN = re.compile(r"DISTANCE_ERROR|error|timeout", re.IGNORECASE)
OUTLIER_THRESHOLD_MM = 300

_height_filter = MovingAverageFilter(window_size=5)
_last_distance_mm: int | None = None
_lock = Lock()


def _serial_port() -> str:
    return os.getenv("HEIGHT_SENSOR_PORT", "/dev/ttyACM0")


def _serial_baud_rate() -> int:
    try:
        return int(os.getenv("HEIGHT_SENSOR_BAUD", "115200"))
    except ValueError:
        return 115200


def _serial_timeout() -> float:
    try:
        return float(os.getenv("HEIGHT_SENSOR_TIMEOUT", "1"))
    except ValueError:
        return 1.0


def parse_height_line(line: str) -> float | None:
    normalized = (line or "").strip()
    if not normalized:
        return None

    distance_match = DISTANCE_PATTERN.search(normalized)
    if not distance_match:
        return None
    return float(int(distance_match.group(1)))


def read_height_measurement(*, max_lines: int = 5) -> dict[str, Any]:
    global _last_distance_mm

    port = _serial_port()

    if serial is None:
        return {
            "status": "error",
            "message": "pyserial n'est pas installe.",
            "height_mm": None,
            "height_cm": None,
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

                distance_mm = parse_height_line(decoded_line)
                if distance_mm is not None:
                    with _lock:
                        rounded_distance = int(round(distance_mm))
                        if is_outlier(rounded_distance, _last_distance_mm, OUTLIER_THRESHOLD_MM):
                            return {
                                "status": "waiting",
                                "message": "Valeur de distance ignoree car instable.",
                                "height_mm": _last_distance_mm,
                                "height_cm": (
                                    round(_last_distance_mm / 10, 1)
                                    if _last_distance_mm is not None
                                    else None
                                ),
                                "source_line": decoded_line,
                                "port": port,
                            }

                        _last_distance_mm = rounded_distance
                        filtered_distance = int(round(_height_filter.add(rounded_distance)))

                    return {
                        "status": "ok",
                        "message": "Lecture de taille recue depuis Arduino.",
                        "height_mm": filtered_distance,
                        "height_cm": round(filtered_distance / 10, 1),
                        "source_line": decoded_line,
                        "port": port,
                    }

                if ERROR_PATTERN.search(decoded_line):
                    return {
                        "status": "error",
                        "message": "Arduino non connecte ou capteur en erreur.",
                        "height_mm": None,
                        "height_cm": None,
                        "source_line": decoded_line,
                        "port": port,
                    }

    except (OSError, SerialException) as exc:
        return {
            "status": "error",
            "message": str(exc) or "Arduino non connecte",
            "height_mm": None,
            "height_cm": None,
            "source_line": "",
            "port": port,
        }

    return {
        "status": "waiting",
        "message": "Aucune lecture valide recue pour le moment.",
        "height_mm": None,
        "height_cm": None,
        "source_line": "",
        "port": port,
    }
