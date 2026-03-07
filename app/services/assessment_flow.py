from __future__ import annotations

from typing import Any, Optional


FLOW_STEPS_V2: list[tuple[str, str]] = [
    ("basic_info", "Basic info"),
    ("risk_factors", "Risk factors"),
    ("symptoms", "Symptoms"),
    ("labs", "Labs"),
    ("results", "Results"),
]

_BASIC_INFO_VIEW_STATES = {"start", "patient_intro", "patient_sex", "patient_age"}
_BASIC_INFO_CODES = {
    "age",
    "age_years",
    "patient_age",
    "sex_at_birth",
    "birth_sex",
    "survey_for",
    "respondent",
    "survey_target",
    "pregnant",
}

_RISK_CODES = {
    "overweight",
    "inactive",
    "family_history",
    "high_bp",
    "bp_history",
    "prediabetes_history",
    "gestational_diabetes",
    "gestational_diabetes_history",
    "bmi_known",
    "bmi_value",
    "height_cm",
    "weight_kg",
}

_LAB_CODES = {
    "has_labs",
    "has_lab",
    "fpg",
    "fbs",
    "hba1c",
    "random_glucose",
    "ogtt75_fast",
    "ogtt75_1h",
    "ogtt75_2h",
}


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _question_flow_key(symptom: Optional[Any]) -> str:
    if not symptom:
        return "symptoms"

    code = _normalize(getattr(symptom, "code", ""))
    category = _normalize(getattr(symptom, "category", ""))
    section = _normalize(getattr(symptom, "ui_section", ""))

    if category == "info" or code in _BASIC_INFO_CODES:
        return "basic_info"

    if (
        code in _LAB_CODES
        or category in {"lab", "labs", "laboratory", "gate", "has_lab", "hab_lab"}
        or section in {"lab", "labs", "laboratory"}
        or any(token in code for token in ("fbs", "fpg", "hba1c", "ogtt", "glucose"))
    ):
        return "labs"

    if (
        code in _RISK_CODES
        or category == "risk"
        or section == "risk"
    ):
        return "risk_factors"

    return "symptoms"


def flow_key_for_view(view_state: str, symptom: Optional[Any] = None) -> str:
    state = _normalize(view_state)
    if state in _BASIC_INFO_VIEW_STATES:
        return "basic_info"
    if state == "results":
        return "results"
    if state == "checklist_batch":
        return "symptoms"
    if state == "confirm_finish":
        return "labs"
    if state == "question":
        return _question_flow_key(symptom)
    return "symptoms"


def build_assessment_steps(view_state: str, symptom: Optional[Any] = None) -> list[dict[str, Any]]:
    current_key = flow_key_for_view(view_state, symptom=symptom)
    current_index = 0
    for idx, (key, _label) in enumerate(FLOW_STEPS_V2):
        if key == current_key:
            current_index = idx
            break

    steps: list[dict[str, Any]] = []
    for idx, (key, label) in enumerate(FLOW_STEPS_V2):
        steps.append(
            {
                "key": key,
                "label": label,
                "is_current": idx == current_index,
                "is_done": idx < current_index,
            }
        )
    return steps
