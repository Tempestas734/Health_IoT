from __future__ import annotations

import json

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .flow import (
    ASSESSMENT_RESULT_KEY,
    CURRENT_STEP_KEY,
    begin_session,
    combined_measurements,
    clear_downstream_step_data,
    first_incomplete_prerequisite,
    get_step_data,
    mark_step_complete,
    result_redirect_path,
)
from .forms import (
    BloodPressureForm,
    ConsentForm,
    GuestForm,
    MeasurementForm,
    SessionActivationForm,
    SymptomForm,
    VitalsForm,
)
from .persistence import get_screening_repository
from .supabase import SupabaseServiceError
from .services.max30102_reader import read_max30102_raw
from .services.receipt_printer import build_receipt_text, print_receipt
from .services.serial_height import read_height_measurement
from .services.session_pin import (
    PIN_SESSION_KEY,
    create_unique_session_pin,
    get_session_snapshot,
    normalize_session_pin,
    publish_session_snapshot,
)
from .use_cases import (
    activate_patient_screening,
    finalize_screening,
    persist_blood_pressure,
    persist_guest_profile,
    persist_measurements,
    persist_vitals,
    start_guest_screening,
)


def _request_data(request) -> dict:
    if "application/json" in (request.content_type or ""):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        data = payload if isinstance(payload, dict) else {}
    else:
        data = request.POST.dict()

    aliases = {
        "sex": {"M": "male", "F": "female"},
        "height": "height_cm",
        "weight": "weight_kg",
        "pulse": "heart_rate",
        "systolic": "systolic_bp",
        "diastolic": "diastolic_bp",
    }
    sex_value = data.get("sex")
    if sex_value in aliases["sex"]:
        data["sex"] = aliases["sex"][sex_value]

    for source_key, target_key in aliases.items():
        if source_key == "sex":
            continue
        if source_key in data and target_key not in data:
            data[target_key] = data[source_key]

    return data


def _expects_json(request) -> bool:
    return request.path.startswith("/api/") or "application/json" in request.headers.get(
        "Accept", ""
    )


def _form_error_response(request, form, template_name, *, status_code=400, context=None):
    if _expects_json(request):
        return JsonResponse({"errors": form.errors.get_json_data()}, status=status_code)
    render_context = {"form": form}
    if context:
        render_context.update(context)
    return render(request, template_name, render_context, status=status_code)


def _redirect_or_json_error(request, path: str, message: str, *, status_code=400):
    if _expects_json(request):
        return JsonResponse({"error": message, "redirect_to": path}, status=status_code)
    return redirect(path)


def _missing_session_response(request):
    return _redirect_or_json_error(
        request,
        "/",
        "Session not found. Please restart from consent.",
        status_code=400,
    )


def _blocked_step_response(request, redirect_path: str):
    return _redirect_or_json_error(
        request,
        redirect_path,
        "Complete the required earlier steps before continuing.",
        status_code=409,
    )


def _service_error_response(request, template_name, message, *, status_code=502, context=None):
    if _expects_json(request):
        return JsonResponse({"error": message}, status=status_code)

    render_context = {"service_error": message}
    if context:
        render_context.update(context)
    return render(request, template_name, render_context, status=status_code)


def _ensure_step_available(request, step_name: str):
    redirect_path = first_incomplete_prerequisite(step_name, request.session)
    if redirect_path == "/":
        return _missing_session_response(request)
    if redirect_path:
        return _blocked_step_response(request, redirect_path)
    return None


def _repository():
    return get_screening_repository()


def _publish_professional_snapshot(session) -> None:
    session_pin = session.get(PIN_SESSION_KEY)
    session_id = session.get("session_id")
    if not session_pin or not session_id:
        return

    snapshot = {
        "session_pin": session_pin,
        "session_id": session_id,
        "current_step": session.get(CURRENT_STEP_KEY),
        "guest_profile": get_step_data(session, "guest"),
        "measurements": combined_measurements(session),
        "symptoms": get_step_data(session, "symptoms"),
        "assessment": session.get(ASSESSMENT_RESULT_KEY),
    }
    publish_session_snapshot(session_pin, snapshot)


