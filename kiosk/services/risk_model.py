from __future__ import annotations

from typing import Literal, TypedDict


RiskLabel = Literal["low", "moderate", "high"]
UrgencyLabel = Literal["routine", "priority_review", "urgent_review"]


class RiskModelInput(TypedDict):
    bmi: float | None
    systolic_bp: int | None
    diastolic_bp: int | None
    heart_rate: int | None
    spo2: int | None
    symptoms: dict[str, bool]


class RiskModelResult(TypedDict):
    risk_score: float
    risk_label: RiskLabel
    urgency_label: UrgencyLabel
    reason_codes: list[str]
    reason_summary: str
    model_version: str


MODEL_VERSION = "v1-placeholder"


def run_placeholder_risk_model(data: RiskModelInput) -> RiskModelResult:
    """Deterministic local placeholder model based only on structured screening inputs."""
    score = 0.0
    reason_codes: list[str] = []

    bmi = data.get("bmi")
    systolic_bp = data.get("systolic_bp")
    diastolic_bp = data.get("diastolic_bp")
    heart_rate = data.get("heart_rate")
    spo2 = data.get("spo2")
    symptoms = data.get("symptoms", {})

    if bmi is not None and bmi >= 30:
        score += 0.15
        reason_codes.append("bmi_obesity_range")
    elif bmi is not None and bmi < 18.5:
        score += 0.1
        reason_codes.append("bmi_underweight_range")

    if systolic_bp is not None and diastolic_bp is not None:
        if systolic_bp >= 140 or diastolic_bp >= 90:
            score += 0.3
            reason_codes.append("blood_pressure_high_range")
        elif systolic_bp >= 120 or diastolic_bp >= 80:
            score += 0.15
            reason_codes.append("blood_pressure_above_ideal_range")
        elif systolic_bp < 90 or diastolic_bp < 60:
            score += 0.1
            reason_codes.append("blood_pressure_low_range")

    if heart_rate is not None and (heart_rate < 50 or heart_rate > 100):
        score += 0.15
        reason_codes.append("heart_rate_out_of_range")

    if spo2 is not None:
        if spo2 < 90:
            score += 0.35
            reason_codes.append("spo2_critical_low")
        elif spo2 < 95:
            score += 0.2
            reason_codes.append("spo2_below_expected_range")

    symptom_weights = {
        "chest_pain": 0.35,
        "shortness_of_breath": 0.25,
        "dizziness": 0.1,
        "fever": 0.05,
        "cough": 0.05,
        "fatigue": 0.05,
    }
    for symptom_name, weight in symptom_weights.items():
        if symptoms.get(symptom_name):
            score += weight
            reason_codes.append(f"symptom_{symptom_name}")

    if symptoms.get("fever") and symptoms.get("cough"):
        score += 0.1
        reason_codes.append("symptom_fever_with_cough")

    score = min(round(score, 2), 1.0)

    if score >= 0.7:
        risk_label: RiskLabel = "high"
        urgency_label: UrgencyLabel = "urgent_review"
    elif score >= 0.35:
        risk_label = "moderate"
        urgency_label = "priority_review"
    else:
        risk_label = "low"
        urgency_label = "routine"

    reason_summary = _build_reason_summary(reason_codes, risk_label, urgency_label)
    return {
        "risk_score": score,
        "risk_label": risk_label,
        "urgency_label": urgency_label,
        "reason_codes": reason_codes,
        "reason_summary": reason_summary,
        "model_version": MODEL_VERSION,
    }


def _build_reason_summary(
    reason_codes: list[str],
    risk_label: RiskLabel,
    urgency_label: UrgencyLabel,
) -> str:
    if not reason_codes:
        return (
            f"Placeholder triage support indicates {risk_label} screening risk with "
            f"{urgency_label.replace('_', ' ')}."
        )

    top_reasons = ", ".join(reason_codes[:3]).replace("_", " ")
    return (
        f"Placeholder triage support indicates {risk_label} screening risk with "
        f"{urgency_label.replace('_', ' ')} based on {top_reasons}."
    )
