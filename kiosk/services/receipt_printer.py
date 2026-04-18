from __future__ import annotations

import os
from datetime import datetime
from typing import Any

ESC = b"\x1b"
GS = b"\x1d"
RECEIPT_WIDTH = 42


def _safe_line(label: str, value: Any, suffix: str = "") -> str:
    if value is None or value == "":
        return f"{label}: N/A"
    return f"{label}: {value}{suffix}"


def _center(text: str, width: int = RECEIPT_WIDTH) -> str:
    normalized = (text or "").strip()
    if not normalized:
        return ""
    if len(normalized) >= width:
        return normalized[:width]
    return normalized.center(width)


def _divider(char: str = "-") -> str:
    return char * RECEIPT_WIDTH


def _normalize_label(value: Any) -> str:
    if value is None or value == "":
        return "N/A"
    text = str(value).replace("_", " ").strip()
    return text.title() if text else "N/A"


def _status_line(label: str, value: Any) -> str:
    return f"Status: {_normalize_label(value)}"


def _format_measurement_block(title: str, value_line: str, status: Any) -> list[str]:
    return [
        title.upper(),
        value_line,
        _status_line("Status", status),
        "",
    ]


def _sex_display(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "male":
        return "Male"
    if normalized == "female":
        return "Female"
    return "N/A"


def build_receipt_text(result: dict[str, Any], guest_profile: dict[str, Any] | None = None) -> str:
    guest_profile = guest_profile or {}
    sex = guest_profile.get("sex")
    age = guest_profile.get("age")
    guest_name = guest_profile.get("full_name") or guest_profile.get("name")

    lines = [
        "",
        _center("+++"),
        _center("HEALTH CHECK"),
        _center("Medical Device Result"),
        _divider("="),
        datetime.now().strftime("Printed: %Y-%m-%d %H:%M"),
        f"Sex: {_sex_display(sex)}",
        f"Age: {age if age not in (None, '') else 'N/A'}",
    ]

    if guest_name:
        lines.append(f"Guest: {guest_name}")

    lines.extend(
        [
            _divider(),
            "",
        ]
    )

    lines.extend(
        _format_measurement_block(
            "BMI",
            _safe_line(
                "Value",
                f"{float(result['bmi']):.1f}" if result.get("bmi") is not None else None,
            ),
            result.get("interpretation"),
        )
    )
    lines.extend(
        _format_measurement_block(
            "Blood Pressure",
            _safe_line(
                "Value",
                (
                    f"{int(round(float(result['systolic_bp'])))}"
                    f"/{int(round(float(result['diastolic_bp'])))} mmHg"
                )
                if result.get("systolic_bp") is not None and result.get("diastolic_bp") is not None
                else None,
            ),
            result.get("blood_pressure_label"),
        )
    )
    lines.extend(
        _format_measurement_block(
            "Heart Rate",
            _safe_line(
                "Value",
                int(round(float(result["heart_rate"]))) if result.get("heart_rate") is not None else None,
                " bpm",
            ),
            result.get("heart_rate_label"),
        )
    )
    lines.extend(
        _format_measurement_block(
            "SpO2",
            _safe_line(
                "Value",
                int(round(float(result["spo2"]))) if result.get("spo2") is not None else None,
                "%",
            ),
            (
                "excellent"
                if result.get("spo2") is not None and float(result["spo2"]) >= 95
                else "monitor"
                if result.get("spo2") is not None and float(result["spo2"]) >= 92
                else "low"
                if result.get("spo2") is not None
                else None
            ),
        )
    )

    lines.extend(
        [
            _divider(),
            _center("Thank You For Using"),
            _center("The Device"),
            "\n\n\n",
        ]
    )
    return "\n".join(lines)


def _cut_command() -> bytes:
    cut_mode = os.getenv("THERMAL_PRINTER_CUT_MODE", "full").strip().lower()
    feed_lines = os.getenv("THERMAL_PRINTER_FEED_LINES", "4").strip()

    try:
        feed_value = max(0, min(10, int(feed_lines)))
    except ValueError:
        feed_value = 4

    # ESC d n: print and feed n lines before cutting.
    feed_command = ESC + b"d" + bytes([feed_value])

    # GS V 0: full cut, GS V 1: partial cut for most ESC/POS printers.
    cut_command = GS + b"V" + (b"\x01" if cut_mode == "partial" else b"\x00")
    return feed_command + cut_command


def print_receipt(text: str) -> None:
    printer_name = os.getenv("THERMAL_PRINTER_NAME")
    if not printer_name:
        raise RuntimeError("THERMAL_PRINTER_NAME is not configured.")

    try:
        import win32print  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "pywin32 is not installed. Install it to enable direct receipt printing."
        ) from exc

    handle = win32print.OpenPrinter(printer_name)
    try:
        document_info = ("Medical Device Result", None, "RAW")
        win32print.StartDocPrinter(handle, 1, document_info)
        win32print.StartPagePrinter(handle)
        payload = text.encode("ascii", errors="replace") + _cut_command()
        win32print.WritePrinter(handle, payload)
        win32print.EndPagePrinter(handle)
        win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)
