from django.test import SimpleTestCase

from kiosk.services.ai_payload import build_ai_payload
from kiosk.services.final_assessment import (
    build_risk_model_input,
    build_screening_assessment,
    merge_rule_assessment_with_ai,
)
from kiosk.services.risk_model import run_placeholder_risk_model


class PlaceholderRiskModelTests(SimpleTestCase):
    def test_placeholder_model_returns_low_risk_for_reassuring_inputs(self):
        result = run_placeholder_risk_model(
            {
                "bmi": 22.5,
                "systolic_bp": 118,
                "diastolic_bp": 76,
                "heart_rate": 72,
                "spo2": 98,
                "symptoms": {
                    "fever": False,
                    "cough": False,
                    "chest_pain": False,
                    "shortness_of_breath": False,
                    "dizziness": False,
                    "fatigue": False,
                },
            }
        )

        self.assertEqual(result["risk_label"], "low")
        self.assertEqual(result["urgency_label"], "routine")
        self.assertEqual(result["model_version"], "v1-placeholder")

    def test_placeholder_model_returns_moderate_risk_for_borderline_inputs(self):
        result = run_placeholder_risk_model(
            {
                "bmi": 28.0,
                "systolic_bp": 130,
                "diastolic_bp": 84,
                "heart_rate": 88,
                "spo2": 94,
                "symptoms": {
                    "fever": False,
                    "cough": False,
                    "chest_pain": False,
                    "shortness_of_breath": False,
                    "dizziness": True,
                    "fatigue": False,
                },
            }
        )

        self.assertEqual(result["risk_label"], "moderate")
        self.assertEqual(result["urgency_label"], "priority_review")

    def test_placeholder_model_returns_high_risk_for_multiple_concerning_signals(self):
        result = run_placeholder_risk_model(
            {
                "bmi": 31.0,
                "systolic_bp": 155,
                "diastolic_bp": 96,
                "heart_rate": 110,
                "spo2": 89,
                "symptoms": {
                    "fever": False,
                    "cough": False,
                    "chest_pain": True,
                    "shortness_of_breath": True,
                    "dizziness": True,
                    "fatigue": False,
                },
            }
        )

        self.assertEqual(result["risk_label"], "high")
        self.assertEqual(result["urgency_label"], "urgent_review")
        self.assertGreaterEqual(result["risk_score"], 0.7)
        self.assertIn("symptom_chest_pain", result["reason_codes"])

    def test_placeholder_model_handles_missing_fields_safely(self):
        result = run_placeholder_risk_model(
            {
                "bmi": None,
                "systolic_bp": None,
                "diastolic_bp": None,
                "heart_rate": None,
                "spo2": None,
                "symptoms": {},
            }
        )

        self.assertEqual(result["risk_score"], 0.0)
        self.assertEqual(result["risk_label"], "low")
        self.assertEqual(result["urgency_label"], "routine")


class AIPayloadTests(SimpleTestCase):
    def test_build_ai_payload_normalizes_missing_values(self):
        payload = build_ai_payload(
            measurements={"systolic_bp": "", "heart_rate": "bad"},
            symptoms={"fever": True},
            assessment={"bmi": ""},
        )

        self.assertIsNone(payload["bmi"])
        self.assertIsNone(payload["systolic_bp"])
        self.assertIsNone(payload["heart_rate"])
        self.assertEqual(payload["symptoms"]["fever"], True)
        self.assertEqual(payload["symptoms"]["cough"], False)


