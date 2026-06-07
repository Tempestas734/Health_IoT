import os

import requests


class SupabaseServiceError(RuntimeError):
    """Raised when a Supabase data-access operation fails."""


PIN_NOT_FOUND_MESSAGE = "Aucune session en attente n'a ete trouvee pour ce PIN."
PIN_ALREADY_ACTIVE_MESSAGE = "Cette session est deja active."
PIN_INVALID_STATUS_MESSAGE = "Cette session ne peut pas etre activee depuis son statut actuel."


def _get_supabase_settings() -> tuple[str, str]:
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        raise SupabaseServiceError("Missing SUPABASE_URL or SUPABASE_ANON_KEY in .env")
    return supabase_url, anon_key


def _format_request_exception(exc: requests.RequestException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    normalized = message.lower()

    if "failed to resolve" in normalized or "name or service not known" in normalized:
        return (
            "Unable to reach Supabase. Check SUPABASE_URL and DNS/network connectivity."
        )

    if "nodename nor servname provided" in normalized:
        return (
            "Unable to reach Supabase. Check SUPABASE_URL and DNS/network connectivity."
        )

    if isinstance(exc, requests.Timeout):
        return "Supabase request timed out. Check network connectivity and service availability."

    if isinstance(exc, requests.ConnectionError):
        return "Unable to connect to Supabase. Check network connectivity and service availability."

    return f"Supabase request failed: {message}"


def _headers(*, prefer: str = "return=representation") -> dict:
    _, anon_key = _get_supabase_settings()
    return {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _request(method: str, path: str, *, json_payload: dict | None = None, params: dict | None = None):
    supabase_url, _ = _get_supabase_settings()
    url = f"{supabase_url}/rest/v1/{path}"
    try:
        response = requests.request(
            method,
            url,
            headers=_headers(),
            json=json_payload,
            params=params,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise SupabaseServiceError(_format_request_exception(exc)) from exc

    if not response.ok:
        raise SupabaseServiceError(f"Supabase request failed: {response.status_code} {response.text}")

    return response


def _require_session_id(session_id) -> str:
    if session_id in (None, ""):
        raise SupabaseServiceError("A valid session_id is required.")
    return str(session_id)


def _session_exists(session_id) -> bool:
    response = _request(
        "GET",
        "exam_sessions",
        params={"id": f"eq.{session_id}", "select": "id", "limit": 1},
    )
    data = response.json()
    return bool(data)


def _ensure_session_exists(session_id) -> str:
    normalized_session_id = _require_session_id(session_id)
    if not _session_exists(normalized_session_id):
        raise SupabaseServiceError("Session not found in Supabase.")
    return normalized_session_id


def sb_insert(table: str, payload: dict) -> dict:
    """
    Insert a single row into Supabase table using PostgREST.
    Returns the inserted row (Prefer: return=representation).
    """
    response = _request("POST", table, json_payload=payload)
    data = response.json()
    # PostgREST returns a list when inserting
    return data[0] if isinstance(data, list) and data else data


def create_consent(*, terms_version: str, language: str) -> dict:
    return sb_insert(
        "consents",
        {
            "terms_version": terms_version,
            "language": language,
        },
    )


def create_guest_session(*, terms_version: str, language: str, device_id: str) -> dict:
    consent = create_consent(terms_version=terms_version, language=language)
    return sb_insert(
        "exam_sessions",
        {
            "device_id": device_id,
            "consent_id": consent["id"],
            "status": "active",
        },
    )


def _get_session_by_pin(session_pin: str) -> dict | None:
    response = _request(
        "GET",
        "exam_sessions",
        params={
            "session_pin": f"eq.{session_pin}",
            "select": "id,patient_id,session_pin,status,mode",
            "order": "created_at.desc",
            "limit": 1,
        },
    )
    data = response.json()
    return data[0] if data else None


def activate_pending_session(
    *,
    session_pin: str,
    terms_version: str,
    language: str,
    device_id: str,
) -> dict:
    session_row = _get_session_by_pin(session_pin)
    if not session_row:
        raise SupabaseServiceError(PIN_NOT_FOUND_MESSAGE)

    status = str(session_row.get("status") or "").strip().lower()
    if status == "active":
        raise SupabaseServiceError(PIN_ALREADY_ACTIVE_MESSAGE)
    if status != "pending":
        raise SupabaseServiceError(PIN_INVALID_STATUS_MESSAGE)

    consent = create_consent(terms_version=terms_version, language=language)
    response = _request(
        "PATCH",
        "exam_sessions",
        json_payload={
            "device_id": device_id,
            "consent_id": consent["id"],
            "status": "active",
        },
        params={
            "id": f"eq.{session_row['id']}",
            "select": "id,patient_id,session_pin,status,mode",
        },
    )
    data = response.json()
    updated_row = data[0] if isinstance(data, list) and data else None
    if not updated_row:
        raise SupabaseServiceError(
            "La session a ete trouvee mais n'a pas pu etre activee dans Supabase. "
            "Verifiez les permissions UPDATE/RLS sur exam_sessions."
        )

    updated_row["consent_id"] = consent["id"]
    updated_row["device_id"] = device_id
    return updated_row


def get_professional_snapshot(*, session_pin: str) -> dict | None:
    response = _request(
        "GET",
        "exam_sessions",
        params={
            "session_pin": f"eq.{session_pin}",
            "status": "eq.active",
            "select": "id,patient_id,session_pin,status",
            "order": "created_at.desc",
            "limit": 1,
        },
    )
    data = response.json()
    session_row = data[0] if data else None
    if not session_row:
        return None

    measurements: dict = {}
    try:
        response = _request(
            "GET",
            "measurements",
            params={
                "session_id": f"eq.{session_row['id']}",
                "select": "type,value,unit",
                "limit": 20,
            },
        )
        for row in response.json():
            measurement_type = row.get("type")
            value = row.get("value")
            if measurement_type == "height":
                measurements["height_cm"] = value
            elif measurement_type == "weight":
                measurements["weight_kg"] = value
            elif measurement_type == "systolic_bp":
                measurements["systolic_bp"] = value
            elif measurement_type == "diastolic_bp":
                measurements["diastolic_bp"] = value
            elif measurement_type == "heart_rate":
                measurements["heart_rate"] = value
            elif measurement_type == "spo2":
                measurements["spo2"] = value
    except SupabaseServiceError:
        measurements = {}

    return {
        "session_pin": session_pin,
        "session_id": session_row["id"],
        "patient_id": session_row.get("patient_id"),
        "current_step": session_row.get("status"),
        "guest_profile": {},
        "measurements": measurements,
        "symptoms": None,
        "assessment": None,
    }


def save_guest_profile(*, session_id, sex: str, age: int) -> dict:
    normalized_session_id = _ensure_session_exists(session_id)
    return sb_insert(
        "guest_profiles",
        {
            "session_id": normalized_session_id,
            "sex": sex,
            "age": age,
        },
    )


def save_measurements(*, session_id, height_cm: float, weight_kg: float, spo2=None) -> list[dict]:
    normalized_session_id = _ensure_session_exists(session_id)
    saved_rows = [
        sb_insert(
            "measurements",
            {
                "session_id": normalized_session_id,
                "type": "height",
                "value": height_cm,
                "unit": "cm",
            },
        ),
        sb_insert(
            "measurements",
            {
                "session_id": normalized_session_id,
                "type": "weight",
                "value": weight_kg,
                "unit": "kg",
            },
        ),
    ]

    if spo2 is not None:
        saved_rows.append(
            sb_insert(
                "measurements",
                {
                    "session_id": normalized_session_id,
                    "type": "spo2",
                    "value": spo2,
                    "unit": "%",
                },
            )
        )

    return saved_rows


def save_blood_pressure(*, session_id, systolic_bp: int, diastolic_bp: int) -> list[dict]:
    normalized_session_id = _ensure_session_exists(session_id)
    saved_rows = [
        sb_insert(
            "measurements",
            {
                "session_id": normalized_session_id,
                "type": "systolic_bp",
                "value": systolic_bp,
                "unit": "mmHg",
            },
        ),
        sb_insert(
            "measurements",
            {
                "session_id": normalized_session_id,
                "type": "diastolic_bp",
                "value": diastolic_bp,
                "unit": "mmHg",
            },
        ),
    ]

    return saved_rows


def save_vitals(*, session_id, heart_rate: int, spo2=None) -> list[dict]:
    normalized_session_id = _ensure_session_exists(session_id)
    saved_rows = [
        sb_insert(
            "measurements",
            {
                "session_id": normalized_session_id,
                "type": "heart_rate",
                "value": heart_rate,
                "unit": "bpm",
            },
        ),
    ]

    if spo2 is not None:
        saved_rows.append(
            sb_insert(
                "measurements",
                {
                    "session_id": normalized_session_id,
                    "type": "spo2",
                    "value": spo2,
                    "unit": "%",
                },
            )
        )

    return saved_rows


def save_symptoms(
    session_id,
    fever,
    cough,
    chest_pain,
    shortness_of_breath,
    dizziness,
    fatigue,
):
    normalized_session_id = _ensure_session_exists(session_id)
    payload = {
        "session_id": normalized_session_id,
        "fever": bool(fever),
        "cough": bool(cough),
        "chest_pain": bool(chest_pain),
        "shortness_of_breath": bool(shortness_of_breath),
        "dizziness": bool(dizziness),
        "fatigue": bool(fatigue),
    }
    return sb_insert("symptoms", payload)


def save_assessment(*, session_id, assessment: dict) -> dict | None:
    normalized_session_id = _ensure_session_exists(session_id)
    bmi = assessment.get("bmi")
    if bmi is None:
        return None

    return sb_insert(
        "derived_metrics",
        {
            "session_id": normalized_session_id,
            "metric": "bmi",
            "value": bmi,
            "interpretation": assessment.get("bmi_label"),
            "rules_version": "v1",
        },
    )
