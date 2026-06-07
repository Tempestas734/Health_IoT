from django.urls import path
from . import views

urlpatterns = [
    # UI pages
    path("", views.kiosk_home, name="home"),
    path("session-activation", views.kiosk_session_activation, name="session_activation"),
    path("consent", views.kiosk_consent, name="consent"),
    path("guest", views.kiosk_guest, name="guest"),
    path("measure", views.kiosk_measure, name="measure"),
    path("blood-pressure", views.kiosk_blood_pressure, name="blood_pressure"),
    path("vitals", views.kiosk_vitals, name="vitals"),
    path("symptoms", views.kiosk_symptoms, name="symptoms"),
    path("result", views.kiosk_result, name="result"),
    path("result/print", views.print_result, name="print_result"),
    path("professional", views.professional_lookup, name="professional_lookup"),
    path("professional/<str:session_pin>", views.professional_result, name="professional_result"),

    # API
    path("api/session-activation/start-session", views.start_pin_session, name="api_start_pin_session"),
    path("api/consent/start-session", views.start_session, name="api_start_session"),
    path("api/guest/profile", views.save_guest_profile, name="api_save_guest_profile"),
    path("api/measurements/height", views.height_capture, name="api_height_capture"),
    path("api/height/", views.api_height, name="api_height"),
    path("api/measurements/submit", views.submit_measurements, name="api_submit_measurements"),
    path("api/blood-pressure/submit", views.submit_blood_pressure, name="api_submit_blood_pressure"),
    path("api/vitals/submit", views.submit_vitals, name="api_submit_vitals"),
    path("api/vitals/raw/", views.api_vitals_raw, name="api_vitals_raw"),
    path("api/symptoms/submit", views.submit_symptoms, name="api_submit_symptoms"),
]
