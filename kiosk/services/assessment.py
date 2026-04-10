from __future__ import annotations


def _add_alert(alerts: list[dict], level: str, message: str) -> None:
    if any(alert["level"] == level and alert["message"] == message for alert in alerts):
        return
    alerts.append({"level": level, "message": message})


def calculate_bmi(weight_kg, height_cm) -> float | None:
    try:
        weight = float(weight_kg)
        height_m = float(height_cm) / 100
    except (TypeError, ValueError):
        return None

    if weight <= 0 or height_m <= 0:
        return None

    bmi = weight / (height_m * height_m)
    return round(bmi, 2)


def interpret_bmi(bmi) -> str | None:
    if bmi is None:
        return None
    if bmi < 18.5:
        return "Underweight"
    if bmi < 25:
        return "Normal weight"
    if bmi < 30:
        return "Overweight"
    return "Obesity"


def interpret_heart_rate(heart_rate) -> str | None:
    if heart_rate is None:
        return None
    if heart_rate < 60:
        return "Low"
    if heart_rate <= 100:
        return "Normal"
    return "High"


def interpret_blood_pressure(systolic_bp, diastolic_bp) -> str | None:
    if systolic_bp is None or diastolic_bp is None:
        return None
    systolic = int(systolic_bp)
    diastolic = int(diastolic_bp)
    if systolic < 90 or diastolic < 60:
        return "Low"
    if systolic < 120 and diastolic < 80:
        return "Normal"
    if systolic < 140 and diastolic < 90:
        return "Elevated"
    return "High"


def interpret_spo2(spo2) -> str | None:
    if spo2 is None:
        return None
    spo2_value = int(spo2)
    if spo2_value < 90:
        return "Low"
    if spo2_value <= 94:
        return "Borderline"
    return "Normal"


def build_summary(
    profile: dict | None,
    measurements: dict | None,
    symptoms: dict | None,
    assessment: dict | None,
) -> str:
    profile = profile or {}
    measurements = measurements or {}
    symptoms = symptoms or {}
    assessment = assessment or {}

    parts: list[str] = []

    if profile.get("age") is not None:
        parts.append(f"Screening completed for age {profile['age']}.")

    bmi = assessment.get("bmi")
    bmi_label = assessment.get("bmi_label")
    if bmi is not None and bmi_label:
        parts.append(f"Your BMI is {bmi_label.lower()} at {bmi:.2f}.")

    systolic_bp = measurements.get("systolic_bp")
    diastolic_bp = measurements.get("diastolic_bp")
    bp_label = assessment.get("bp_label")
    if systolic_bp is not None and diastolic_bp is not None and bp_label:
        parts.append(
            f"Your blood pressure is {bp_label.lower()} at {int(systolic_bp)}/{int(diastolic_bp)} mmHg."
        )

    heart_rate = measurements.get("heart_rate")
    hr_label = assessment.get("hr_label")
    if heart_rate is not None and hr_label:
        parts.append(f"Your heart rate is {hr_label.lower()} at {int(heart_rate)} bpm.")

    spo2 = measurements.get("spo2")
    spo2_label = assessment.get("spo2_label")
    if spo2 is not None and spo2_label:
        parts.append(f"Your oxygen saturation is {spo2_label.lower()} at {int(spo2)}%.")

    if symptoms.get("fever") and symptoms.get("cough"):
        parts.append("You reported fever and cough, which may suggest an infection.")
    if symptoms.get("chest_pain"):
        parts.append("You reported chest pain, which requires prompt clinical review.")
    if symptoms.get("shortness_of_breath"):
        parts.append("You reported shortness of breath, which should be monitored closely.")
    if symptoms.get("dizziness"):
        parts.append("You reported dizziness, which should be monitored.")
    if symptoms.get("fatigue"):
        parts.append("You reported fatigue.")

    parts.append("This is a preliminary screening and not a medical diagnosis.")
    return " ".join(parts)


