from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

ESC = b"\x1b"
GS = b"\x1d"
LF = b"\x0a"

DEFAULT_DEVICE_PATH = "/dev/usb/lp0"
RECEIPT_WIDTH = 48
DEFAULT_ENCODING = "ascii"
DEFAULT_TITLE = "Health Check"
DEFAULT_SUBTITLE = "by Nouha/Aya/Oumaima"


class ReceiptPrinterError(RuntimeError):
    """Raised when the thermal printer cannot be accessed or written to."""


@dataclass(slots=True)
class ReceiptData:
    patient_name: str
    patient_sex: str
    patient_age: str
    measured_at: datetime
    bmi_value: str
    bmi_label: str
    blood_pressure_value: str
    blood_pressure_label: str
    spo2: str
    spo2_label: str
    heart_rate: str
    heart_rate_label: str
    qr_data: str | None = None
    title: str = DEFAULT_TITLE
    subtitle: str = DEFAULT_SUBTITLE


def _initialize_printer() -> bytes:
    return ESC + b"@" + ESC + b"2"


def _set_bold(enabled: bool) -> bytes:
    return ESC + b"E" + (b"\x01" if enabled else b"\x00")


def _set_align(mode: str) -> bytes:
    mapping = {
        "left": b"\x00",
        "center": b"\x01",
        "right": b"\x02",
    }
    return ESC + b"a" + mapping.get(mode, b"\x00")


def _feed(lines: int = 1) -> bytes:
    safe_lines = max(0, min(10, int(lines)))
    return ESC + b"d" + bytes([safe_lines])


def _cut_paper() -> bytes:
    return GS + b"V" + b"\x00"


def _safe_text(value: Any, fallback: str = "N/A") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _safe_number(value: Any, suffix: str = "", digits: int = 0, fallback: str = "N/A") -> str:
    if value in (None, ""):
        return fallback

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return _safe_text(value, fallback=fallback)

    if digits > 0:
        formatted = f"{numeric:.{digits}f}"
    else:
        formatted = str(int(round(numeric)))

    return f"{formatted}{suffix}"


def _normalize_risk_level(value: Any) -> str:
    text = _safe_text(value).replace("_", " ")
    return text.title()


