from typing import Any, Optional
from datetime import datetime

from io import BytesIO

from flask import abort, render_template, request, send_file, session, redirect, url_for
from app.extensions import db
from sqlalchemy.orm import selectinload

from app.models import (
    Assessment,
    CaseFact,
    DiagnosisRun,
    Rule,
    Symptom,
    User,
)
from app.inference.facts import facts_for_assessment
from app.services.assessment_flow import build_assessment_steps
from app.services.assessment_service import get_inference_snapshot, run_diagnosis_now
from app.services.report_builder import build_report
from app.services.report_pdf import build_report_pdf

from . import web_bp
from .utils import require_login, require_permissions, current_permissions, current_roles


def _current_user_id():
    me = session.get("me") or {}
    uid = me.get("user_id")
    return int(uid) if uid is not None else None


def _patient_profile_from_user(user: Optional[User]) -> dict[str, Any]:
    survey_for = ((getattr(user, "survey_for", None) or "myself").strip().lower() if user else "myself")
    if survey_for == "someone":
        survey_for = "someone_else"
    if survey_for not in {"myself", "someone_else"}:
        survey_for = "myself"

    sex_at_birth = ((getattr(user, "sex_at_birth", None) or "").strip().lower() if user else "")
    if sex_at_birth not in {"female", "male", "intersex", "prefer_not"}:
        sex_at_birth = ""

    age_years = getattr(user, "age_years", None) if user else None
    try:
        age_years = int(age_years) if age_years is not None else None
    except (TypeError, ValueError):
        age_years = None

    return {
        "survey_for": survey_for,
        "sex_at_birth": sex_at_birth,
        "age_years": age_years,
    }


def _normalize_key(value: Optional[str]) -> str:
    return (value or "").strip().lower().replace("-", "_")


def _is_classic_checklist_symptom(symptom: Symptom) -> bool:
    if not symptom or symptom.parent_symptom_id:
        return False
    if (symptom.input_type or "").upper() != "BOOLEAN":
        return False
    category = _normalize_key(symptom.category)
    return category == "classic"


def _classic_checklist_symptoms() -> list[Symptom]:
    return [s for s in _ordered_symptoms() if _is_classic_checklist_symptom(s)]


def _is_patient_info_symptom(symptom: Symptom) -> bool:
    if not symptom:
        return False
    return _normalize_key(symptom.category) == "info"


def _profile_value_for_info_symptom(symptom: Symptom, profile: dict[str, Any]) -> Any:
    code = _normalize_key(symptom.code)
    if code in {"age_years", "age", "patient_age"}:
        return profile.get("age_years")
    if code in {"sex_at_birth", "birth_sex", "sex_birth"}:
        return profile.get("sex_at_birth")
    if code in {"survey_for", "respondent", "survey_target"}:
        return profile.get("survey_for")
    return None


def _sync_patient_info_symptom_facts(assessment_id: int, patient_profile: dict[str, Any]):
    info_symptoms = [
        symptom
        for symptom in _ordered_symptoms()
        if _is_patient_info_symptom(symptom)
    ]
    changed = False
    for symptom in info_symptoms:
        profile_value = _profile_value_for_info_symptom(symptom, patient_profile)
        if profile_value in (None, ""):
            continue
        _upsert_fact(assessment_id, symptom.id, profile_value, input_type=symptom.input_type)
        changed = True
    if changed:
        db.session.commit()


def _next_patient_info_symptom(assessment_id: int) -> Optional[Symptom]:
    facts = facts_for_assessment(assessment_id)
    answered_ids = {
        row.symptom_id
        for row in CaseFact.query.filter_by(assessment_id=assessment_id).all()
        if row.symptom_id
    }
    all_symptoms = _ordered_symptoms()
    symptom_map = {symptom.id: symptom for symptom in all_symptoms}
    info_symptoms = [symptom for symptom in all_symptoms if _is_patient_info_symptom(symptom)]

    for symptom in info_symptoms:
        if symptom.id in answered_ids:
            continue
        if not _trigger_ready(symptom, facts, symptom_map):
            continue
        return symptom
    return None


def _greeting_for_hour(hour: int) -> str:
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def _shift_for_hour(hour: int) -> str:
    if 8 <= hour < 13:
        return "Morning shift (08:00 - 13:00)"
    if 13 <= hour < 18:
        return "Afternoon shift (13:00 - 18:00)"
    return "Night shift (18:00 - 08:00)"


def _clinical_cycle_for_date(value: datetime) -> str:
    start_year = value.year if value.month >= 7 else value.year - 1
    return f"Clinical Cycle {start_year}-{start_year + 1}"


