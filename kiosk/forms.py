from django import forms


YES_NO_CHOICES = (
    ("yes", "Yes"),
    ("no", "No"),
)


def _coerce_yes_no(value):
    if value in (True, False):
        return value
    if value in (None, ""):
        raise forms.ValidationError("This field is required.")

    normalized = str(value).strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    raise forms.ValidationError("Please choose Yes or No.")


class ConsentForm(forms.Form):
    agree = forms.BooleanField(required=False)
    terms_version = forms.CharField(required=False, max_length=20, initial="v1")
    language = forms.CharField(required=False, max_length=10, initial="fr")
    device_id = forms.CharField(required=False, max_length=100, initial="UNKNOWN")

    def clean_terms_version(self) -> str:
        value = (self.cleaned_data.get("terms_version") or "v1").strip()
        return value or "v1"

    def clean_language(self) -> str:
        value = (self.cleaned_data.get("language") or "fr").strip().lower()
        return value or "fr"

    def clean_device_id(self) -> str:
        value = (self.cleaned_data.get("device_id") or "UNKNOWN").strip()
        return value or "UNKNOWN"

    def clean(self):
        cleaned_data = super().clean()
        if "agree" not in self.data and self.is_bound:
            cleaned_data["agree"] = True
        elif not cleaned_data.get("agree"):
            self.add_error("agree", "You must accept the consent terms to continue.")
        return cleaned_data


class GuestForm(forms.Form):
    SEX_CHOICES = (
        ("male", "Male"),
        ("female", "Female"),
    )

    sex = forms.ChoiceField(
        choices=SEX_CHOICES,
        error_messages={
            "required": "Please select a biological sex.",
            "invalid_choice": "Please choose either male or female.",
        },
    )
    age = forms.IntegerField(
        min_value=1,
        max_value=120,
        error_messages={
            "required": "Please enter the guest age.",
            "invalid": "Age must be a whole number.",
            "min_value": "Age must be at least 1 year.",
            "max_value": "Age must be 120 years or less.",
        },
    )

    def clean_sex(self) -> str:
        return self.cleaned_data["sex"].strip().lower()

    def clean_age(self) -> int:
        return int(self.cleaned_data["age"])


class MeasurementForm(forms.Form):
    height_cm = forms.FloatField(
        min_value=50,
        max_value=250,
        error_messages={
            "required": "Please enter height in centimeters.",
            "invalid": "Height must be a valid number.",
            "min_value": "Height must be at least 50 cm.",
            "max_value": "Height must be 250 cm or less.",
        },
    )
    weight_kg = forms.FloatField(
        min_value=10,
        max_value=300,
        error_messages={
            "required": "Please enter weight in kilograms.",
            "invalid": "Weight must be a valid number.",
            "min_value": "Weight must be at least 10 kg.",
            "max_value": "Weight must be 300 kg or less.",
        },
    )

    def clean_height_cm(self) -> float:
        return round(float(self.cleaned_data["height_cm"]), 1)

    def clean_weight_kg(self) -> float:
        return round(float(self.cleaned_data["weight_kg"]), 1)


class BloodPressureForm(forms.Form):
    systolic_bp = forms.IntegerField(
        min_value=60,
        max_value=250,
        error_messages={
            "required": "Please enter systolic blood pressure.",
            "invalid": "Systolic pressure must be a whole number.",
            "min_value": "Systolic pressure must be at least 60 mmHg.",
            "max_value": "Systolic pressure must be 250 mmHg or less.",
        },
    )
    diastolic_bp = forms.IntegerField(
        min_value=40,
        max_value=150,
        error_messages={
            "required": "Please enter diastolic blood pressure.",
            "invalid": "Diastolic pressure must be a whole number.",
            "min_value": "Diastolic pressure must be at least 40 mmHg.",
            "max_value": "Diastolic pressure must be 150 mmHg or less.",
        },
    )

    def clean_systolic_bp(self) -> int:
        return int(self.cleaned_data["systolic_bp"])

    def clean_diastolic_bp(self) -> int:
        return int(self.cleaned_data["diastolic_bp"])


class VitalsForm(forms.Form):
    heart_rate = forms.IntegerField(
        min_value=30,
        max_value=220,
        error_messages={
            "required": "Please enter heart rate in beats per minute.",
            "invalid": "Heart rate must be a whole number.",
            "min_value": "Heart rate must be at least 30 bpm.",
            "max_value": "Heart rate must be 220 bpm or less.",
        },
    )
    spo2 = forms.IntegerField(
        required=False,
        min_value=50,
        max_value=100,
        error_messages={
            "invalid": "SpO2 must be a whole number.",
            "min_value": "SpO2 must be at least 50%.",
            "max_value": "SpO2 must be 100% or less.",
        },
    )

    def clean_heart_rate(self) -> int:
        return int(self.cleaned_data["heart_rate"])

    def clean_spo2(self) -> int | None:
        value = self.cleaned_data.get("spo2")
        return None if value in (None, "") else int(value)


class SymptomForm(forms.Form):
    fever = forms.TypedChoiceField(
        label="Fever",
        choices=YES_NO_CHOICES,
        coerce=_coerce_yes_no,
        error_messages={"required": "Please select Yes or No for fever."},
    )
    cough = forms.TypedChoiceField(
        label="Cough",
        choices=YES_NO_CHOICES,
        coerce=_coerce_yes_no,
        error_messages={"required": "Please select Yes or No for cough."},
    )
    chest_pain = forms.TypedChoiceField(
        label="Chest pain",
        choices=YES_NO_CHOICES,
        coerce=_coerce_yes_no,
        error_messages={"required": "Please select Yes or No for chest pain."},
    )
    shortness_of_breath = forms.TypedChoiceField(
        label="Shortness of breath",
        choices=YES_NO_CHOICES,
        coerce=_coerce_yes_no,
        error_messages={
            "required": "Please select Yes or No for shortness of breath.",
        },
    )
    dizziness = forms.TypedChoiceField(
        label="Dizziness",
        choices=YES_NO_CHOICES,
        coerce=_coerce_yes_no,
        error_messages={"required": "Please select Yes or No for dizziness."},
    )
    fatigue = forms.TypedChoiceField(
        label="Fatigue",
        choices=YES_NO_CHOICES,
        coerce=_coerce_yes_no,
        error_messages={"required": "Please select Yes or No for fatigue."},
    )
