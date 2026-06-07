from unittest.mock import patch

from django.test import TestCase
from django.test import Client

from kiosk.supabase import (
    PIN_ALREADY_ACTIVE_MESSAGE,
    PIN_INVALID_STATUS_MESSAGE,
    PIN_NOT_FOUND_MESSAGE,
    SupabaseServiceError,
)


class FakeRepository:
    def __init__(self, *, fail_on=None):
        self.fail_on = fail_on or set()
        self.calls = []

    def _record(self, name, payload):
        self.calls.append((name, payload))
        if name in self.fail_on:
            raise SupabaseServiceError(f"{name} failed")

    def create_guest_session(self, *, terms_version, language, device_id):
        payload = {
            "terms_version": terms_version,
            "language": language,
            "device_id": device_id,
        }
        self._record("create_guest_session", payload)
        return {"id": "session-123"}

    def activate_pending_session(self, *, session_pin, terms_version, language, device_id):
        payload = {
            "session_pin": session_pin,
            "terms_version": terms_version,
            "language": language,
            "device_id": device_id,
        }
        self._record("activate_pending_session", payload)
        return {
            "id": "session-patient-1",
            "patient_id": "patient-1",
            "consent_id": "consent-1",
            "mode": "patient",
        }

    def save_guest_profile(self, *, session_id, sex, age):
        payload = {"session_id": session_id, "sex": sex, "age": age}
        self._record("save_guest_profile", payload)
        return payload

    def save_measurements(self, *, session_id, height_cm, weight_kg, spo2=None):
        payload = {
            "session_id": session_id,
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "spo2": spo2,
        }
        self._record("save_measurements", payload)
        return [payload]

    def save_blood_pressure(self, *, session_id, systolic_bp, diastolic_bp):
        payload = {
            "session_id": session_id,
            "systolic_bp": systolic_bp,
            "diastolic_bp": diastolic_bp,
        }
        self._record("save_blood_pressure", payload)
        return [payload]

    def save_vitals(self, *, session_id, heart_rate, spo2=None):
        payload = {"session_id": session_id, "heart_rate": heart_rate, "spo2": spo2}
        self._record("save_vitals", payload)
        return [payload]

    def save_symptoms(
        self,
        *,
        session_id,
        fever,
        cough,
        chest_pain,
        shortness_of_breath,
        dizziness,
        fatigue,
    ):
        payload = {
            "session_id": session_id,
            "fever": fever,
            "cough": cough,
            "chest_pain": chest_pain,
            "shortness_of_breath": shortness_of_breath,
            "dizziness": dizziness,
            "fatigue": fatigue,
        }
        self._record("save_symptoms", payload)
        return payload

    def save_assessment(self, *, session_id, assessment):
        payload = {"session_id": session_id, "assessment": assessment}
        self._record("save_assessment", payload)
        return payload

    def get_professional_snapshot(self, *, session_pin):
        payload = {"session_pin": session_pin}
        self._record("get_professional_snapshot", payload)
        if session_pin != "157021":
            return None
        return {
            "session_pin": session_pin,
            "session_id": "session-active-1",
            "patient_id": "patient-lookup-1",
            "current_step": "active",
            "guest_profile": {},
            "measurements": {"height_cm": 170, "weight_kg": 70},
            "symptoms": None,
            "assessment": None,
        }