def _phase_for_date(value: datetime) -> str:
    quarter = ((value.month - 1) // 3) + 1
    return f"Phase: Q{quarter} Review"


def _role_label(roles: set, fallback: str = "USER") -> str:
    role = fallback
    if "ADMIN" in roles:
        role = "ADMIN"
    elif "KB_DOCTOR" in roles:
        role = "KB_DOCTOR"
    elif roles:
        role = sorted(roles)[0]
    return role.replace("_", " ").title()


def _get_or_create_assessment(user_id: int) -> Assessment:
    active = Assessment.query.filter_by(user_id=user_id, status="IN_PROGRESS").first()
    if active:
        return active
    assessment = Assessment(user_id=user_id, patient_id=user_id, status="IN_PROGRESS")
    db.session.add(assessment)
    db.session.commit()
    return assessment


def _upsert_fact(assessment_id: int, symptom_id: int, value: Any, input_type: Optional[str] = None):
    symptom = Symptom.query.get(symptom_id)
    if not symptom:
        return
    input_type = (input_type or symptom.input_type or "BOOLEAN").upper()

    value_bool = None
    value_number = None
    value_text = None
    if input_type == "BOOLEAN":
        value_bool = None if value is None else bool(value)
    elif input_type == "NUMBER":
        value_number = float(value) if value not in (None, "") else None
    elif input_type in {"TEXT", "SINGLE"}:
        value_text = str(value).strip() if value is not None else None
    else:
        value_bool = bool(value)
        input_type = "BOOLEAN"

    existing = CaseFact.query.filter_by(
        assessment_id=assessment_id,
        symptom_id=symptom_id,
    ).first()
    if existing:
        existing.value_bool = value_bool
        existing.value_number = value_number
        existing.value_text = value_text
    else:
        db.session.add(CaseFact(
            assessment_id=assessment_id,
            symptom_id=symptom_id,
            value_bool=value_bool,
            value_number=value_number,
            value_text=value_text,
        ))


def _parse_bool_value(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"unknown", "dont_know", "don't_know", "dk", "not_sure"}:
            return None
        if lowered in {"1", "true", "yes", "y"}:
            return True
        if lowered in {"0", "false", "no", "n"}:
            return False
    return None


def _match_trigger(operator: Optional[str], expected: Optional[str], actual: Any) -> bool:
    operator = (operator or "==").upper()
    if actual is None:
        if operator == "ABSENT":
            return True
        return False

    if isinstance(expected, str) and expected.lower() in {"true", "false"}:
        expected = "1" if expected.lower() == "true" else "0"

    if isinstance(expected, str) and expected.strip() in {"1", "0"}:
        expected_val = expected.strip() == "1"
    else:
        expected_val = expected

    if operator == "PRESENT":
        if isinstance(actual, bool):
            return actual is True
        return True
    if operator == "ABSENT":
        if isinstance(actual, bool):
            return actual is False
        return False
    if operator == "==":
        return actual == expected_val
    if operator == "!=":
        return actual != expected_val

    try:
        actual_num = float(actual)
        expected_num = float(expected_val)
    except (TypeError, ValueError):
        return False

    if operator == ">":
        return actual_num > expected_num
    if operator == ">=":
        return actual_num >= expected_num
    if operator == "<":
        return actual_num < expected_num
    if operator == "<=":
        return actual_num <= expected_num
    return False


def _ordered_symptoms() -> list:
    symptoms = Symptom.query.filter_by(is_active=True).all()

    def _section_rank(name: Optional[str]) -> tuple:
        key = (name or "").strip().lower()
        if key in {"symptoms", "symptom"}:
            return (0, name or "")
        if key in {"labs", "lab", "laboratory"}:
            return (1, name or "")
        return (2, name or "")

    return sorted(
        symptoms,
        key=lambda s: (
            _section_rank(s.category),
            s.priority_order or 0,
            s.id,
        ),
    )


def _trigger_ready(symptom: Symptom, facts: dict, symptom_map: dict) -> bool:
    if not symptom.parent_symptom_id:
        return True
    parent = symptom_map.get(symptom.parent_symptom_id)
    if not parent or not parent.code:
        return False
    if parent.code not in facts:
        return False
    actual = facts.get(parent.code)
    return _match_trigger(symptom.show_if_operator, symptom.show_if_value, actual)


def _question_style(symptom: Symptom) -> str:
    category = _normalize_key(symptom.category)
    code = _normalize_key(symptom.code)
    if category in {"lab", "labs", "laboratory", "has_lab", "hab_lab", "gate"}:
        return "lab"
    if code in {"has_labs", "has_lab"}:
        return "lab"
    if symptom.parent_symptom_id:
        return "detail"
    if category == "classic":
        return "checklist"
    return "checklist"


def _trigger_text(symptom: Symptom) -> str:
    if not symptom.parent_symptom_id:
        return ""
    parent = Symptom.query.get(symptom.parent_symptom_id)
    if not parent:
        return ""
    parent_label = parent.name or parent.question_text or parent.code
    op = (symptom.show_if_operator or "==").upper()
    if op in {"PRESENT", "ABSENT"}:
        return f"Shown when {parent_label} is {op.lower()}."
    expected = symptom.show_if_value
    if expected in (None, ""):
        return f"Follow-up for {parent_label}."
    return f"Shown when {parent_label} {op} {expected}."


def _next_symptom(assessment_id: int, last_answered_id: Optional[int]) -> Optional[Symptom]:
    """Return the next question in the expert-system interview.

    Behavior (matches your workflow):
    - Ask one question at a time.
    - Start with root symptoms (parent_symptom_id IS NULL).
    - When a parent is answered, ask its children next.
    - When a child is answered, ask:
        1) its own children (grandchildren), then
        2) its siblings under the same parent,
      so a whole "child bundle" (Onset / Night urination / Thirst / ...) completes naturally.
    - After the bundle is done, continue with the next root symptom.
    """
    facts = facts_for_assessment(assessment_id)

    answered_ids = {
        row.symptom_id
        for row in CaseFact.query.filter_by(assessment_id=assessment_id).all()
        if row.symptom_id
    }

    all_symptoms = _ordered_symptoms()
    symptoms = [symptom for symptom in all_symptoms if not _is_patient_info_symptom(symptom)]
    symptom_map = {s.id: s for s in all_symptoms}

    # Children grouped by parent (ordering preserved from _ordered_symptoms()).
    by_parent: dict[int, list[Symptom]] = {}
    for s in symptoms:
        if s.parent_symptom_id:
            by_parent.setdefault(s.parent_symptom_id, []).append(s)

    def _pick(candidates: list[Symptom]) -> Optional[Symptom]:
        for s in candidates:
            if s.id in answered_ids:
                continue
            if not _trigger_ready(s, facts, symptom_map):
                continue
            return s
        return None

    def _pick_pending_children() -> Optional[Symptom]:
        for parent_id in sorted(by_parent.keys()):
            if parent_id not in answered_ids:
                continue
            child = _pick(by_parent.get(parent_id, []))
            if child:
                return child
        return None

    if last_answered_id:
        # 1) Ask direct children of the last answered symptom first.
        child = _pick(by_parent.get(last_answered_id, []))
        if child:
            return child

        # 2) If last answered is itself a child, continue with its siblings
        # under the same parent (complete the bundle).
        last_symptom = symptom_map.get(last_answered_id)
        if last_symptom and last_symptom.parent_symptom_id:
            sibling = _pick(by_parent.get(last_symptom.parent_symptom_id, []))
            if sibling:
                return sibling

    # 3) Ask any remaining children of already-answered parents.
    pending_child = _pick_pending_children()
    if pending_child:
        return pending_child

    # 4) Otherwise, ask the next root symptom.
    root_symptoms = [s for s in symptoms if not s.parent_symptom_id]
    return _pick(root_symptoms)


def _format_value(symptom: Symptom, fact: CaseFact) -> str:
    input_type = (symptom.input_type or "BOOLEAN").upper()
    if input_type == "BOOLEAN":
        if fact.value_bool is None:
            return "Don't know"
        return "Yes" if fact.value_bool else "No"
    if input_type == "NUMBER":
        if fact.value_number is None:
            return "Not provided"
        base = f"{fact.value_number}".rstrip("0").rstrip(".")
        return f"{base} {symptom.unit}".strip() if symptom.unit else base
    if input_type in {"TEXT", "SINGLE"}:
        return fact.value_text or "Not provided"
    return "Not provided"


def _answers_summary(assessment_id: int) -> list:
    rows = CaseFact.query.filter_by(assessment_id=assessment_id).all()
    symptom_ids = [row.symptom_id for row in rows if row.symptom_id]
    symptoms = Symptom.query.filter(Symptom.id.in_(symptom_ids)).all() if symptom_ids else []
    fact_map = {row.symptom_id: row for row in rows}
    code_map = {s.code: s for s in symptoms}

    grouped: dict[str, list[dict]] = {}
    section_order: list[str] = []

    for symptom in _ordered_symptoms():
        if symptom.id not in fact_map:
            continue
        row = fact_map[symptom.id]
        section = (symptom.category or "General").strip() or "General"
        if section not in grouped:
            grouped[section] = []
            section_order.append(section)
        grouped[section].append({
            "label": symptom.name or symptom.question_text or symptom.code,
            "value": _format_value(symptom, row),
        })

    # Derived BMI display if height + weight are present
    height_symptom = code_map.get("height_cm")
    weight_symptom = code_map.get("weight_kg")
    height_row = fact_map.get(height_symptom.id) if height_symptom else None
    weight_row = fact_map.get(weight_symptom.id) if weight_symptom else None
    if height_row and weight_row and height_row.value_number and weight_row.value_number:
        try:
            height_m = float(height_row.value_number) / 100.0
            weight_kg = float(weight_row.value_number)
            if height_m > 0:
                bmi = weight_kg / (height_m ** 2)
                section = (height_symptom.category or "Risk").strip() or "Risk"
                if section not in grouped:
                    grouped[section] = []
                    section_order.append(section)
                grouped[section].append({
                    "label": "BMI (kg/m²)",
                    "value": f"{bmi:.1f}",
                })
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    lab_categories = {"lab", "labs", "laboratory", "has_lab", "hab_lab", "gate"}
    has_labs_defined = any(
        _normalize_key(symptom.category) in lab_categories
        for symptom in Symptom.query.filter(Symptom.is_active.is_(True)).all()
    )
    if has_labs_defined and "Labs" not in grouped:
        grouped["Labs"] = [{"label": "Labs", "value": "Not provided"}]
        section_order.append("Labs")

    return [{"section": section, "items": grouped[section]} for section in section_order]


def _condition_labels(items: list, symptom_map: dict) -> list[str]:
    labels = []
    for item in items:
        sid = item.get("symptom_id")
        symptom = symptom_map.get(sid)
        if symptom:
            labels.append(symptom.name or symptom.question_text or symptom.code)
        else:
            labels.append(item.get("symptom_code") or f"Symptom {sid}")
    return labels


def _rule_summary(report: Optional[dict]) -> dict:
    if not report:
        return {}
    trace = report.get("explanation_trace") or {}
    fired_rule_id = trace.get("fired_rule_id")
    fired_rule_code = trace.get("fired_rule_code")
    matched_items = []
    if trace.get("rules_fired"):
        matched_items = trace["rules_fired"][0].get("matched") or []
    elif trace.get("matched_conditions"):
        matched_items = trace.get("matched_conditions") or []

    missing_items = []
    if fired_rule_id and trace.get("rules_evaluated"):
        for row in trace["rules_evaluated"]:
            if row.get("rule_id") == fired_rule_id:
                missing_items = row.get("missing_conditions") or []
                break

    symptom_ids = set()
    for item in matched_items + missing_items:
        sid = item.get("symptom_id")
        if sid:
            symptom_ids.add(sid)
    symptom_map = {}
    if symptom_ids:
        symptom_map = {s.id: s for s in Symptom.query.filter(Symptom.id.in_(symptom_ids)).all()}

    rule_title = fired_rule_code
    rule_type = "screening"
    if fired_rule_id:
        rule = Rule.query.get(fired_rule_id)
        if rule:
            rule_title = rule.title or rule.rule_code
            rule_type = (rule.rule_type or "screening").lower()

    return {
        "rule_id": fired_rule_id,
        "rule_type": rule_type,
        "rule_title": rule_title,
        "matched": _condition_labels(matched_items, symptom_map),
        "missing": _condition_labels(missing_items, symptom_map),
    }


def _assessment_data_gaps(assessment_id: int, rule_summary: Optional[dict]) -> tuple[list[str], list[str]]:
    missing_data = list((rule_summary or {}).get("missing") or [])
    rule_type = str((rule_summary or {}).get("rule_type") or "screening").strip().lower()
    recommended_tests: list[str] = []

    facts = facts_for_assessment(assessment_id)
    parent = Symptom.query.filter_by(code="has_labs").first()
    missing_labs: list[str] = []
    if parent:
        lab_children = (
            Symptom.query
            .filter_by(parent_symptom_id=parent.id, is_active=True)
            .order_by(Symptom.priority_order.asc(), Symptom.id.asc())
            .all()
        )
        for lab in lab_children:
            if lab.code not in facts:
                label = lab.name or lab.question_text or lab.code
                if label and label not in missing_labs:
                    missing_labs.append(label)

    if rule_type == "screening":
        recommended_tests = list(missing_labs)
        screening_optional_labels = {item.strip().lower() for item in recommended_tests if item}
        if parent:
            screening_optional_labels.update(
                {
                    (parent.name or "").strip().lower(),
                    (parent.question_text or "").strip().lower(),
                    (parent.code or "").strip().lower(),
                }
            )
        if screening_optional_labels:
            missing_data = [
                item for item in missing_data
                if item and item.strip().lower() not in screening_optional_labels
            ]

    return missing_data, recommended_tests


def _result_quality_summary(
    report: Optional[dict],
    missing_data: Optional[list[str]] = None,
    recommended_tests: Optional[list[str]] = None,
) -> dict:
    missing_data = list(missing_data or [])
    recommended_tests = list(recommended_tests or [])
    trace = (report or {}).get("explanation_trace") or {}
    risk_assessment = (report or {}).get("risk_assessment") or {}

    prediction_mode = str(trace.get("prediction_mode") or "").strip().lower()
    candidate_status = str(trace.get("selected_candidate_status") or "").strip().upper()

    confidence = risk_assessment.get("confidence")
    confidence_pct = None
    if confidence is not None:
        try:
            confidence_pct = round(max(0.0, min(1.0, float(confidence))) * 100.0, 1)
        except (TypeError, ValueError):
            confidence_pct = None

    coverage = trace.get("match_coverage")
    coverage_pct = None
    if coverage is not None:
        try:
            coverage_pct = round(max(0.0, min(1.0, float(coverage))) * 100.0, 1)
        except (TypeError, ValueError):
            coverage_pct = None

    is_partial_prediction = (
        prediction_mode == "partial_match_prediction"
        or candidate_status == "POSSIBLE"
    )
    has_data_gaps = bool(missing_data or recommended_tests)
    is_low_confidence = confidence_pct is not None and confidence_pct < 70.0

    if is_partial_prediction or has_data_gaps:
        level = "provisional"
        title = "Provisional result"
        message = "Current result is a screening estimate and can change after adding missing information."
    elif is_low_confidence:
        level = "review"
        title = "Moderate certainty"
        message = "Result is usable, but collecting additional information may improve certainty."
    else:
        level = "strong"
        title = "Strong result quality"
        message = "Result is based on sufficient matched evidence and has no major data gaps."

    bullets: list[str] = []
    if is_partial_prediction:
        if coverage_pct is not None:
            bullets.append(f"Matched from partial rule evidence ({coverage_pct:.1f}% coverage).")
        else:
            bullets.append("Matched from partial rule evidence.")
    if recommended_tests:
        bullets.append(f"{len(recommended_tests)} recommended lab test(s) are still missing.")
    if missing_data:
        bullets.append(f"{len(missing_data)} additional symptom/data point(s) are missing.")
    if confidence_pct is not None:
        bullets.append(f"Current confidence is {confidence_pct:.1f}%.")

    return {
        "level": level,
        "title": title,
        "message": message,
        "confidence_pct": confidence_pct,
        "coverage_pct": coverage_pct,
        "missing_count": len(missing_data),
        "recommended_tests_count": len(recommended_tests),
        "is_partial_prediction": is_partial_prediction,
        "bullets": bullets,
    }


def _facts_by_code(assessment_id: int) -> dict[str, dict[str, Any]]:
    rows = (
        db.session.query(CaseFact, Symptom)
        .join(Symptom, Symptom.id == CaseFact.symptom_id)
        .filter(CaseFact.assessment_id == assessment_id)
        .all()
    )
    facts: dict[str, dict[str, Any]] = {}
    for fact, symptom in rows:
        code = (symptom.code or "").strip().lower()
        if not code:
            continue

        input_type = (symptom.input_type or "BOOLEAN").upper()
        value: Any = None
        if input_type == "NUMBER":
            value = fact.value_number
        elif input_type == "BOOLEAN":
            value = fact.value_bool
        else:
            value = fact.value_text

        facts[code] = {
            "value": value,
            "unit": symptom.unit or "",
            "label": symptom.name or symptom.question_text or symptom.code,
            "input_type": input_type,
        }
    return facts


def _pick_numeric_fact(facts: dict[str, dict[str, Any]], codes: list[str]) -> Optional[dict[str, Any]]:
    for code in codes:
        item = facts.get(code)
        if not item:
            continue
        raw = item.get("value")
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        return {
            "code": code,
            "value": number,
            "unit": item.get("unit") or "",
            "label": item.get("label") or code,
        }
    return None


def _build_overview_callouts(
    report: Optional[dict],
    missing_data: list[str],
    recommended_tests: list[str],
) -> list[dict[str, str]]:
    report = report or {}
    likely = list(report.get("likely_conditions") or [])
    possible = list(report.get("possible_conditions") or [])
    key_yes = list((report.get("key_symptoms") or {}).get("yes") or [])
    reasoning = [str(item).strip() for item in (report.get("reasoning") or []) if str(item).strip()]
    anchors = ["head-right", "chest-left", "chest-right", "abdomen-right", "abdomen-left"]

    callouts: list[dict[str, str]] = []

    if likely:
        top = likely[0]
        title = top.get("diagnosis_name") or top.get("diagnosis_code") or "Likely condition"
        confidence_pct = round(float(top.get("confidence") or 0) * 100.0)
        callouts.append({
            "title": f"Likely: {title}",
            "body": f"High evidence with estimated confidence around {confidence_pct}%.",
        })

    if key_yes:
        callouts.append({
            "title": key_yes[0],
            "body": "Patient reported this symptom during assessment.",
        })
    if len(key_yes) > 1:
        callouts.append({
            "title": key_yes[1],
            "body": "Additional finding that contributes to current result.",
        })

    if recommended_tests:
        preview = ", ".join(recommended_tests[:2])
        if len(recommended_tests) > 2:
            preview += ", ..."
        callouts.append({
            "title": "Lab confirmation recommended",
            "body": f"Suggested next tests: {preview}",
        })
    elif missing_data:
        callouts.append({
            "title": "Missing clinical information",
            "body": "Add more symptom details to improve certainty.",
        })

    if possible and len(callouts) < 5:
        secondary = possible[0]
        label = secondary.get("diagnosis_name") or secondary.get("diagnosis_code") or "Possible condition"
        callouts.append({
            "title": f"Possible: {label}",
            "body": "Moderate evidence candidate tracked in this report.",
        })

    if reasoning and len(callouts) < 5:
        callouts.append({
            "title": "Clinical reasoning",
            "body": reasoning[0],
        })

    fallback_callouts = [
        {
            "title": "Symptom tracking",
            "body": "Track any worsening symptoms and update the latest assessment findings.",
        },
        {
            "title": "Follow-up focus",
            "body": "Prioritize high-impact symptoms to improve confidence in next run.",
        },
        {
            "title": "Lab verification",
            "body": "Add confirmatory lab values when available for stronger evidence.",
        },
        {
            "title": "Care note",
            "body": "Keep monitoring and review this summary after new patient inputs.",
        },
    ]
    fallback_index = 0
    while len(callouts) < 5:
        callouts.append(fallback_callouts[fallback_index % len(fallback_callouts)])
        fallback_index += 1

    for index, item in enumerate(callouts[:5]):
        item["anchor"] = anchors[index]

    return callouts[:5]


def _consultation_overview_context(assessment: Assessment) -> dict[str, Any]:
    report = build_report(assessment.id)
    answers_summary = _answers_summary(assessment.id)
    rule_summary = _rule_summary(report)
    missing_data, recommended_tests = _assessment_data_gaps(assessment.id, rule_summary)
    result_quality = _result_quality_summary(report, missing_data, recommended_tests)

    facts = _facts_by_code(assessment.id)
    pulse = _pick_numeric_fact(facts, ["heart_rate", "pulse", "bpm"])
    systolic = _pick_numeric_fact(facts, ["systolic_bp", "sbp", "blood_pressure_systolic"])
    diastolic = _pick_numeric_fact(facts, ["diastolic_bp", "dbp", "blood_pressure_diastolic"])
    glucose = _pick_numeric_fact(facts, ["fpg", "random_glucose", "glucose", "blood_glucose", "hba1c"])

    risk = (report or {}).get("risk_assessment") or {}
    likely = list((report or {}).get("likely_conditions") or [])
    possible = list((report or {}).get("possible_conditions") or [])
    candidate_items = likely + possible

    confidence_pct = result_quality.get("confidence_pct")
    if confidence_pct is None:
        try:
            confidence_pct = round(float(risk.get("confidence") or 0) * 100.0, 1)
        except (TypeError, ValueError):
            confidence_pct = 0.0

    user = assessment.user
    age_text = f"{int(user.age_years)} years" if user and user.age_years is not None else "--"
    sex_value = ((user.sex_at_birth or "").replace("_", " ").strip() if user else "")
    sex_text = sex_value.title() if sex_value else "--"

    diagnosis_notes: list[dict[str, str]] = []
    for item in candidate_items[:3]:
        label = item.get("diagnosis_name") or item.get("diagnosis_code") or "Condition"
        evidence = item.get("evidence_level") or "-"
        summary = item.get("summary") or f"Evidence level: {evidence}"
        diagnosis_notes.append({"title": label, "text": summary})
    if not diagnosis_notes:
        diagnosis_notes.append({
            "title": "No ranked candidates yet",
            "text": "Finish additional inputs to generate a more specific result.",
        })

    heart_rate_text = "--"
    if pulse:
        pulse_value = pulse["value"]
        heart_rate_text = f"{int(round(pulse_value))} BPM" if pulse_value is not None else "--"

    blood_pressure_text = "--"
    if systolic and diastolic:
        blood_pressure_text = f"{int(round(systolic['value']))}/{int(round(diastolic['value']))}"

    glucose_text = "--"
    glucose_unit = ""
    if glucose:
        g_val = glucose["value"]
        glucose_text = f"{g_val:.1f}".rstrip("0").rstrip(".")
        glucose_unit = glucose.get("unit") or ""

    primary_label = risk.get("diagnosis_name") or risk.get("diagnosis_code") or "Undetermined"
    risk_level = (risk.get("risk_level") or "UNKNOWN").upper()

    overview_callouts = _build_overview_callouts(report, missing_data, recommended_tests)

    return {
        "assessment": assessment,
        "report": report,
        "answers_summary": answers_summary,
        "result_quality": result_quality,
        "missing_data": missing_data,
        "recommended_tests": recommended_tests,
        "overview_callouts": overview_callouts,
        "primary_label": primary_label,
        "risk_level": risk_level,
        "confidence_pct": float(confidence_pct or 0.0),
        "heart_rate_text": heart_rate_text,
        "blood_pressure_text": blood_pressure_text,
        "glucose_text": glucose_text,
        "glucose_unit": glucose_unit,
        "diagnosis_notes": diagnosis_notes,
        "patient_age_text": age_text,
        "patient_sex_text": sex_text,
        "patient_blood_text": "--",
        "patient_contact_text": user.email if user and user.email else "--",
        "patient_phone_text": "--",
    }


def _format_condition(detail: dict, symptom_map: dict) -> dict:
    sid = detail.get("symptom_id")
    symptom = symptom_map.get(sid)
    label = None
    if symptom:
        label = symptom.name or symptom.question_text or symptom.code
    if not label:
        label = detail.get("symptom_code") or f"Symptom {sid}"

    operator = detail.get("operator") or detail.get("op") or "=="
    expected = detail.get("expected")
    if expected is None:
        expected = detail.get("value")
    actual = detail.get("actual")
    return {
        "label": label,
        "operator": operator,
        "expected": expected,
        "actual": actual,
    }


def _build_explanation_blocks(report: Optional[dict]) -> list:
    if not report:
        return []
    trace = report.get("explanation_trace") or {}
    rules_fired = trace.get("rules_fired") or []
    if not rules_fired and trace.get("fired_rule_code"):
        rules_fired = [
            {
                "rule_code": trace.get("fired_rule_code"),
                "matched": trace.get("matched_conditions") or [],
            }
        ]

    symptom_ids = set()
    for rule in rules_fired:
        for item in (rule.get("matched") or rule.get("matched_conditions") or []):
            sid = item.get("symptom_id")
            if sid:
                symptom_ids.add(sid)

    symptom_map = {}
    if symptom_ids:
        symptom_map = {s.id: s for s in Symptom.query.filter(Symptom.id.in_(symptom_ids)).all()}

    blocks = []
    for rule in rules_fired:
        rule_code = rule.get("rule_code") or rule.get("rule_id") or "Rule"
        matched = rule.get("matched") or rule.get("matched_conditions") or []
        items = [_format_condition(item, symptom_map) for item in matched]
        if items:
            blocks.append({"rule_code": rule_code, "items": items})
    return blocks


def _load_assessment(user_id: int, start_flag: bool):
    assessment = None
    session_assessment_id = session.get("active_assessment_id")

    if start_flag:
        assessment = _get_or_create_assessment(user_id)
        session["active_assessment_id"] = assessment.id
    elif session_assessment_id:
        assessment = Assessment.query.filter_by(id=session_assessment_id, user_id=user_id).first()
    else:
        assessment = Assessment.query.filter_by(user_id=user_id, status="IN_PROGRESS").first()
        if assessment:
            session["active_assessment_id"] = assessment.id

    return assessment


@web_bp.get("/patient/diagnosis")
def patient_diagnosis():
    guard = require_login()
    if guard:
        return guard

    user_id = _current_user_id()
    if not user_id:
        return redirect(url_for("web.login_page"))

    now_local = datetime.now()
    now_utc = datetime.utcnow()
    me = session.get("me") or {}
    roles = current_roles()

    assessments_query = Assessment.query.filter_by(user_id=user_id)
    total_assessments = assessments_query.count()
    active_cases = assessments_query.filter(Assessment.status == "IN_PROGRESS").count()

    day_start_utc = datetime(now_utc.year, now_utc.month, now_utc.day)
    today_consultations = assessments_query.filter(Assessment.started_at >= day_start_utc).count()

    latest_assessment = (
        Assessment.query
        .filter_by(user_id=user_id)
        .order_by(Assessment.started_at.desc(), Assessment.id.desc())
        .first()
    )

    latest_run = None
    if latest_assessment:
        latest_run = (
            DiagnosisRun.query.options(selectinload(DiagnosisRun.disease))
            .filter_by(assessment_id=latest_assessment.id)
            .order_by(DiagnosisRun.created_at.desc(), DiagnosisRun.id.desc())
            .first()
        )

    completed_assessment_ids = [
        row[0]
        for row in (
            db.session.query(Assessment.id)
            .filter(
                Assessment.user_id == user_id,
                Assessment.status == "COMPLETED",
            )
            .all()
        )
    ]
    reviewed_assessment_ids = set()
    if completed_assessment_ids:
        reviewed_assessment_ids = {
            row[0]
            for row in (
                db.session.query(DiagnosisRun.assessment_id)
                .filter(DiagnosisRun.assessment_id.in_(completed_assessment_ids))
                .distinct()
                .all()
            )
        }
    pending_reviews = max(0, len(completed_assessment_ids) - len(reviewed_assessment_ids))

    high_risk_alerts = (
        db.session.query(DiagnosisRun.id)
        .join(Assessment, Assessment.id == DiagnosisRun.assessment_id)
        .filter(
            Assessment.user_id == user_id,
            DiagnosisRun.risk_level == "HIGH",
        )
        .count()
    )

    started_for_code = (
        latest_assessment.started_at if latest_assessment and latest_assessment.started_at else now_local
    )
    code_suffix = latest_assessment.id if latest_assessment else user_id
    diagnosis_case_code = f"DX-{started_for_code.year}-{int(code_suffix):03d}"
    display_name = (
        (me.get("name") or "").strip()
        or (me.get("email") or "").strip()
        or f"Patient #{user_id}"
    )
    latest_risk_label = (
        latest_run.risk_level.title()
        if latest_run and latest_run.risk_level
        else "Undetermined"
    )

    monitoring_tone = "neutral"
    monitoring_label = "No active monitoring"
    if active_cases > 0:
        monitoring_tone = "success"
        monitoring_label = "Assessment in progress"
    elif latest_run:
        monitoring_tone = "info"
        monitoring_label = "Recent diagnosis available"

    diagnosis_hero = {
        "greeting": _greeting_for_hour(now_local.hour),
        "patient_heading": display_name,
        "meta_items": [
            f"ID: {diagnosis_case_code}",
            f"Role: {_role_label(roles, str(me.get('role') or 'USER'))}",
            f"Latest risk: {latest_risk_label}",
        ],
        "cycle_label": _clinical_cycle_for_date(now_local),
        "phase_label": _phase_for_date(now_local),
        "monitoring_tone": monitoring_tone,
        "monitoring_label": monitoring_label,
        "shift_label": _shift_for_hour(now_local.hour),
        "workspace_label": "Clinical workspace" if roles.intersection({"ADMIN", "KB_DOCTOR"}) else "Patient workspace",
    }

    diagnosis_stats = {
        "today_consultations": today_consultations,
        "today_consultations_note": (
            f"{today_consultations} started today"
            if today_consultations
            else "No consultations started today"
        ),
        "active_cases": active_cases,
        "active_cases_note": f"{total_assessments} total assessment(s)",
        "pending_reviews": pending_reviews,
        "pending_reviews_note": (
            f"{pending_reviews} completed case(s) without result review"
            if pending_reviews
            else "No pending review queue"
        ),
        "high_risk_alerts": high_risk_alerts,
        "high_risk_alerts_note": (
            f"{high_risk_alerts} high-risk diagnosis run(s) on record"
            if high_risk_alerts
            else "No high-risk alerts right now"
        ),
    }

    today_schedule = []
    today_assessments = (
        Assessment.query
        .filter(
            Assessment.user_id == user_id,
            Assessment.started_at >= day_start_utc,
        )
        .order_by(Assessment.started_at.asc(), Assessment.id.asc())
        .limit(5)
        .all()
    )
    today_assessment_ids = [item.id for item in today_assessments]
    today_runs_by_assessment = {}
    if today_assessment_ids:
        today_runs = (
            DiagnosisRun.query.options(selectinload(DiagnosisRun.disease))
            .filter(DiagnosisRun.assessment_id.in_(today_assessment_ids))
            .order_by(DiagnosisRun.created_at.desc(), DiagnosisRun.id.desc())
            .all()
        )
        for run in today_runs:
            if run.assessment_id not in today_runs_by_assessment:
                today_runs_by_assessment[run.assessment_id] = run

    for assessment in today_assessments:
        run = today_runs_by_assessment.get(assessment.id)
        time_label = assessment.started_at.strftime("%I:%M %p") if assessment.started_at else "--"
        case_code = f"C-{assessment.id}"
        detail_parts = [assessment.status.replace("_", " ").title()]
        if run and run.risk_level:
            detail_parts.append(f"Risk: {run.risk_level.title()}")
        if run and run.disease and run.disease.name:
            detail_parts.append(run.disease.name)

        entry = {
            "time": time_label,
            "title": f"Assessment review - Case {case_code}",
            "detail": " • ".join(detail_parts),
            "icon": "bi-heart-pulse",
            "icon_wrap_class": "bg-primary bg-opacity-10 text-primary",
            "badge_label": "Consultation",
            "badge_class": "bg-primary-subtle text-primary",
        }

        if assessment.status == "COMPLETED":
            entry["title"] = f"Completed case - {case_code}"
            entry["icon"] = "bi-clipboard2-check"
            entry["icon_wrap_class"] = "bg-success bg-opacity-10 text-success"
            entry["badge_label"] = "Follow-up"
            entry["badge_class"] = "bg-success-subtle text-success"
        if run and run.risk_level == "HIGH":
            entry["title"] = f"High risk validation - {case_code}"
            entry["icon"] = "bi-shield-exclamation"
            entry["icon_wrap_class"] = "bg-warning bg-opacity-10 text-warning"
            entry["badge_label"] = "Review"
            entry["badge_class"] = "bg-warning-subtle text-warning"

        today_schedule.append(entry)

    latest_overview_url = (
        url_for("web.patient_consultation_overview_v2", assessment_id=latest_assessment.id)
        if latest_assessment
        else None
    )

    return render_template(
        "patient/diagnosis.html",
        diagnosis_hero=diagnosis_hero,
        diagnosis_stats=diagnosis_stats,
        today_schedule=today_schedule,
        latest_overview_url=latest_overview_url,
    )


@web_bp.get("/patient/history")
def patient_history():
    guard = require_login()
    if guard:
        return guard

    user_id = _current_user_id()
    perms = current_permissions()
    roles = current_roles()
    can_view_all = "ADMIN" in roles or bool(perms.intersection({"CASE_VIEW_ALL", "CASE_VIEW_FACTS"}))

    query = (
        Assessment.query.options(selectinload(Assessment.user))
        .order_by(Assessment.started_at.desc())
    )
    if not can_view_all:
        query = query.filter_by(user_id=user_id)

    assessments = query.all()
    assessment_ids = [a.id for a in assessments]

    runs_by_assessment = {}
    if assessment_ids:
        runs = (
            DiagnosisRun.query.options(selectinload(DiagnosisRun.disease))
            .filter(DiagnosisRun.assessment_id.in_(assessment_ids))
            .order_by(DiagnosisRun.created_at.desc())
            .all()
        )
        for run in runs:
            if run.assessment_id not in runs_by_assessment:
                runs_by_assessment[run.assessment_id] = run

    def status_label(status: str) -> str:
        return "Completed" if status == "COMPLETED" else "In Progress"

    def status_class(status: str) -> str:
        return "bg-success" if status == "COMPLETED" else "bg-warning"

    def result_text(run: Optional[DiagnosisRun]) -> str:
        if run and run.disease and run.disease.name:
            return run.disease.name
        if run and run.risk_level:
            return run.risk_level.title().replace("_", " ")
        return "Undetermined"

    def result_class(text: str) -> str:
        value = (text or "").lower()
        if "normal" in value:
            return "bg-success"
        if "prediabetes" in value:
            return "bg-warning"
        if "high" in value:
            return "bg-danger"
        if "type 1" in value or "type1" in value:
            return "bg-info"
        return "bg-secondary"

    risk_filter = (request.args.get("risk") or "").strip().lower()
    high_risk_only = risk_filter == "high"

    history_rows = []
    high_risk_count = 0
    for assessment in assessments:
        run = runs_by_assessment.get(assessment.id)
        result = result_text(run)
        if run and run.risk_level == "HIGH":
            high_risk_count += 1

        if high_risk_only and (not run or run.risk_level != "HIGH"):
            continue

        patient_name = (
            assessment.user.name
            if assessment.user and assessment.user.name
            else f"Patient #{assessment.user_id}"
        )
        timestamp = assessment.completed_at or assessment.started_at
        view_url = (
            url_for("web.admin_consultation_view", assessment_id=assessment.id)
            if can_view_all
            else url_for("web.patient_consultation_view", assessment_id=assessment.id)
        )
        history_rows.append(
            {
                "case_id": f"C-{assessment.id}",
                "patient": patient_name,
                "status": status_label(assessment.status),
                "status_class": status_class(assessment.status),
                "result": result,
                "result_class": result_class(result),
                "date": timestamp.strftime("%Y-%m-%d %H:%M") if timestamp else "--",
                "view_url": view_url,
            }
        )

    total = len(assessments)
    completed = sum(1 for a in assessments if a.status == "COMPLETED")
    in_progress = total - completed

    history_stats = {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "high_risk": high_risk_count,
    }

    return render_template(
        "patient/history.html",
        history_rows=history_rows,
        history_stats=history_stats,
        show_patient_column=can_view_all,
        history_filter=("high" if high_risk_only else ""),
    )


@web_bp.get("/admin/consultations/<int:assessment_id>")
def admin_consultation_view(assessment_id: int):
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("CASE_VIEW_ALL", "CASE_VIEW_FACTS")
    if guard:
        return guard

    assessment = Assessment.query.get(assessment_id)
    if not assessment:
        abort(404)

    report = build_report(assessment.id)
    answers_summary = _answers_summary(assessment.id)
    rule_summary = _rule_summary(report)
    missing_data, recommended_tests = _assessment_data_gaps(assessment.id, rule_summary)
    result_quality = _result_quality_summary(report, missing_data, recommended_tests)

    return render_template(
        "patient/assessment_core.html",
        view_state="results",
        assessment=assessment,
        steps=build_assessment_steps("results"),
        report=report,
        answers_summary=answers_summary,
        rule_summary=rule_summary,
        missing_data=missing_data,
        recommended_tests=recommended_tests,
        result_quality=result_quality,
    )


@web_bp.get("/patient/consultations/<int:assessment_id>")
def patient_consultation_view(assessment_id: int):
    guard = require_login()
    if guard:
        return guard

    user_id = _current_user_id()
    if not user_id:
        return redirect(url_for("web.login_page"))

    assessment = Assessment.query.filter_by(id=assessment_id, user_id=user_id).first()
    if not assessment:
        abort(404)

    report = build_report(assessment.id)
    answers_summary = _answers_summary(assessment.id)
    rule_summary = _rule_summary(report)
    missing_data, recommended_tests = _assessment_data_gaps(assessment.id, rule_summary)
    result_quality = _result_quality_summary(report, missing_data, recommended_tests)

    return render_template(
        "patient/assessment_core.html",
        view_state="results",
        assessment=assessment,
        steps=build_assessment_steps("results"),
        report=report,
        answers_summary=answers_summary,
        rule_summary=rule_summary,
        missing_data=missing_data,
        recommended_tests=recommended_tests,
        result_quality=result_quality,
    )


@web_bp.get("/admin/consultations/<int:assessment_id>/overview-v2")
def admin_consultation_overview_v2(assessment_id: int):
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("CASE_VIEW_ALL", "CASE_VIEW_FACTS")
    if guard:
        return guard

    assessment = Assessment.query.options(selectinload(Assessment.user)).filter_by(id=assessment_id).first()
    if not assessment:
        abort(404)

    context = _consultation_overview_context(assessment)
    context.update(
        {
            "legacy_url": url_for("web.admin_consultation_view", assessment_id=assessment.id),
            "dashboard_url": url_for("web.admin_dashboard"),
            "download_url": "",
            "viewer_mode": "admin",
        }
    )
    return render_template("patient/assessment_overview_v2.html", **context)


@web_bp.get("/patient/consultations/<int:assessment_id>/overview-v2")
def patient_consultation_overview_v2(assessment_id: int):
    guard = require_login()
    if guard:
        return guard

    user_id = _current_user_id()
    if not user_id:
        return redirect(url_for("web.login_page"))

    assessment = (
        Assessment.query.options(selectinload(Assessment.user))
        .filter_by(id=assessment_id, user_id=user_id)
        .first()
    )
    if not assessment:
        abort(404)

    context = _consultation_overview_context(assessment)
    context.update(
        {
            "legacy_url": url_for("web.patient_consultation_view", assessment_id=assessment.id),
            "dashboard_url": url_for("web.patient_diagnosis"),
            "download_url": url_for("web.patient_report_pdf", assessment_id=assessment.id),
            "viewer_mode": "patient",
        }
    )
    return render_template("patient/assessment_overview_v2.html", **context)


@web_bp.get("/patient/profile")
def patient_profile():
    guard = require_login()
    if guard:
        return guard
    return render_template("patient/profile.html")


@web_bp.route("/patient/assessment", methods=["GET", "POST"])
def patient_assessment():
    guard = require_login()
    if guard:
        return guard

    user_id = _current_user_id()
    if not user_id:
        return redirect(url_for("web.login_page"))
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for("web.login_page"))
    patient_profile = _patient_profile_from_user(user)

    if request.method == "POST":
        actions = request.form.getlist("action")
        action = actions[0] if actions else ""
        if "back" in actions:
            action = "back"
        if action == "restart":
            now = datetime.utcnow()
            in_progress = Assessment.query.filter_by(user_id=user_id, status="IN_PROGRESS").all()
            for current in in_progress:
                current.status = "COMPLETED"
                if not current.completed_at:
                    current.completed_at = now

            new_assessment = Assessment(user_id=user_id, patient_id=user_id, status="IN_PROGRESS")
            db.session.add(new_assessment)
            db.session.commit()

            session["active_assessment_id"] = new_assessment.id
            session.pop("last_answered_symptom_id", None)
            session.pop("finish_snooze", None)
            session.pop("finish_snooze_assessment_id", None)
            session.pop("answer_history", None)
            session.pop("back_symptom_id", None)
            session.pop("patient_profile_assessment_id", None)
            session.pop("patient_profile_step", None)
            session.pop("classic_checklist_done_assessment_id", None)
            return redirect(url_for("web.patient_assessment"))

        if action == "start_assessment":
            assessment = Assessment(user_id=user_id, patient_id=user_id, status="IN_PROGRESS")
            db.session.add(assessment)
            db.session.commit()
            session["active_assessment_id"] = assessment.id
            session.pop("last_answered_symptom_id", None)
            session.pop("finish_snooze", None)
            session.pop("finish_snooze_assessment_id", None)
            session.pop("answer_history", None)
            session.pop("back_symptom_id", None)
            session.pop("patient_profile_assessment_id", None)
            session.pop("patient_profile_step", None)
            session.pop("classic_checklist_done_assessment_id", None)
            return redirect(url_for("web.patient_assessment"))

        assessment = _load_assessment(user_id, False) or _get_or_create_assessment(user_id)
        session["active_assessment_id"] = assessment.id
        patient_profile_done = session.get("patient_profile_assessment_id") == assessment.id

        if action == "save_patient_intro":
            survey_for = (request.form.get("survey_for") or "myself").strip().lower()
            if survey_for == "someone":
                survey_for = "someone_else"
            if survey_for not in {"myself", "someone_else"}:
                survey_for = "myself"
            user.survey_for = survey_for
            db.session.commit()
            patient_profile = _patient_profile_from_user(user)
            session["patient_profile_step"] = "sex"
            return redirect(url_for("web.patient_assessment"))

        if action == "save_patient_sex":
            sex_at_birth = (request.form.get("sex_at_birth") or "").strip().lower()
            if sex_at_birth not in {"female", "male", "intersex", "prefer_not"}:
                session["form_error"] = "Please select sex listed on birth certificate."
                session["patient_profile_step"] = "sex"
                return redirect(url_for("web.patient_assessment"))
            user.sex_at_birth = sex_at_birth
            db.session.commit()
            patient_profile = _patient_profile_from_user(user)
            session["patient_profile_step"] = "age"
            return redirect(url_for("web.patient_assessment"))

        if action == "save_patient_age":
            age_raw = (request.form.get("age_years") or "").strip()
            try:
                age_years = int(age_raw)
            except (TypeError, ValueError):
                session["form_error"] = "Please enter a valid age in years."
                session["patient_profile_step"] = "age"
                return redirect(url_for("web.patient_assessment"))
            if age_years < 1 or age_years > 120:
                session["form_error"] = "Age must be between 1 and 120."
                session["patient_profile_step"] = "age"
                return redirect(url_for("web.patient_assessment"))
            user.age_years = age_years
            db.session.commit()
            patient_profile = _patient_profile_from_user(user)
            session["patient_profile_assessment_id"] = assessment.id
            session.pop("patient_profile_step", None)
            return redirect(url_for("web.patient_assessment"))

        if action == "patient_back_to_intro":
            session["patient_profile_step"] = "intro"
            return redirect(url_for("web.patient_assessment"))

        if action == "patient_back_to_sex":
            session["patient_profile_step"] = "sex"
            return redirect(url_for("web.patient_assessment"))

        if action == "patient_back_to_age":
            session.pop("patient_profile_assessment_id", None)
            session["patient_profile_step"] = "age"
            return redirect(url_for("web.patient_assessment"))

        if action == "save_classic_checklist":
            checklist = _classic_checklist_symptoms()
            checklist_ids = [s.id for s in checklist]
            selected_ids = set()
            for raw_id in request.form.getlist("symptom_ids"):
                try:
                    selected_ids.add(int(raw_id))
                except (TypeError, ValueError):
                    continue
            answered_root_ids = []
            for symptom in checklist:
                answered_value = symptom.id in selected_ids
                _upsert_fact(assessment.id, symptom.id, answered_value, input_type="BOOLEAN")
                answered_root_ids.append(symptom.id)
            db.session.commit()
            session["classic_checklist_done_assessment_id"] = assessment.id
            if answered_root_ids:
                session["last_answered_symptom_id"] = answered_root_ids[-1]
            return redirect(url_for("web.patient_assessment"))

        if not patient_profile_done:
            return redirect(url_for("web.patient_assessment"))

        if action == "submit_answer":
            try:
                symptom_id = int(request.form.get("symptom_id"))
            except (TypeError, ValueError):
                session["form_error"] = "Please answer the question to continue."
                return redirect(url_for("web.patient_assessment"))

            symptom = Symptom.query.get(symptom_id)
            if not symptom:
                session["form_error"] = "Question not found. Please try again."
                return redirect(url_for("web.patient_assessment"))

            raw = request.form.get("answer")
            input_type = (symptom.input_type or "BOOLEAN").upper()
            if input_type == "BOOLEAN":
                parsed = _parse_bool_value(raw)
                if raw is None or raw == "":
                    session["form_error"] = "Please choose Yes, No, or Don't know."
                    return redirect(url_for("web.patient_assessment"))
                _upsert_fact(assessment.id, symptom.id, parsed, input_type="BOOLEAN")
            elif input_type == "NUMBER":
                if isinstance(raw, str) and raw.strip().lower() in {"unknown", "dont_know", "don't_know", "dk"}:
                    _upsert_fact(assessment.id, symptom.id, None, input_type="NUMBER")
                    db.session.commit()
                    session["last_answered_symptom_id"] = symptom.id
                    history = session.get("answer_history") or []
                    if not isinstance(history, list):
                        history = []
                    history.append(symptom.id)
                    session["answer_history"] = history
                    return redirect(url_for("web.patient_assessment"))
                try:
                    number_val = float(raw)
                except (TypeError, ValueError):
                    session["form_error"] = "Please enter a valid number or choose Don't know."
                    return redirect(url_for("web.patient_assessment"))
                _upsert_fact(assessment.id, symptom.id, number_val, input_type="NUMBER")
            elif input_type in {"TEXT", "SINGLE"}:
                text_val = str(raw or "").strip()
                if not text_val:
                    session["form_error"] = "Please enter a value."
                    return redirect(url_for("web.patient_assessment"))
                _upsert_fact(assessment.id, symptom.id, text_val, input_type=input_type)
            else:
                session["form_error"] = "Unsupported input type."
                return redirect(url_for("web.patient_assessment"))

            db.session.commit()
            session["last_answered_symptom_id"] = symptom.id
            history = session.get("answer_history") or []
            if not isinstance(history, list):
                history = []
            history.append(symptom.id)
            session["answer_history"] = history
            return redirect(url_for("web.patient_assessment"))

        if action == "finish_now":
            session.pop("finish_snooze", None)
            session.pop("finish_snooze_assessment_id", None)
            run_diagnosis_now(assessment)
            return redirect(url_for("web.patient_assessment", view="results"))

        if action == "continue_interview":
            session.pop("finish_snooze", None)
            session["finish_snooze_assessment_id"] = assessment.id
            return redirect(url_for("web.patient_assessment"))

        if action == "back":
            history = session.get("answer_history") or []
            if not isinstance(history, list) or not history:
                return redirect(url_for("web.patient_assessment"))
            back_id = history.pop()  # last answered symptom
            CaseFact.query.filter_by(assessment_id=assessment.id, symptom_id=back_id).delete()
            db.session.commit()
            session["answer_history"] = history
            session["back_symptom_id"] = back_id
            session["last_answered_symptom_id"] = history[-1] if history else None
            return redirect(url_for("web.patient_assessment"))

    assessment = _load_assessment(user_id, bool(request.args.get("start")))

    if not assessment:
        return render_template(
            "patient/assessment_core.html",
            view_state="start",
            assessment=None,
            steps=build_assessment_steps("start"),
        )

    if assessment.status != "IN_PROGRESS" or request.args.get("view") == "results":
        report = build_report(assessment.id)
        answers_summary = _answers_summary(assessment.id)
        rule_summary = _rule_summary(report)
        missing_data, recommended_tests = _assessment_data_gaps(assessment.id, rule_summary)
        result_quality = _result_quality_summary(report, missing_data, recommended_tests)
        return render_template(
            "patient/assessment_core.html",
            view_state="results",
            assessment=assessment,
            steps=build_assessment_steps("results"),
            report=report,
            answers_summary=answers_summary,
            rule_summary=rule_summary,
            missing_data=missing_data,
            recommended_tests=recommended_tests,
            result_quality=result_quality,
        )

    patient_profile_done = session.get("patient_profile_assessment_id") == assessment.id
    if not patient_profile_done:
        patient_step = _normalize_key(session.get("patient_profile_step"))
        if patient_step not in {"intro", "sex", "age"}:
            patient_step = "intro"
            session["patient_profile_step"] = patient_step
        view_state_map = {
            "intro": "patient_intro",
            "sex": "patient_sex",
            "age": "patient_age",
        }
        patient_view_state = view_state_map[patient_step]
        return render_template(
            "patient/assessment_core.html",
            view_state=patient_view_state,
            assessment=assessment,
            steps=build_assessment_steps(patient_view_state),
            patient_profile=patient_profile,
            error_message=session.pop("form_error", None),
        )

    _sync_patient_info_symptom_facts(assessment.id, patient_profile)
    next_patient_info = _next_patient_info_symptom(assessment.id)
    if next_patient_info:
        back_symptom_id = session.pop("back_symptom_id", None)
        if back_symptom_id:
            back_symptom = Symptom.query.get(back_symptom_id)
            if back_symptom and _is_patient_info_symptom(back_symptom):
                next_patient_info = back_symptom
        return render_template(
            "patient/assessment_core.html",
            view_state="question",
            assessment=assessment,
            steps=build_assessment_steps("question", symptom=next_patient_info),
            symptom=next_patient_info,
            question_style=_question_style(next_patient_info),
            question_trigger_text=_trigger_text(next_patient_info),
            error_message=session.pop("form_error", None),
            answers_summary=_answers_summary(assessment.id),
            can_go_back=bool(session.get("answer_history")),
        )

    checklist_done = session.get("classic_checklist_done_assessment_id") == assessment.id
    if not checklist_done:
        checklist_symptoms = _classic_checklist_symptoms()
        if checklist_symptoms:
            checklist_ids = [symptom.id for symptom in checklist_symptoms]
            existing_rows = (
                CaseFact.query
                .filter(CaseFact.assessment_id == assessment.id, CaseFact.symptom_id.in_(checklist_ids))
                .all()
            )
            selected_ids = {row.symptom_id for row in existing_rows if row.value_bool is True}
            return render_template(
                "patient/assessment_core.html",
                view_state="checklist_batch",
                assessment=assessment,
                steps=build_assessment_steps("checklist_batch"),
                checklist_symptoms=checklist_symptoms,
                checklist_selected_ids=selected_ids,
                error_message=session.pop("form_error", None),
                answers_summary=_answers_summary(assessment.id),
                can_go_back=bool(session.get("answer_history")),
            )
        session["classic_checklist_done_assessment_id"] = assessment.id

    inference = get_inference_snapshot(assessment.id)
    offer_finish = bool(inference.get("best_row") and inference.get("finalizable"))
    legacy_snooze = bool(session.get("finish_snooze"))
    snoozed_assessment_id = session.get("finish_snooze_assessment_id")
    if legacy_snooze and not snoozed_assessment_id:
        session["finish_snooze_assessment_id"] = assessment.id
        snoozed_assessment_id = assessment.id
        session.pop("finish_snooze", None)
    is_snoozed = snoozed_assessment_id == assessment.id
    if offer_finish and not is_snoozed:
        return render_template(
            "patient/assessment_core.html",
            view_state="confirm_finish",
            assessment=assessment,
            steps=build_assessment_steps("confirm_finish"),
            candidate=inference.get("best_row"),
        )

    back_symptom_id = session.pop("back_symptom_id", None)
    next_symptom = None
    if back_symptom_id:
        next_symptom = Symptom.query.get(back_symptom_id)
    if not next_symptom:
        next_symptom = _next_symptom(assessment.id, session.get("last_answered_symptom_id"))
    if not next_symptom:
        session.pop("finish_snooze", None)
        session.pop("finish_snooze_assessment_id", None)
        run_diagnosis_now(assessment)
        return redirect(url_for("web.patient_assessment", view="results"))

    error_message = session.pop("form_error", None)

    return render_template(
        "patient/assessment_core.html",
        view_state="question",
        assessment=assessment,
        steps=build_assessment_steps("question", symptom=next_symptom),
        symptom=next_symptom,
        question_style=_question_style(next_symptom),
        question_trigger_text=_trigger_text(next_symptom),
        error_message=error_message,
        answers_summary=_answers_summary(assessment.id),
        can_go_back=bool(session.get("answer_history")),
    )


