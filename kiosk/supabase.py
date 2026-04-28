import os

import requests


class SupabaseServiceError(RuntimeError):
    """Raised when a Supabase data-access operation fails."""


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


def create_guest_session(*, terms_version: str, language: str, device_id: str) -> dict:
    consent = sb_insert(
        "consents",
        {
            "terms_version": terms_version,
            "language": language,
        },
    )
    return sb_insert(
        "exam_sessions",
        {
            "device_id": device_id,
            "consent_id": consent["id"],
            "status": "active",
        },
    )


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
