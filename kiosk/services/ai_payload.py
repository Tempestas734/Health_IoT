from __future__ import annotations


def build_ai_payload(*, measurements: dict | None, symptoms: dict | None, assessment: dict | None) -> dict:
    """Build a stable structured payload for local AI inference."""
    measurements = measurements or {}
    symptoms = symptoms or {}
    assessment = assessment or {}

    return {
        "bmi": _float_or_none(assessment.get("bmi")),
        "systolic_bp": _int_or_none(measurements.get("systolic_bp")),
        "diastolic_bp": _int_or_none(measurements.get("diastolic_bp")),
        "heart_rate": _int_or_none(measurements.get("heart_rate")),
        "spo2": _int_or_none(measurements.get("spo2")),
        "symptoms": normalize_symptoms(symptoms),
    }


def normalize_symptoms(symptoms: dict | None) -> dict[str, bool]:
    symptoms = symptoms or {}
    known_fields = (
        "fever",
        "cough",
        "chest_pain",
        "shortness_of_breath",
        "dizziness",
        "fatigue",
    )
    return {field: bool(symptoms.get(field, False)) for field in known_fields}


def _int_or_none(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
