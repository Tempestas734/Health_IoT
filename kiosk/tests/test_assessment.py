from django.test import SimpleTestCase

from kiosk.services.assessment import (
    assess_measurements,
    calculate_bmi,
    interpret_blood_pressure,
    interpret_spo2,
)


class AssessmentLogicTests(SimpleTestCase):
    def test_calculate_bmi_returns_none_for_invalid_values(self):
        self.assertIsNone(calculate_bmi(weight_kg=0, height_cm=170))
        self.assertIsNone(calculate_bmi(weight_kg=70, height_cm=0))
        self.assertIsNone(calculate_bmi(weight_kg="bad", height_cm=170))

    def test_interpret_blood_pressure_thresholds_match_current_ranges(self):
        self.assertEqual(interpret_blood_pressure(89, 59), "Low")
        self.assertEqual(interpret_blood_pressure(119, 79), "Normal")
        self.assertEqual(interpret_blood_pressure(130, 85), "Elevated")
        self.assertEqual(interpret_blood_pressure(140, 90), "High")

    def test_interpret_spo2_thresholds_match_current_ranges(self):
        self.assertEqual(interpret_spo2(89), "Low")
        self.assertEqual(interpret_spo2(92), "Borderline")
        self.assertEqual(interpret_spo2(98), "Normal")

    def test_assessment_generates_urgent_alerts_for_chest_pain_and_low_spo2(self):
        assessment = assess_measurements(
            profile={"age": 42},
            measurements={
                "height_cm": 170,
                "weight_kg": 90,
                "systolic_bp": 150,
                "diastolic_bp": 95,
                "heart_rate": 105,
                "spo2": 89,
            },
            symptoms={
                "fever": False,
                "cough": False,
                "chest_pain": True,
                "shortness_of_breath": True,
                "dizziness": True,
                "fatigue": False,
            },
        )

        messages = {alert["message"] for alert in assessment["alerts"]}
        self.assertIn("Blood pressure is high and should be reviewed promptly.", messages)
        self.assertIn("SpO2 is critically low and needs urgent medical attention.", messages)
        self.assertIn("Chest pain reported. Immediate clinical review is recommended.", messages)
        self.assertIn(
            "Shortness of breath with low oxygen saturation requires urgent attention.",
            messages,
        )
        self.assertIn("BMI is in the obesity range.", messages)

    def test_assessment_returns_normal_alert_when_everything_is_in_range(self):
        assessment = assess_measurements(
            profile={"age": 30},
            measurements={
                "height_cm": 175,
                "weight_kg": 72,
                "systolic_bp": 118,
                "diastolic_bp": 76,
                "heart_rate": 72,
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

        self.assertEqual(
            assessment["alerts"],
            [{"level": "normal", "message": "All recorded measurements are within the expected screening range."}],
        )
        self.assertIn("preliminary screening", assessment["summary"])
