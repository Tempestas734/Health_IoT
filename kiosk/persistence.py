from __future__ import annotations

from typing import Protocol

from . import supabase


class ScreeningRepository(Protocol):
    def create_guest_session(self, *, terms_version: str, language: str, device_id: str) -> dict: ...
    def save_guest_profile(self, *, session_id: str, sex: str, age: int) -> dict: ...
    def save_measurements(self, *, session_id: str, height_cm: float, weight_kg: float, spo2=None) -> list[dict]: ...
    def save_blood_pressure(self, *, session_id: str, systolic_bp: int, diastolic_bp: int) -> list[dict]: ...
    def save_vitals(self, *, session_id: str, heart_rate: int, spo2=None) -> list[dict]: ...
    def save_symptoms(
        self,
        *,
        session_id: str,
        fever: bool,
        cough: bool,
        chest_pain: bool,
        shortness_of_breath: bool,
        dizziness: bool,
        fatigue: bool,
    ) -> dict: ...
    def save_assessment(self, *, session_id: str, assessment: dict) -> dict | None: ...


class SupabaseScreeningRepository:
    def create_guest_session(self, *, terms_version: str, language: str, device_id: str) -> dict:
        return supabase.create_guest_session(
            terms_version=terms_version,
            language=language,
            device_id=device_id,
        )

    def save_guest_profile(self, *, session_id: str, sex: str, age: int) -> dict:
        return supabase.save_guest_profile(session_id=session_id, sex=sex, age=age)

    def save_measurements(self, *, session_id: str, height_cm: float, weight_kg: float, spo2=None) -> list[dict]:
        return supabase.save_measurements(
            session_id=session_id,
            height_cm=height_cm,
            weight_kg=weight_kg,
            spo2=spo2,
        )

    def save_blood_pressure(self, *, session_id: str, systolic_bp: int, diastolic_bp: int) -> list[dict]:
        return supabase.save_blood_pressure(
            session_id=session_id,
            systolic_bp=systolic_bp,
            diastolic_bp=diastolic_bp,
        )

    def save_vitals(self, *, session_id: str, heart_rate: int, spo2=None) -> list[dict]:
        return supabase.save_vitals(
            session_id=session_id,
            heart_rate=heart_rate,
            spo2=spo2,
        )

    def save_symptoms(
        self,
        *,
        session_id: str,
        fever: bool,
        cough: bool,
        chest_pain: bool,
        shortness_of_breath: bool,
        dizziness: bool,
        fatigue: bool,
    ) -> dict:
        return supabase.save_symptoms(
            session_id=session_id,
            fever=fever,
            cough=cough,
            chest_pain=chest_pain,
            shortness_of_breath=shortness_of_breath,
            dizziness=dizziness,
            fatigue=fatigue,
        )

    def save_assessment(self, *, session_id: str, assessment: dict) -> dict | None:
        return supabase.save_assessment(session_id=session_id, assessment=assessment)


def get_screening_repository() -> ScreeningRepository:
    return SupabaseScreeningRepository()
