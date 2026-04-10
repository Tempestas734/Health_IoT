from __future__ import annotations

from .flow import combined_measurements
from .services.final_assessment import build_screening_assessment


def start_guest_screening(repository, *, terms_version: str, language: str, device_id: str) -> dict:
    return repository.create_guest_session(
        terms_version=terms_version,
        language=language,
        device_id=device_id,
    )


def persist_guest_profile(repository, *, session_id: str, profile: dict) -> None:
    repository.save_guest_profile(session_id=session_id, **profile)


def persist_measurements(repository, *, session_id: str, measurements: dict) -> None:
    repository.save_measurements(session_id=session_id, **measurements)


def persist_blood_pressure(repository, *, session_id: str, blood_pressure: dict) -> None:
    repository.save_blood_pressure(session_id=session_id, **blood_pressure)


def persist_vitals(repository, *, session_id: str, vitals: dict) -> None:
    repository.save_vitals(session_id=session_id, **vitals)


def finalize_screening(repository, *, session, symptoms: dict) -> dict:
    session_id = session["session_id"]
    repository.save_symptoms(session_id=session_id, **symptoms)

    assessment = build_screening_assessment(
        profile=session.get("guest_profile", {}),
        measurements=combined_measurements(session),
        symptoms=symptoms,
    )
    repository.save_assessment(session_id=session_id, assessment=assessment)
    return assessment