def home(request):
    return render(request, "kiosk/home.html")


def session_activation(request):
    form = SessionActivationForm(
        initial={
            "terms_version": "v1",
            "language": "fr",
            "device_id": "DEV-PI-001",
        }
    )
    if request.method != "POST":
        return render(request, "kiosk/session_activation.html", {"form": form})

    form = SessionActivationForm(_request_data(request))
    if not form.is_valid():
        return _form_error_response(request, form, "kiosk/session_activation.html")

    try:
        activated_session = activate_patient_screening(
            _repository(),
            session_pin=form.cleaned_data["session_pin"],
            terms_version=form.cleaned_data["terms_version"],
            language=form.cleaned_data["language"],
            device_id=form.cleaned_data["device_id"],
        )
    except SupabaseServiceError as exc:
        return _service_error_response(
            request,
            "kiosk/session_activation.html",
            str(exc),
            context={"form": form},
        )

    begin_session(request.session, str(activated_session["id"]))
    request.session[PIN_SESSION_KEY] = form.cleaned_data["session_pin"]
    if activated_session.get("patient_id"):
        request.session["patient_id"] = str(activated_session["patient_id"])
    request.session["consent_id"] = str(activated_session["consent_id"])
    request.session["session_mode"] = str(activated_session.get("mode") or "patient")
    _publish_professional_snapshot(request.session)

    if _expects_json(request):
        return JsonResponse(
            {
                "session_id": activated_session["id"],
                "patient_id": activated_session.get("patient_id"),
                "session_pin": request.session[PIN_SESSION_KEY],
                "message": "Patient session activated.",
                "next_path": "/guest",
            },
            status=201,
        )
    return redirect("/guest")


def consent(request):
    form = ConsentForm(
        initial={"terms_version": "v1", "language": "fr", "device_id": "DEV-PI-001"}
    )
    if request.method != "POST":
        return render(request, "kiosk/guest_mode/consent.html", {"form": form})

    form = ConsentForm(_request_data(request))
    if not form.is_valid():
        return _form_error_response(request, form, "kiosk/guest_mode/consent.html")

    try:
        guest_session = start_guest_screening(
            _repository(),
            terms_version=form.cleaned_data["terms_version"],
            language=form.cleaned_data["language"],
            device_id=form.cleaned_data["device_id"],
        )
    except SupabaseServiceError as exc:
        return _service_error_response(request, "kiosk/guest_mode/consent.html", str(exc), context={"form": form})

    begin_session(request.session, str(guest_session["id"]))
    request.session[PIN_SESSION_KEY] = create_unique_session_pin()
    _publish_professional_snapshot(request.session)

    if _expects_json(request):
        return JsonResponse(
            {
                "session_id": guest_session["id"],
                "session_pin": request.session[PIN_SESSION_KEY],
                "professional_url": reverse("professional_lookup"),
            },
            status=201,
        )
    return redirect("/guest")


def guest(request):
    blocked_response = _ensure_step_available(request, "guest")
    if blocked_response:
        return blocked_response

    form = GuestForm(initial=get_step_data(request.session, "guest"))
    if request.method != "POST":
        return render(request, "kiosk/guest_mode/guest.html", {"form": form})

    form = GuestForm(_request_data(request))
    if not form.is_valid():
        return _form_error_response(request, form, "kiosk/guest_mode/guest.html")

    profile = form.cleaned_data
    try:
        persist_guest_profile(
            _repository(),
            session_id=request.session["session_id"],
            profile=profile,
        )
    except SupabaseServiceError as exc:
        return _service_error_response(
            request,
            "kiosk/guest_mode/guest.html",
            str(exc),
            context={"form": form},
        )

    mark_step_complete(request.session, "guest", profile)
    _publish_professional_snapshot(request.session)

    if _expects_json(request):
        return JsonResponse({"status": "ok"}, status=201)
    return redirect("/measure")


