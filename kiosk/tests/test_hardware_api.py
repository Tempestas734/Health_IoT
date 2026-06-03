from unittest.mock import patch

from django.test import SimpleTestCase


class HardwareApiTests(SimpleTestCase):
    def test_api_height_returns_normalized_payload(self):
        with patch(
            "kiosk.views.read_height_measurement",
            return_value={"height_mm": 523, "status": "ok", "message": "ok"},
        ):
            response = self.client.get("/api/height/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"height_mm": 523, "status": "ok", "message": "ok"})

    def test_api_vitals_raw_returns_sensor_payload(self):
        with patch(
            "kiosk.views.read_max30102_raw",
            return_value={
                "red": 45670,
                "ir": 62000,
                "heart_rate": 72,
                "spo2": 98,
                "status": "ok",
            },
        ):
            response = self.client.get("/api/vitals/raw/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"red": 45670, "ir": 62000, "heart_rate": 72, "spo2": 98, "status": "ok"},
        )
