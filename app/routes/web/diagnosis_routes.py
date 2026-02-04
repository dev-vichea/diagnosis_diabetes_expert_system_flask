from typing import Any, Optional

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
)
from app.inference.facts import facts_for_assessment
from app.services.assessment_service import get_inference_snapshot, run_diagnosis_now
from app.services.report_builder import build_report
from app.services.report_pdf import build_report_pdf

from . import web_bp
from .utils import require_login, require_permissions, current_permissions, current_roles


def _current_user_id():
    me = session.get("me") or {}
    uid = me.get("user_id")
    return int(uid) if uid is not None else None


def _get_or_create_assessment(user_id: int) -> Assessment:
    active = Assessment.query.filter_by(user_id=user_id, status="IN_PROGRESS").first()
    if active:
        return active
    assessment = Assessment(user_id=user_id, status="IN_PROGRESS")
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
            _section_rank(s.ui_section or s.category),
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

    symptoms = _ordered_symptoms()
    symptom_map = {s.id: s for s in symptoms}

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

    # 3) Otherwise, ask the next root symptom.
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
        section = (symptom.ui_section or symptom.category or "General").strip() or "General"
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
                section = (height_symptom.ui_section or height_symptom.category or "Risk").strip() or "Risk"
                if section not in grouped:
                    grouped[section] = []
                    section_order.append(section)
                grouped[section].append({
                    "label": "BMI (kg/m²)",
                    "value": f"{bmi:.1f}",
                })
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    has_labs_defined = (
        Symptom.query.filter(Symptom.is_active.is_(True))
        .filter((Symptom.ui_section == "Labs") | (Symptom.category == "Labs"))
        .first()
        is not None
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
    if fired_rule_id:
        rule = Rule.query.get(fired_rule_id)
        if rule:
            rule_title = rule.title or rule.rule_code

    return {
        "rule_title": rule_title,
        "matched": _condition_labels(matched_items, symptom_map),
        "missing": _condition_labels(missing_items, symptom_map),
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
    return render_template("patient/diagnosis.html")


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

    history_rows = []
    high_risk_count = 0
    for assessment in assessments:
        run = runs_by_assessment.get(assessment.id)
        result = result_text(run)
        if run and run.risk_level == "HIGH":
            high_risk_count += 1
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
    missing_data = list(rule_summary.get("missing") or [])
    if not missing_data:
        facts = facts_for_assessment(assessment.id)
        parent = Symptom.query.filter_by(code="has_labs").first()
        if parent:
            lab_children = (
                Symptom.query
                .filter_by(parent_symptom_id=parent.id, is_active=True)
                .order_by(Symptom.priority_order.asc(), Symptom.id.asc())
                .all()
            )
            for lab in lab_children:
                if lab.code not in facts:
                    missing_data.append(lab.question_text or lab.name or lab.code)

    return render_template(
        "patient/assessment_core.html",
        view_state="results",
        assessment=assessment,
        steps=[
            {"key": "start", "label": "Start", "is_current": False, "is_done": True},
            {"key": "interview", "label": "Interview", "is_current": False, "is_done": True},
            {"key": "results", "label": "Results", "is_current": True, "is_done": False},
        ],
        report=report,
        answers_summary=answers_summary,
        rule_summary=rule_summary,
        missing_data=missing_data,
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
    missing_data = list(rule_summary.get("missing") or [])
    if not missing_data:
        facts = facts_for_assessment(assessment.id)
        parent = Symptom.query.filter_by(code="has_labs").first()
        if parent:
            lab_children = (
                Symptom.query
                .filter_by(parent_symptom_id=parent.id, is_active=True)
                .order_by(Symptom.priority_order.asc(), Symptom.id.asc())
                .all()
            )
            for lab in lab_children:
                if lab.code not in facts:
                    missing_data.append(lab.question_text or lab.name or lab.code)

    return render_template(
        "patient/assessment_core.html",
        view_state="results",
        assessment=assessment,
        steps=[
            {"key": "start", "label": "Start", "is_current": False, "is_done": True},
            {"key": "interview", "label": "Interview", "is_current": False, "is_done": True},
            {"key": "results", "label": "Results", "is_current": True, "is_done": False},
        ],
        report=report,
        answers_summary=answers_summary,
        rule_summary=rule_summary,
        missing_data=missing_data,
    )


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

    if request.method == "POST":
        actions = request.form.getlist("action")
        action = actions[0] if actions else ""
        if "back" in actions:
            action = "back"
        if action == "restart":
            session.pop("active_assessment_id", None)
            session.pop("last_answered_symptom_id", None)
            session.pop("finish_snooze", None)
            session.pop("answer_history", None)
            session.pop("back_symptom_id", None)
            return redirect(url_for("web.patient_assessment"))

        if action == "start_assessment":
            assessment = Assessment(user_id=user_id, status="IN_PROGRESS")
            db.session.add(assessment)
            db.session.commit()
            session["active_assessment_id"] = assessment.id
            session.pop("last_answered_symptom_id", None)
            session.pop("finish_snooze", None)
            session.pop("answer_history", None)
            session.pop("back_symptom_id", None)
            return redirect(url_for("web.patient_assessment"))

        assessment = _load_assessment(user_id, False) or _get_or_create_assessment(user_id)
        session["active_assessment_id"] = assessment.id

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
                try:
                    number_val = float(raw)
                except (TypeError, ValueError):
                    session["form_error"] = "Please enter a valid number."
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
            session.pop("finish_snooze", None)
            return redirect(url_for("web.patient_assessment"))

        if action == "finish_now":
            run_diagnosis_now(assessment)
            return redirect(url_for("web.patient_assessment", view="results"))

        if action == "continue_interview":
            session["finish_snooze"] = True
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
            session.pop("finish_snooze", None)
            return redirect(url_for("web.patient_assessment"))

    assessment = _load_assessment(user_id, bool(request.args.get("start")))

    if not assessment:
        return render_template(
            "patient/assessment_core.html",
            view_state="start",
            assessment=None,
            steps=[
                {"key": "start", "label": "Start", "is_current": True, "is_done": False},
                {"key": "interview", "label": "Interview", "is_current": False, "is_done": False},
                {"key": "results", "label": "Results", "is_current": False, "is_done": False},
            ],
        )

    if assessment.status != "IN_PROGRESS" or request.args.get("view") == "results":
        report = build_report(assessment.id)
        answers_summary = _answers_summary(assessment.id)
        rule_summary = _rule_summary(report)
        missing_data = list(rule_summary.get("missing") or [])
        if not missing_data:
            facts = facts_for_assessment(assessment.id)
            parent = Symptom.query.filter_by(code="has_labs").first()
            if parent:
                lab_children = (
                    Symptom.query
                    .filter_by(parent_symptom_id=parent.id, is_active=True)
                    .order_by(Symptom.priority_order.asc(), Symptom.id.asc())
                    .all()
                )
                for lab in lab_children:
                    if lab.code not in facts:
                        missing_data.append(lab.question_text or lab.name or lab.code)
        return render_template(
            "patient/assessment_core.html",
            view_state="results",
            assessment=assessment,
            steps=[
                {"key": "start", "label": "Start", "is_current": False, "is_done": True},
                {"key": "interview", "label": "Interview", "is_current": False, "is_done": True},
                {"key": "results", "label": "Results", "is_current": True, "is_done": False},
            ],
            report=report,
            answers_summary=answers_summary,
            rule_summary=rule_summary,
            missing_data=missing_data,
        )

    inference = get_inference_snapshot(assessment.id)
    offer_finish = bool(inference.get("best_row") and inference.get("finalizable"))
    if offer_finish and not session.get("finish_snooze"):
        return render_template(
            "patient/assessment_core.html",
            view_state="confirm_finish",
            assessment=assessment,
            steps=[
                {"key": "start", "label": "Start", "is_current": False, "is_done": True},
                {"key": "interview", "label": "Interview", "is_current": True, "is_done": False},
                {"key": "results", "label": "Results", "is_current": False, "is_done": False},
            ],
            candidate=inference.get("best_row"),
        )

    back_symptom_id = session.pop("back_symptom_id", None)
    next_symptom = None
    if back_symptom_id:
        next_symptom = Symptom.query.get(back_symptom_id)
    if not next_symptom:
        next_symptom = _next_symptom(assessment.id, session.get("last_answered_symptom_id"))
    if not next_symptom:
        run_diagnosis_now(assessment)
        return redirect(url_for("web.patient_assessment", view="results"))

    error_message = session.pop("form_error", None)

    return render_template(
        "patient/assessment_core.html",
        view_state="question",
        assessment=assessment,
        steps=[
            {"key": "start", "label": "Start", "is_current": False, "is_done": True},
            {"key": "interview", "label": "Interview", "is_current": True, "is_done": False},
            {"key": "results", "label": "Results", "is_current": False, "is_done": False},
        ],
        symptom=next_symptom,
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
