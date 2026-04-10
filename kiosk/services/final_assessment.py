from __future__ import annotations

from .assessment import assess_measurements
from .ai_payload import build_ai_payload
from .risk_model import RiskModelResult, run_placeholder_risk_model


def build_risk_model_input(
    *,
    measurements: dict | None,
    symptoms: dict | None,
    assessment: dict,
) -> dict:
    return build_ai_payload(
        measurements=measurements,
        symptoms=symptoms,
        assessment=assessment,
    )


def merge_rule_assessment_with_ai(
    *,
    rule_assessment: dict,
    ai_result: RiskModelResult,
) -> dict:
    merged = dict(rule_assessment)
    ai_output = dict(ai_result)

    rule_flags = _extract_rule_flags(rule_assessment.get("alerts", []))
    rule_urgent_alert_count = sum(1 for alert in rule_assessment.get("alerts", []) if alert.get("level") == "urgent")
    rule_override_applied = rule_urgent_alert_count > 0

    if rule_override_applied:
        ai_output["risk_score"] = max(float(ai_output["risk_score"]), 0.85)
        ai_output["risk_label"] = "high"
        ai_output["urgency_label"] = "urgent_review"
        ai_output["reason_codes"] = [
            "rule_urgent_override",
            *[code for code in ai_output["reason_codes"] if code != "rule_urgent_override"],
        ]
        ai_output["reason_summary"] = (
            "Urgent rule-based screening flags require urgent review and override the AI triage support output."
        )

    final_risk_label = ai_output["risk_label"]
    final_urgency_label = ai_output["urgency_label"]
    recommended_action = _recommended_action(final_urgency_label)
    display_summary = _display_summary(
        rule_urgent=rule_override_applied,
        risk_label=final_risk_label,
        urgency_label=final_urgency_label,
        reason_summary=ai_output["reason_summary"],
    )

    merged["rule_urgent"] = rule_override_applied
    merged["rule_flags"] = rule_flags
    merged["ai"] = {
        **ai_output,
        "rule_override_applied": rule_override_applied,
        "rule_urgent_alert_count": rule_urgent_alert_count,
    }
    merged["final"] = {
        "risk_label": final_risk_label,
        "urgency_label": final_urgency_label,
        "urgency_display": final_urgency_label.replace("_", " "),
        "recommended_action": recommended_action,
        "display_summary": display_summary,
    }
    merged["triage_support"] = merged["final"]
    return merged


def build_screening_assessment(
    *,
    profile: dict | None,
    measurements: dict | None,
    symptoms: dict | None,
) -> dict:
    rule_assessment = assess_measurements(
        profile=profile,
        measurements=measurements,
        symptoms=symptoms,
    )
    ai_input = build_risk_model_input(
        measurements=measurements,
        symptoms=symptoms,
        assessment=rule_assessment,
    )
    ai_result = run_placeholder_risk_model(ai_input)
    return merge_rule_assessment_with_ai(
        rule_assessment=rule_assessment,
        ai_result=ai_result,
    )


def _extract_rule_flags(alerts: list[dict]) -> list[str]:
    return [str(alert.get("message", "")).strip() for alert in alerts if alert.get("message")]


def _recommended_action(urgency_label: str) -> str:
    if urgency_label == "urgent_review":
        return "Seek urgent clinical review now."
    if urgency_label == "priority_review":
        return "Arrange a priority clinical review soon."
    return "Continue with routine follow-up if symptoms persist or worsen."


def _display_summary(
    *,
    rule_urgent: bool,
    risk_label: str,
    urgency_label: str,
    reason_summary: str,
) -> str:
    if rule_urgent:
        return (
            f"Screening result indicates {risk_label} risk with {urgency_label.replace('_', ' ')}. "
            f"Urgent rule-based screening flags were identified. {reason_summary}"
        )

    return (
        f"Screening result indicates {risk_label} risk with {urgency_label.replace('_', ' ')}. "
        f"{reason_summary}"
    )