@web_bp.route("/patient/messages", methods=["GET", "POST"])
def patient_messages():
    if request.method == "POST":
        return redirect(url_for("web.patient_assessment"))
    return redirect(url_for("web.patient_assessment"))


@web_bp.get("/patient/assessment/<int:assessment_id>/report.pdf")
def patient_report_pdf(assessment_id: int):
    guard = require_login()
    if guard:
        return guard

    user_id = _current_user_id()
    if not user_id:
        return redirect(url_for("web.login_page"))

    assessment = Assessment.query.filter_by(id=assessment_id, user_id=user_id).first()
    if not assessment:
        abort(404)

    report = build_report(assessment.id)
    try:
        pdf_bytes = build_report_pdf(assessment, report)
    except RuntimeError as exc:
        return str(exc), 500
    filename = f"assessment_{assessment.id}_report.pdf"
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@web_bp.route("/patient/symptoms", methods=["GET", "POST"])
def patient_update_symptoms():
    guard = require_login()
    if guard:
        return guard

    user_id = _current_user_id()
    if not user_id:
        return redirect(url_for("web.login_page"))

    latest_assessment = (
        Assessment.query
        .filter_by(user_id=user_id)
        .order_by(Assessment.started_at.desc(), Assessment.id.desc())
        .first()
    )
    saved = False
    if request.method == "POST":
        symptom_ids = request.form.getlist("symptom_ids")
        ids = []
        for sid in symptom_ids:
            try:
                ids.append(int(sid))
            except (TypeError, ValueError):
                continue

        assessment = latest_assessment or _get_or_create_assessment(user_id)
        session["active_assessment_id"] = assessment.id
        existing = {a.symptom_id: a for a in CaseFact.query.filter_by(assessment_id=assessment.id).all()}
        for sid in ids:
            answer = request.form.get(f"symptom_{sid}")
            if answer is None:
                continue
            value_bool = _parse_bool_value(answer)
            if sid in existing:
                existing[sid].value_bool = value_bool
                existing[sid].value_text = None
                existing[sid].value_number = None
            elif value_bool is not None:
                db.session.add(CaseFact(
                    assessment_id=assessment.id,
                    symptom_id=sid,
                    value_bool=value_bool,
                ))
        db.session.commit()
        saved = True

    answers_map = {}
    if latest_assessment:
        facts = CaseFact.query.filter_by(assessment_id=latest_assessment.id).all()
        for fact in facts:
            if fact.value_bool is True:
                answers_map[fact.symptom_id] = "yes"
            elif fact.value_bool is False:
                answers_map[fact.symptom_id] = "no"
            else:
                answers_map[fact.symptom_id] = "unknown"

    symptoms = (
        Symptom.query
        .filter_by(is_active=True)
        .order_by(Symptom.category.asc(), Symptom.priority_order.asc(), Symptom.id.asc())
        .all()
    )
    symptom_groups = {}
    for symptom in symptoms:
        key = symptom.category or "general"
        symptom_groups.setdefault(key, []).append(symptom)

    return render_template(
        "patient/symptoms_update.html",
        symptom_groups=symptom_groups,
        saved=saved,
        answers_map=answers_map,
    )


@web_bp.get("/patient/calendar")
def patient_calendar():
    guard = require_login()
    if guard:
        return guard
    return render_template("calendar.html")