def measure(request):
    blocked_response = _ensure_step_available(request, "measure")
    if blocked_response:
        return blocked_response

    form = MeasurementForm(initial=get_step_data(request.session, "measure"))
    if request.method != "POST":
        return render(request, "kiosk/guest_mode/measure.html", {"form": form})

    form = MeasurementForm(_request_data(request))
    if not form.is_valid():
        return _form_error_response(request, form, "kiosk/guest_mode/measure.html")

    measurements = form.cleaned_data
    try:
        persist_measurements(
            _repository(),
            session_id=request.session["session_id"],
            measurements=measurements,
        )
    except SupabaseServiceError as exc:
        return _service_error_response(
            request,
            "kiosk/guest_mode/measure.html",
            str(exc),
            context={"form": form},
        )

    mark_step_complete(request.session, "measure", measurements)
    clear_downstream_step_data(request.session, "measure")
    _publish_professional_snapshot(request.session)

    if _expects_json(request):
        return JsonResponse({"status": "ok"}, status=200)
    return redirect("/blood-pressure")


def blood_pressure(request):
    blocked_response = _ensure_step_available(request, "blood_pressure")
    if blocked_response:
        return blocked_response

    form = BloodPressureForm(initial=get_step_data(request.session, "blood_pressure"))
    if request.method != "POST":
        return render(request, "kiosk/guest_mode/blood_pressure.html", {"form": form})

    form = BloodPressureForm(_request_data(request))
    if not form.is_valid():
        return _form_error_response(request, form, "kiosk/guest_mode/blood_pressure.html")

    blood_pressure_data = form.cleaned_data
    try:
        persist_blood_pressure(
            _repository(),
            session_id=request.session["session_id"],
            blood_pressure=blood_pressure_data,
        )
    except SupabaseServiceError as exc:
        return _service_error_response(
            request,
            "kiosk/guest_mode/blood_pressure.html",
            str(exc),
            context={"form": form},
        )

    mark_step_complete(request.session, "blood_pressure", blood_pressure_data)
    clear_downstream_step_data(request.session, "blood_pressure")
    _publish_professional_snapshot(request.session)

    if _expects_json(request):
        return JsonResponse({"status": "ok"}, status=200)
    return redirect("/vitals")


def vitals(request):
    blocked_response = _ensure_step_available(request, "vitals")
    if blocked_response:
        return blocked_response

    form = VitalsForm(initial=get_step_data(request.session, "vitals"))
    if request.method != "POST":
        return render(request, "kiosk/guest_mode/vitals.html", {"form": form})

    form = VitalsForm(_request_data(request))
    if not form.is_valid():
        return _form_error_response(request, form, "kiosk/guest_mode/vitals.html")

    vitals_data = form.cleaned_data
    try:
        persist_vitals(
            _repository(),
            session_id=request.session["session_id"],
            vitals=vitals_data,
        )
    except SupabaseServiceError as exc:
        return _service_error_response(
            request,
            "kiosk/guest_mode/vitals.html",
            str(exc),
            context={"form": form},
        )

    mark_step_complete(request.session, "vitals", vitals_data)
    clear_downstream_step_data(request.session, "vitals")
    _publish_professional_snapshot(request.session)

    if _expects_json(request):
        return JsonResponse({"status": "ok"}, status=200)
    return redirect("/symptoms")


def symptoms(request):
    blocked_response = _ensure_step_available(request, "symptoms")
    if blocked_response:
        return blocked_response

    initial = {}
    stored_symptoms = get_step_data(request.session, "symptoms")
    if stored_symptoms:
        initial = {key: "yes" if value else "no" for key, value in stored_symptoms.items()}

    form = SymptomForm(initial=initial)
    if request.method != "POST":
        return render(request, "kiosk/guest_mode/symptoms.html", {"form": form})

    form = SymptomForm(_request_data(request))
    if not form.is_valid():
        return _form_error_response(request, form, "kiosk/guest_mode/symptoms.html")

    symptoms_data = form.cleaned_data
    try:
        assessment = finalize_screening(
            _repository(),
            session=request.session,
            symptoms=symptoms_data,
        )
    except SupabaseServiceError as exc:
        return _service_error_response(
            request,
            "kiosk/guest_mode/symptoms.html",
            str(exc),
            context={"form": form},
        )

    mark_step_complete(request.session, "symptoms", symptoms_data)
    request.session[ASSESSMENT_RESULT_KEY] = assessment
    _publish_professional_snapshot(request.session)

    if _expects_json(request):
        return JsonResponse(assessment, status=200)
    return redirect("/result")