class ScreeningFlowTests(TestCase):
    def setUp(self):
        super().setUp()
        self.repository = FakeRepository()
        self.repository_patcher = patch("kiosk.views.get_screening_repository", return_value=self.repository)
        self.repository_patcher.start()
        self.addCleanup(self.repository_patcher.stop)

    def test_html_flow_redirects_when_step_is_skipped(self):
        response = self.client.get("/vitals")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")

    def test_api_flow_rejects_skipped_step_with_redirect_hint(self):
        response = self.client.post(
            "/api/measurements/submit",
            data='{"height": 175, "weight": 72.4}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["redirect_to"], "/")

    def test_complete_api_flow_builds_result_and_stores_session_state(self):
        consent_response = self.client.post(
            "/api/consent/start-session",
            data='{"agree": true, "device_id": "DEV-PI-001", "terms_version": "v1", "language": "fr"}',
            content_type="application/json",
        )
        self.assertEqual(consent_response.status_code, 201)
        self.assertRegex(consent_response.json()["session_pin"], r"^\d{6}$")
        self.assertEqual(consent_response.json()["professional_url"], "/professional")

        guest_response = self.client.post(
            "/api/guest/profile",
            data='{"sex": "F", "age": 31}',
            content_type="application/json",
        )
        self.assertEqual(guest_response.status_code, 201)

        measure_response = self.client.post(
            "/api/measurements/submit",
            data='{"height": 175, "weight": 72.4}',
            content_type="application/json",
        )
        self.assertEqual(measure_response.status_code, 200)

        blood_pressure_response = self.client.post(
            "/api/blood-pressure/submit",
            data='{"systolic_bp": 118, "diastolic_bp": 76}',
            content_type="application/json",
        )
        self.assertEqual(blood_pressure_response.status_code, 200)

        vitals_response = self.client.post(
            "/api/vitals/submit",
            data='{"heart_rate": 72, "spo2": 98}',
            content_type="application/json",
        )
        self.assertEqual(vitals_response.status_code, 200)

        symptoms_response = self.client.post(
            "/api/symptoms/submit",
            data=(
                '{"fever": "no", "cough": "no", "chest_pain": "no", '
                '"shortness_of_breath": "no", "dizziness": "no", "fatigue": "no"}'
            ),
            content_type="application/json",
        )
        self.assertEqual(symptoms_response.status_code, 200)
        self.assertEqual(symptoms_response.json()["alerts"][0]["level"], "normal")
        self.assertIn("ai", symptoms_response.json())
        self.assertIn("final", symptoms_response.json())
        self.assertEqual(symptoms_response.json()["ai"]["model_version"], "v1-placeholder")

        session = self.client.session
        self.assertEqual(session["session_id"], "session-123")
        self.assertEqual(session["guest_profile"], {"sex": "female", "age": 31})
        self.assertEqual(session["measurements"], {"height_cm": 175.0, "weight_kg": 72.4})
        self.assertEqual(session["blood_pressure"], {"systolic_bp": 118, "diastolic_bp": 76})
        self.assertEqual(session["vitals"], {"heart_rate": 72, "spo2": 98})
        self.assertRegex(session["session_pin"], r"^\d{6}$")
        self.assertIn("assessment_result", session)
        self.assertIn("ai", session["assessment_result"])
        self.assertIn("final", session["assessment_result"])

        result_response = self.client.get("/result")
        self.assertEqual(result_response.status_code, 200)
        self.assertContains(result_response, "Your Health Results")
        self.assertContains(result_response, "Session PIN")
        self.assertContains(result_response, "Body Mass Index")
        self.assertEqual(result_response.context["result"]["final"]["urgency_label"], "routine")

        professional_client = Client()
        professional_response = professional_client.get(f"/professional/{session['session_pin']}")
        self.assertEqual(professional_response.status_code, 200)
        self.assertContains(professional_response, "Professional Review")
        self.assertContains(professional_response, session["session_pin"])
        self.assertEqual(
            professional_response.context["result"]["final"]["urgency_label"],
            "routine",
        )

    def test_pin_activation_redirects_to_professionnelle_capture(self):
        response = self.client.post(
            "/api/session-activation/start-session",
            data='{"session_pin": "563272", "device_id": "DEV-PI-001", "terms_version": "v1", "language": "fr"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["next_path"], "/professionnelle/capture")
        session = self.client.session
        self.assertEqual(session["session_id"], "session-patient-1")
        self.assertEqual(session["patient_id"], "patient-1")
        self.assertEqual(session["current_step"], "measure")

    def test_professionnelle_capture_submits_measurements_and_vitals(self):
        session = self.client.session
        session["session_id"] = "session-patient-1"
        session["session_pin"] = "563272"
        session["session_mode"] = "patient"
        session["guest"] = {"patient_id": "patient-1", "mode": "patient"}
        session["current_step"] = "measure"
        session.save()

        response = self.client.post(
            "/api/professionnelle/capture/submit",
            data='{"height": 175, "weight": 72.4, "heart_rate": 72, "spo2": 98}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["next_path"], "/blood-pressure")
        refreshed_session = self.client.session
        self.assertEqual(refreshed_session["measurements"], {"height_cm": 175.0, "weight_kg": 72.4})
        self.assertEqual(refreshed_session["vitals"], {"heart_rate": 72, "spo2": 98})

    def test_changing_measurements_clears_dependent_session_data(self):
        session = self.client.session
        session["session_id"] = "session-123"
        session["measurements"] = {"height_cm": 170.0, "weight_kg": 70.0}
        session["blood_pressure"] = {"systolic_bp": 120, "diastolic_bp": 80}
        session["vitals"] = {"heart_rate": 72, "spo2": 98}
        session["symptoms"] = {"fever": False}
        session["assessment_result"] = {"summary": "old"}
        session.save()

        response = self.client.post(
            "/api/measurements/submit",
            data='{"height": 180, "weight": 80}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        refreshed_session = self.client.session
        self.assertEqual(refreshed_session["measurements"], {"height_cm": 180.0, "weight_kg": 80.0})
        self.assertNotIn("blood_pressure", refreshed_session)
        self.assertNotIn("vitals", refreshed_session)
        self.assertNotIn("symptoms", refreshed_session)
        self.assertNotIn("assessment_result", refreshed_session)

    def test_supabase_failure_returns_safe_json_error(self):
        failing_repository = FakeRepository(fail_on={"save_guest_profile"})
        with patch("kiosk.views.get_screening_repository", return_value=failing_repository):
            self.client.post(
                "/api/consent/start-session",
                data='{"agree": true, "device_id": "DEV-PI-001", "terms_version": "v1", "language": "fr"}',
                content_type="application/json",
            )
            response = self.client.post(
                "/api/guest/profile",
                data='{"sex": "M", "age": 40}',
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "save_guest_profile failed")

    def test_pin_activation_messages_are_user_facing(self):
        self.assertEqual(PIN_NOT_FOUND_MESSAGE, "Aucune session en attente n'a ete trouvee pour ce PIN.")
        self.assertEqual(PIN_ALREADY_ACTIVE_MESSAGE, "Cette session est deja active.")
        self.assertEqual(
            PIN_INVALID_STATUS_MESSAGE,
            "Cette session ne peut pas etre activee depuis son statut actuel.",
        )

    def test_professional_lookup_uses_repository_when_cache_is_empty(self):
        with patch("kiosk.views.get_session_snapshot", return_value=None):
            response = self.client.get("/professional?pin=157021")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Session 157021")
        self.assertContains(response, "session-active-1")