def assess_measurements(
    profile: dict | None,
    measurements: dict | None,
    symptoms: dict | None = None,
) -> dict:
    profile = profile or {}
    measurements = measurements or {}
    symptoms = symptoms or {}

    bmi = calculate_bmi(
        weight_kg=measurements.get("weight_kg"),
        height_cm=measurements.get("height_cm"),
    )
    bmi_label = interpret_bmi(bmi)
    systolic_bp = measurements.get("systolic_bp")
    diastolic_bp = measurements.get("diastolic_bp")
    blood_pressure_label = interpret_blood_pressure(systolic_bp, diastolic_bp)
    heart_rate = measurements.get("heart_rate")
    heart_rate_label = interpret_heart_rate(heart_rate)
    spo2 = measurements.get("spo2")
    spo2_label = interpret_spo2(spo2)

    alerts: list[dict] = []

    if bmi is None:
        _add_alert(alerts, "warning", "BMI could not be calculated from the submitted measurements.")
    elif bmi_label == "Underweight":
        _add_alert(alerts, "warning", "BMI is in the underweight range.")
    elif bmi_label == "Overweight":
        _add_alert(alerts, "warning", "BMI is in the overweight range.")
    elif bmi_label == "Obesity":
        _add_alert(alerts, "warning", "BMI is in the obesity range.")

    if systolic_bp is not None and diastolic_bp is not None:
        if blood_pressure_label == "Low":
            _add_alert(alerts, "warning", "Blood pressure is below the expected range and should be reviewed.")
        elif blood_pressure_label == "Elevated":
            _add_alert(alerts, "warning", "Blood pressure is above the ideal range and should be monitored.")
        elif blood_pressure_label == "High":
            _add_alert(alerts, "urgent", "Blood pressure is high and should be reviewed promptly.")

    if heart_rate is not None:
        heart_rate_value = int(heart_rate)
        if heart_rate_value < 50:
            _add_alert(alerts, "warning", "Heart rate is unusually low and should be reviewed.")
        elif heart_rate_value > 100:
            _add_alert(alerts, "warning", "Heart rate is elevated and should be reviewed.")

    if spo2 is not None:
        if spo2_label == "Low":
            _add_alert(alerts, "urgent", "SpO2 is critically low and needs urgent medical attention.")
        elif spo2_label == "Borderline":
            _add_alert(alerts, "warning", "SpO2 is below the usual range and should be reviewed.")

    if symptoms.get("chest_pain"):
        _add_alert(alerts, "urgent", "Chest pain reported. Immediate clinical review is recommended.")

    if symptoms.get("shortness_of_breath") and spo2 is not None and int(spo2) < 95:
        _add_alert(alerts, "urgent", "Shortness of breath with low oxygen saturation requires urgent attention.")

    if symptoms.get("dizziness") and blood_pressure_label in {"Elevated", "High"}:
        _add_alert(alerts, "warning", "Dizziness with elevated blood pressure should be reviewed promptly.")

    if symptoms.get("fever") and symptoms.get("cough"):
        _add_alert(alerts, "warning", "Fever with cough may indicate an infection and should be assessed.")

    if not alerts:
        _add_alert(alerts, "normal", "All recorded measurements are within the expected screening range.")

    assessment = {
        "bmi": bmi,
        "bmi_label": bmi_label,
        "interpretation": bmi_label,
        "systolic_bp": systolic_bp,
        "diastolic_bp": diastolic_bp,
        "blood_pressure_label": blood_pressure_label,
        "bp_label": blood_pressure_label,
        "heart_rate": heart_rate,
        "heart_rate_label": heart_rate_label,
        "hr_label": heart_rate_label,
        "spo2": spo2,
        "spo2_label": spo2_label,
        "symptoms": symptoms,
        "alerts": alerts,
    }
    assessment["summary"] = build_summary(
        profile=profile,
        measurements=measurements,
        symptoms=symptoms,
        assessment=assessment,
    )

    return assessment