def result(request):
    assessment = request.session.get(ASSESSMENT_RESULT_KEY)
    if not assessment:
        return redirect(result_redirect_path(request.session))

    return render(
        request,
        "kiosk/guest_mode/result.html",
        {
            "result": assessment,
            "guest_profile": get_step_data(request.session, "guest"),
            "session_pin": request.session.get(PIN_SESSION_KEY),
        },
    )


def professional_lookup(request):
    requested_pin = normalize_session_pin(
        request.POST.get("session_pin") or request.GET.get("pin")
    )
    snapshot = get_session_snapshot(requested_pin) if requested_pin else None
    if requested_pin and snapshot is None:
        try:
            snapshot = _repository().get_professional_snapshot(session_pin=requested_pin)
        except SupabaseServiceError:
            snapshot = None
    lookup_error = None

    if (request.method == "POST" or request.GET.get("pin")) and not requested_pin:
        lookup_error = "Enter a valid 6-digit session PIN."
    elif requested_pin and snapshot is None:
        lookup_error = "No active session was found for this PIN."

    return render(
        request,
        "kiosk/professional.html",
        {
            "requested_pin": requested_pin or "",
            "lookup_error": lookup_error,
            "snapshot": snapshot,
        },
    )


def professional_result(request, session_pin: str):
    normalized_pin = normalize_session_pin(session_pin)
    snapshot = get_session_snapshot(normalized_pin) if normalized_pin else None
    if normalized_pin and snapshot is None:
        try:
            snapshot = _repository().get_professional_snapshot(session_pin=normalized_pin)
        except SupabaseServiceError:
            snapshot = None
    if not snapshot:
        return redirect(f"{reverse('professional_lookup')}?pin={session_pin}")

    assessment = snapshot.get("assessment")
    if not assessment:
        return redirect(f"{reverse('professional_lookup')}?pin={normalized_pin}")

    return render(
        request,
        "kiosk/guest_mode/result.html",
        {
            "result": assessment,
            "guest_profile": snapshot.get("guest_profile"),
            "session_pin": normalized_pin,
            "professional_view": True,
        },
    )


def height_capture(request):
    return JsonResponse(read_height_measurement(), status=200)


def api_height(request):
    payload = read_height_measurement()
    return JsonResponse(
        {
            "height_mm": payload.get("height_mm"),
            "height_cm": payload.get("height_cm"),
            "distance_mm": payload.get("distance_mm"),
            "status": payload.get("status", "error"),
            "message": payload.get("message", ""),
            "port": payload.get("port", ""),
            "source_line": payload.get("source_line", ""),
        },
        status=200,
    )


def api_vitals_raw(request):
    return JsonResponse(read_max30102_raw(), status=200)


@require_POST
def print_result(request):
    assessment = request.session.get(ASSESSMENT_RESULT_KEY)
    if not assessment:
        return JsonResponse(
            {"ok": False, "error": "No assessment found for this session."},
            status=400,
        )

    guest_profile = get_step_data(request.session, "guest")
    receipt_text = build_receipt_text(assessment, guest_profile)

    try:
        print_receipt(receipt_text)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)

    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def start_session(request):
    return consent(request)


@csrf_exempt
@require_POST
def start_pin_session(request):
    return session_activation(request)


@csrf_exempt
@require_POST
def save_guest_profile(request):
    return guest(request)


@csrf_exempt
@require_POST
def submit_measurements(request):
    return measure(request)


@csrf_exempt
@require_POST
def submit_blood_pressure(request):
    return blood_pressure(request)


@csrf_exempt
@require_POST
def submit_vitals(request):
    return vitals(request)


@csrf_exempt
@require_POST
def submit_symptoms(request):
    return symptoms(request)


kiosk_home = home
kiosk_session_activation = session_activation
kiosk_consent = consent
kiosk_guest = guest
kiosk_measure = measure
kiosk_blood_pressure = blood_pressure
kiosk_vitals = vitals
kiosk_symptoms = symptoms
kiosk_result = result