def _normalize_sex(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "female":
        return "Female"
    if normalized == "male":
        return "Male"
    return "N/A"


def _normalize_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value

    if isinstance(value, str) and value.strip():
        normalized = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue

    return datetime.now()


def _fit(text: str, width: int, align: str = "left") -> str:
    value = text[:width]
    if align == "right":
        return value.rjust(width)
    if align == "center":
        return value.center(width)
    return value.ljust(width)


def _center_text(text: str, width: int = RECEIPT_WIDTH) -> str:
    return _fit(text.strip(), width, align="center")


def _divider(char: str = "-") -> str:
    return char * RECEIPT_WIDTH


def _kv_line(label: str, value: str, width: int = RECEIPT_WIDTH) -> str:
    left = f"{label}:"
    usable_value_width = max(0, width - len(left) - 1)
    return f"{left} {_fit(value, usable_value_width, align='right')}"


def _measurement_line(label: str, value: str, unit: str) -> str:
    left_width = 20
    value_width = 12
    unit_width = RECEIPT_WIDTH - left_width - value_width
    return (
        f"{_fit(label, left_width, 'left')}"
        f"{_fit(value, value_width, 'right')}"
        f"{_fit(unit, unit_width, 'right')}"
    )


def _patient_summary_line(name: str, sex: str, age: str) -> str:
    return _center_text(f"{name} | {sex} | {age}")


def _compact_measurement_line(title: str, value: str, interpretation: str) -> str:
    left_width = 16
    center_width = 14
    right_width = RECEIPT_WIDTH - left_width - center_width
    return (
        f"{_fit(title, left_width, 'left')}"
        f"{_fit(value, center_width, 'center')}"
        f"{_fit(interpretation, right_width, 'right')}"
    )


def _build_qr_placeholder_block(qr_data: str | None) -> list[str]:
    if not qr_data:
        return []

    return [
        _divider(),
        _center_text("QR CODE"),
        _center_text("[ Scan at nurse station ]"),
        _center_text(qr_data[:RECEIPT_WIDTH]),
    ]


def build_receipt_text(result: dict[str, Any], guest_profile: dict[str, Any] | None = None) -> str:
    guest_profile = guest_profile or {}
    measured_at = _normalize_datetime(
        result.get("measured_at")
        or result.get("created_at")
        or result.get("timestamp")
    )

    receipt = ReceiptData(
        patient_name=_safe_text(
            guest_profile.get("full_name")
            or guest_profile.get("name")
            or result.get("patient_name"),
            fallback="Guest",
        ),
        patient_sex=_normalize_sex(guest_profile.get("sex") or result.get("sex")),
        patient_age=_safe_text(
            f"{guest_profile.get('age')} y.o"
            if guest_profile.get("age") not in (None, "")
            else result.get("age"),
            fallback="N/A",
        ),
        measured_at=measured_at,
        bmi_value=_safe_number(result.get("bmi"), digits=1),
        bmi_label=_safe_text(result.get("bmi_label") or result.get("interpretation")),
        blood_pressure_value=(
            f"{int(round(float(result.get('systolic_bp'))))}/{int(round(float(result.get('diastolic_bp'))))} mmHg"
            if result.get("systolic_bp") is not None and result.get("diastolic_bp") is not None
            else "N/A"
        ),
        blood_pressure_label=_safe_text(result.get("blood_pressure_label") or result.get("bp_label")),
        spo2=_safe_number(result.get("spo2"), suffix=" %"),
        spo2_label=_safe_text(result.get("spo2_label")),
        heart_rate=_safe_number(result.get("heart_rate"), suffix=" bpm"),
        heart_rate_label=_safe_text(result.get("heart_rate_label") or result.get("hr_label")),
        qr_data=_safe_text(result.get("qr_data"), fallback="") or None,
    )
    return render_receipt_text(receipt)


def render_receipt_text(receipt: ReceiptData) -> str:
    lines = [
        _center_text(receipt.title),
        _center_text(receipt.subtitle),
        _divider("="),
        _patient_summary_line(
            _safe_text(receipt.patient_name, fallback="Guest"),
            _safe_text(receipt.patient_sex),
            _safe_text(receipt.patient_age),
        ),
        _center_text(
            f"{receipt.measured_at.strftime('%Y-%m-%d')} | {receipt.measured_at.strftime('%H:%M:%S')}"
        ),
        _divider(),
        _center_text("MEASUREMENTS"),
        _divider(),
        _compact_measurement_line("BMI", receipt.bmi_value, receipt.bmi_label),
        _compact_measurement_line("Blood Pressure", receipt.blood_pressure_value, receipt.blood_pressure_label),
        _compact_measurement_line("SpO2", receipt.spo2, receipt.spo2_label),
        _compact_measurement_line("Heart Rate", receipt.heart_rate, receipt.heart_rate_label),
        _divider(),
    ]

    lines.extend(_build_qr_placeholder_block(receipt.qr_data))
    lines.extend(
        [
            _divider("="),
            _center_text("Please keep this receipt"),
            _center_text("for your medical record"),
            "",
            "",
        ]
    )

    return "\n".join(lines)


def _text_to_escpos_payload(text: str) -> bytes:
    lines = text.splitlines()
    payload = bytearray()
    payload.extend(_initialize_printer())

    centered_headers = {
        DEFAULT_TITLE,
        DEFAULT_SUBTITLE,
        "MEASUREMENTS",
        "QR CODE",
        "[ Scan at nurse station ]",
        "Please keep this receipt",
        "for your medical record",
    }
    centered_prefixes = ("Guest |", "Male |", "Female |")

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            payload.extend(LF)
            continue

        if (
            stripped in centered_headers
            or stripped.startswith("=")
            or stripped.startswith("-")
            or " | " in stripped
            or stripped.startswith(centered_prefixes)
        ):
            payload.extend(_set_align("center"))
            if stripped in {DEFAULT_TITLE, "MEASUREMENTS", "QR CODE"}:
                payload.extend(_set_bold(True))
            payload.extend(stripped.encode(DEFAULT_ENCODING, errors="replace"))
            if stripped in {DEFAULT_TITLE, "MEASUREMENTS", "QR CODE"}:
                payload.extend(_set_bold(False))
            payload.extend(LF)
            payload.extend(_set_align("left"))
            continue

        payload.extend(_set_align("left"))
        payload.extend(line.encode(DEFAULT_ENCODING, errors="replace"))
        payload.extend(LF)

    payload.extend(_feed(4))
    payload.extend(_cut_paper())
    return bytes(payload)


def _write_to_device(payload: bytes, device_path: str) -> None:
    try:
        with open(device_path, "wb", buffering=0) as printer_device:
            printer_device.write(payload)
            printer_device.flush()
    except FileNotFoundError as exc:
        raise ReceiptPrinterError(
            f"Printer device not found: {device_path}. Check USB connection and device mapping."
        ) from exc
    except PermissionError as exc:
        raise ReceiptPrinterError(
            f"Permission denied for printer device: {device_path}."
        ) from exc
    except OSError as exc:
        raise ReceiptPrinterError(
            f"Failed to write to printer device {device_path}: {exc.strerror or exc}"
        ) from exc


def print_receipt(text: str, device_path: str | None = None) -> None:
    payload = _text_to_escpos_payload(text)
    _write_to_device(payload, device_path or os.getenv("THERMAL_PRINTER_DEVICE", DEFAULT_DEVICE_PATH))


def print_receipt_data(receipt: ReceiptData, device_path: str | None = None) -> None:
    print_receipt(render_receipt_text(receipt), device_path=device_path)


def test_print(device_path: str | None = None) -> None:
    sample = ReceiptData(
        patient_name="Guest",
        patient_sex="Female",
        patient_age="31 y.o",
        measured_at=datetime.now(),
        bmi_value="23.4",
        bmi_label="Normal weight",
        blood_pressure_value="118/76 mmHg",
        blood_pressure_label="Normal",
        spo2="98 %",
        spo2_label="Normal",
        heart_rate="72 bpm",
        heart_rate_label="Normal",
        qr_data="TEST-QR-PLACEHOLDER",
    )
    print_receipt_data(sample, device_path=device_path)


if __name__ == "__main__":
    test_print()
