from __future__ import annotations

from dataclasses import dataclass


SESSION_ID_KEY = "session_id"
CURRENT_STEP_KEY = "current_step"
ASSESSMENT_RESULT_KEY = "assessment_result"


@dataclass(frozen=True)
class FlowStep:
    name: str
    path: str
    session_key: str | None
    prerequisites: tuple[str, ...] = ()


CONSENT_STEP = FlowStep("consent", "/consent", None)
GUEST_STEP = FlowStep("guest", "/guest", "guest_profile", (SESSION_ID_KEY,))
MEASURE_STEP = FlowStep("measure", "/measure", "measurements", (SESSION_ID_KEY,))
BLOOD_PRESSURE_STEP = FlowStep(
    "blood_pressure",
    "/blood-pressure",
    "blood_pressure",
    (SESSION_ID_KEY, "measurements"),
)
VITALS_STEP = FlowStep(
    "vitals",
    "/vitals",
    "vitals",
    (SESSION_ID_KEY, "measurements", "blood_pressure"),
)
SYMPTOMS_STEP = FlowStep(
    "symptoms",
    "/symptoms",
    "symptoms",
    (SESSION_ID_KEY, "measurements", "blood_pressure", "vitals"),
)
RESULT_STEP = FlowStep(
    "result",
    "/result",
    ASSESSMENT_RESULT_KEY,
    (SESSION_ID_KEY, "measurements", "blood_pressure", "vitals", "symptoms"),
)


FLOW_STEPS = (
    CONSENT_STEP,
    GUEST_STEP,
    MEASURE_STEP,
    BLOOD_PRESSURE_STEP,
    VITALS_STEP,
    SYMPTOMS_STEP,
    RESULT_STEP,
)
FLOW_STEPS_BY_NAME = {step.name: step for step in FLOW_STEPS}

STEP_DATA_KEYS = tuple(
    step.session_key for step in FLOW_STEPS if step.session_key is not None
)


def begin_session(session, session_id: str) -> None:
    session[SESSION_ID_KEY] = session_id
    session[CURRENT_STEP_KEY] = GUEST_STEP.name
    clear_step_data(session)


def clear_step_data(session) -> None:
    for key in STEP_DATA_KEYS:
        session.pop(key, None)


def clear_downstream_step_data(session, step_name: str) -> None:
    seen_target = False
    for step in FLOW_STEPS:
        if step.name == step_name:
            seen_target = True
            continue
        if seen_target and step.session_key is not None:
            session.pop(step.session_key, None)


def mark_step_complete(session, step_name: str, data) -> None:
    step = FLOW_STEPS_BY_NAME[step_name]
    if step.session_key is not None:
        session[step.session_key] = data

    step_index = FLOW_STEPS.index(step)
    next_index = min(step_index + 1, len(FLOW_STEPS) - 1)
    session[CURRENT_STEP_KEY] = FLOW_STEPS[next_index].name


def get_step_data(session, step_name: str, default=None):
    session_key = FLOW_STEPS_BY_NAME[step_name].session_key
    if session_key is None:
        return default
    return session.get(session_key, default)


def first_incomplete_prerequisite(step_name: str, session) -> str | None:
    step = FLOW_STEPS_BY_NAME[step_name]
    for required_key in step.prerequisites:
        if not session.get(required_key):
            if required_key == SESSION_ID_KEY:
                return "/"
            return path_for_session_key(required_key)
    return None


def result_redirect_path(session) -> str:
    if session.get(ASSESSMENT_RESULT_KEY):
        return RESULT_STEP.path

    for required_key in RESULT_STEP.prerequisites[1:]:
        if not session.get(required_key):
            return path_for_session_key(required_key)
    return SYMPTOMS_STEP.path


def path_for_session_key(session_key: str) -> str:
    for step in FLOW_STEPS:
        if step.session_key == session_key:
            return step.path
    return CONSENT_STEP.path


def combined_measurements(session) -> dict:
    measurements: dict = {}
    for step_name in ("measure", "blood_pressure", "vitals"):
        measurements.update(get_step_data(session, step_name, {}) or {})
    return measurements