class TriageSupportMergeTests(SimpleTestCase):
    def test_build_risk_model_input_uses_structured_assessment_data(self):
        assessment = {
            "bmi": 27.1,
            "alerts": [{"level": "warning", "message": "Blood pressure is above the ideal range and should be monitored."}],
        }
        model_input = build_risk_model_input(
            measurements={"systolic_bp": 132, "diastolic_bp": 84, "heart_rate": 88, "spo2": 96},
            symptoms={"fever": True, "cough": False},
            assessment=assessment,
        )

        self.assertEqual(model_input["bmi"], 27.1)
        self.assertEqual(model_input["symptoms"]["fever"], True)
        self.assertEqual(model_input["symptoms"]["cough"], False)

    def test_rule_based_urgent_alert_overrides_model_output(self):
        assessment = {
            "alerts": [{"level": "urgent", "message": "Chest pain reported. Immediate clinical review is recommended."}],
        }
        model_output = {
            "risk_score": 0.2,
            "risk_label": "low",
            "urgency_label": "routine",
            "reason_codes": ["age_65_or_above"],
            "reason_summary": "Placeholder triage support indicates low screening risk with routine review.",
            "model_version": "v1-placeholder",
        }

        merged = merge_rule_assessment_with_ai(rule_assessment=assessment, ai_result=model_output)

        self.assertEqual(merged["triage_support"]["risk_label"], "high")
        self.assertEqual(merged["triage_support"]["urgency_label"], "urgent_review")
        self.assertTrue(merged["ai"]["rule_override_applied"])
        self.assertEqual(merged["ai"]["reason_codes"][0], "rule_urgent_override")
        self.assertTrue(merged["rule_urgent"])
        self.assertEqual(merged["final"]["recommended_action"], "Seek urgent clinical review now.")

    def test_non_urgent_rule_allows_ai_risk_and_urgency(self):
        rule_assessment = {"alerts": [{"level": "warning", "message": "Review advised."}]}
        ai_result = {
            "risk_score": 0.48,
            "risk_label": "moderate",
            "urgency_label": "priority_review",
            "reason_codes": ["blood_pressure_above_ideal_range"],
            "reason_summary": "Placeholder triage support indicates moderate screening risk with priority review.",
            "model_version": "v1-placeholder",
        }

        merged = merge_rule_assessment_with_ai(rule_assessment=rule_assessment, ai_result=ai_result)

        self.assertFalse(merged["rule_urgent"])
        self.assertEqual(merged["final"]["risk_label"], "moderate")
        self.assertEqual(merged["final"]["urgency_label"], "priority_review")
        self.assertEqual(merged["final"]["recommended_action"], "Arrange a priority clinical review soon.")

    def test_summary_and_action_text_are_stable(self):
        merged = merge_rule_assessment_with_ai(
            rule_assessment={"alerts": []},
            ai_result={
                "risk_score": 0.1,
                "risk_label": "low",
                "urgency_label": "routine",
                "reason_codes": [],
                "reason_summary": "Placeholder triage support indicates low screening risk with routine.",
                "model_version": "v1-placeholder",
            },
        )

        self.assertEqual(
            merged["final"]["display_summary"],
            "Screening result indicates low risk with routine. Placeholder triage support indicates low screening risk with routine.",
        )
        self.assertEqual(
            merged["final"]["recommended_action"],
            "Continue with routine follow-up if symptoms persist or worsen.",
        )

    def test_build_screening_assessment_preserves_rule_alerts_and_adds_merged_result(self):
        merged_assessment = build_screening_assessment(
            profile={"age": 42, "sex": "female"},
            measurements={
                "height_cm": 170,
                "weight_kg": 75,
                "systolic_bp": 145,
                "diastolic_bp": 92,
                "heart_rate": 82,
                "spo2": 98,
            },
            symptoms={
                "fever": False,
                "cough": False,
                "chest_pain": False,
                "shortness_of_breath": False,
                "dizziness": False,
                "fatigue": False,
            },
        )

        self.assertTrue(any(alert["level"] == "urgent" for alert in merged_assessment["alerts"]))
        self.assertIn("ai", merged_assessment)
        self.assertIn("final", merged_assessment)
        self.assertEqual(merged_assessment["final"]["urgency_label"], "urgent_review")
        self.assertTrue(merged_assessment["ai"]["rule_override_applied"])
