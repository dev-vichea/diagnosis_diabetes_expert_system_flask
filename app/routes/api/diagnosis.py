from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.utils.decorators import require_permission
from app.models import Assessment, DiagnosisRun, Symptom, User

from app.services.assessment_service import (
    finalize_if_ready,
    ensure_fallback_result,
    get_assessment_diagnosis_payload,
    get_diagnosis_detail,
    get_next_symptom,
    get_ranked_candidates,
    submit_answer,
)
from app.services.report_builder import build_report

diagnosis_bp = Blueprint("diagnosis", __name__)


def _current_user_id() -> int:
    return int(get_jwt_identity())


def _ensure_owner_or_perm(assessment: Assessment, permission: str):
    uid = _current_user_id()
    if assessment.user_id == uid:
        return
    from app.services.rbac_service import user_has_permission
    if not user_has_permission(uid, permission):
        return {"message": "forbidden"}, 403
    return None


def _symptom_payload(s: Symptom):
    return {
        "symptom_id": s.id,
        "code": s.code,
        "name": s.name or s.code,
        "question_text": s.question_text,
        "input_type": s.input_type,
        "unit": s.unit,
        "options_json": s.options_json,
        "category": s.category,
        "ui_section": s.ui_section,
        "parent_symptom_id": s.parent_symptom_id,
        "show_if_operator": s.show_if_operator,
        "show_if_value": s.show_if_value,
    }


@diagnosis_bp.post("/start")
@jwt_required()
@require_permission("DIAGNOSIS_START")
def start_assessment():
    uid = _current_user_id()
    if not User.query.get(uid):
        return {"message": "user not found"}, 404

    active = Assessment.query.filter_by(user_id=uid, status="IN_PROGRESS").first()
    if active:
        nxt = get_next_symptom(active)
        if not nxt:
            ensure_fallback_result(active)
            return build_report(active.id), 200
        candidates = get_ranked_candidates(active)
        return {
            "assessment_id": active.id,
            "status": active.status,
            "next_question": _symptom_payload(nxt),
            **candidates,
        }, 200

    a = Assessment(user_id=uid, patient_id=uid, status="IN_PROGRESS")
    db.session.add(a)
    db.session.commit()

    nxt = get_next_symptom(a)
    if not nxt:
        ensure_fallback_result(a)
        return build_report(a.id), 200
    candidates = get_ranked_candidates(a)
    return {
        "assessment_id": a.id,
        "status": a.status,
        "next_question": _symptom_payload(nxt),
        **candidates,
    }, 201


@diagnosis_bp.get("/assessments/<int:assessment_id>/next")
@jwt_required()
@require_permission("DIAGNOSIS_VIEW")
def next_question(assessment_id: int):
    a = Assessment.query.get_or_404(assessment_id)

    forbid = _ensure_owner_or_perm(a, "CASE_VIEW_ALL")
    if forbid:
        return forbid

    if a.status != "IN_PROGRESS":
        return build_report(a.id), 200

    nxt = get_next_symptom(a)
    candidates = get_ranked_candidates(a)
    return {
        "assessment_id": a.id,
        "status": a.status,
        "next_question": _symptom_payload(nxt) if nxt else None,
        **candidates,
    }, 200


@diagnosis_bp.post("/assessments/<int:assessment_id>/answer")
@jwt_required()
@require_permission("DIAGNOSIS_ANSWER")
def answer_question(assessment_id: int):
    a = Assessment.query.get_or_404(assessment_id)

    forbid = _ensure_owner_or_perm(a, "CASE_VIEW_ALL")
    if forbid:
        return forbid

    if a.status != "IN_PROGRESS":
        return {"message": "assessment is locked/completed"}, 409

    data = request.get_json() or {}
    symptom_id = data.get("symptom_id")
    answer_value = data.get("answer")
    answer_type = data.get("answer_type")

    if symptom_id is None:
        return {"message": "symptom_id is required"}, 400

    try:
        symptom_id = int(symptom_id)
    except Exception:
        return {"message": "symptom_id must be int"}, 400

    s = Symptom.query.get(symptom_id)
    if not s or not s.is_active:
        return {"message": "invalid symptom_id"}, 400

    input_type = (answer_type or s.input_type or "BOOLEAN").upper()
    if input_type == "NUMBER":
        try:
            answer_value = float(answer_value)
        except (TypeError, ValueError):
            return {"message": "answer must be a number"}, 400
    elif input_type in {"TEXT", "SINGLE"}:
        if answer_value is None or answer_value == "":
            return {"message": "answer is required"}, 400
        answer_value = str(answer_value)
    else:
        answer_value = bool(answer_value)
        input_type = "BOOLEAN"

    result = submit_answer(a, symptom_id, answer_value, input_type=input_type)
    if result:
        return build_report(a.id), 200

    nxt = get_next_symptom(a)
    if not nxt:
        ensure_fallback_result(a)
        return build_report(a.id), 200
    candidates = get_ranked_candidates(a)

    return {
        "assessment_id": a.id,
        "status": a.status,
        "answered": {"symptom_id": symptom_id, "answer": answer_value, "answer_type": input_type},
        "next_question": _symptom_payload(nxt),
        **candidates,
    }, 200


@diagnosis_bp.get("/assessments/<int:assessment_id>/report")
@jwt_required()
@require_permission("DIAGNOSIS_VIEW")
def report(assessment_id: int):
    a = Assessment.query.get_or_404(assessment_id)

    forbid = _ensure_owner_or_perm(a, "CASE_VIEW_ALL")
    if forbid:
        return forbid

    return build_report(a.id), 200


@diagnosis_bp.get("/assessments/<int:assessment_id>/results")
@jwt_required()
@require_permission("DIAGNOSIS_VIEW")
def assessment_results(assessment_id: int):
    a = Assessment.query.get_or_404(assessment_id)

    forbid = _ensure_owner_or_perm(a, "CASE_VIEW_ALL")
    if forbid:
        return forbid

    payload = get_assessment_diagnosis_payload(a)
    return {
        "assessment_id": a.id,
        "status": a.status,
        **payload,
    }, 200


@diagnosis_bp.get("/assessments/<int:assessment_id>/results/<int:disease_id>")
@jwt_required()
@require_permission("DIAGNOSIS_VIEW")
def assessment_result_details(assessment_id: int, disease_id: int):
    a = Assessment.query.get_or_404(assessment_id)

    forbid = _ensure_owner_or_perm(a, "CASE_VIEW_ALL")
    if forbid:
        return forbid

    detail = get_diagnosis_detail(a, disease_id)
    if not detail:
        return {"message": "candidate not found"}, 404

    return detail, 200


@diagnosis_bp.get("/history")
@jwt_required()
@require_permission("DIAGNOSIS_HISTORY")
def my_history():
    uid = _current_user_id()
    rows = (
        Assessment.query
        .filter_by(user_id=uid)
        .order_by(Assessment.id.desc())
        .limit(50)
        .all()
    )

    items = []
    for a in rows:
        res = (
            DiagnosisRun.query
            .filter_by(assessment_id=a.id)
            .order_by(DiagnosisRun.id.desc())
            .first()
        )
        disease = res.disease if res else None
        items.append({
            "assessment_id": a.id,
            "status": a.status,
            "diagnosis_code": disease.code if disease else None,
            "risk_level": res.risk_level if res else None,
        })

    return {"items": items}, 200
