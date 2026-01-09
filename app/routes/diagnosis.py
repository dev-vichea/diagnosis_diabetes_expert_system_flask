from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.utils.decorators import require_permission
from app.models import Assessment, AssessmentAnswer, AssessmentResult, Symptom

from app.services.inference_engine import infer_if_complete, next_question, ensure_fallback_result
from app.services.report_builder import build_report

diagnosis_bp = Blueprint("diagnosis", __name__)


def _current_user_id() -> int:
    return int(get_jwt_identity())


def _ensure_owner_or_perm(assessment: Assessment, permission: str):
    """
    User can only access their own assessments unless they have permission (doctor/admin).
    """
    uid = _current_user_id()
    if assessment.user_id == uid:
        return
    # if not owner, must have permission
    from app.services.rbac_service import user_has_permission
    if not user_has_permission(uid, permission):
        return {"message": "forbidden"}, 403
    return None


def _symptom_payload(s: Symptom):
    return {
        "symptom_id": s.id,
        "code": s.code,
        "question_text": s.question_text,
        "category": s.category,
    }


# -------------------------------------------------------
# 1) Start assessment
# -------------------------------------------------------
@diagnosis_bp.post("/start")
@jwt_required()
@require_permission("DIAGNOSIS_START")
def start_assessment():
    uid = _current_user_id()

    # Optional: allow only one active assessment per user
    active = Assessment.query.filter_by(user_id=uid, status="IN_PROGRESS").first()
    if active:
        # return next question for existing session
        s = next_question(active)
        if not s:
            ensure_fallback_result(active)
            return build_report(active.id), 200
        return {
            "assessment_id": active.id,
            "status": active.status,
            "next_question": _symptom_payload(s) if s else None,
        }, 200

    a = Assessment(user_id=uid, status="IN_PROGRESS")
    db.session.add(a)
    db.session.commit()

    s = next_question(a)
    if not s:
        ensure_fallback_result(a)
        return build_report(a.id), 200
    return {
        "assessment_id": a.id,
        "status": a.status,
        "next_question": _symptom_payload(s) if s else None,
    }, 201


# -------------------------------------------------------
# 2) Get next question (highest priority unanswered)
# -------------------------------------------------------
@diagnosis_bp.get("/assessments/<int:assessment_id>/next")
@jwt_required()
@require_permission("DIAGNOSIS_VIEW")
def get_next_question(assessment_id: int):
    a = Assessment.query.get_or_404(assessment_id)

    forbid = _ensure_owner_or_perm(a, "CASE_VIEW_ALL")
    if forbid:
        return forbid

    if a.status != "IN_PROGRESS":
        # Locked: return report/result not next question
        return build_report(a.id), 200

    s = next_question(a)
    return {
        "assessment_id": a.id,
        "status": a.status,
        "next_question": _symptom_payload(s) if s else None,
    }, 200


# -------------------------------------------------------
# 3) Answer question (prevent duplicate + lock after result)
# -------------------------------------------------------
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
    answer_bool = data.get("answer")

    if symptom_id is None or answer_bool is None:
        return {"message": "symptom_id and answer are required"}, 400

    try:
        symptom_id = int(symptom_id)
    except Exception:
        return {"message": "symptom_id must be int"}, 400

    answer_bool = bool(answer_bool)

    # validate symptom exists & active
    s = Symptom.query.get(symptom_id)
    if not s or not s.is_active:
        return {"message": "invalid symptom_id"}, 400

    # Prevent answering same question twice
    existing = AssessmentAnswer.query.filter_by(assessment_id=a.id, symptom_id=symptom_id).first()
    if existing:
        return {"message": "this symptom is already answered"}, 409

    # Save fact
    ans = AssessmentAnswer(assessment_id=a.id, symptom_id=symptom_id, answer_bool=answer_bool)
    db.session.add(ans)
    db.session.commit()

    # Run inference (may complete assessment)
    result = infer_if_complete(a)

    if result:
        # Locked by inference engine -> return final report
        return build_report(a.id), 200

    # Still in progress -> ask next question
    nxt = next_question(a)
    if not nxt:
        ensure_fallback_result(a)
        return build_report(a.id), 200

    return {
        "assessment_id": a.id,
        "status": a.status,
        "answered": {"symptom_id": s.id, "answer": answer_bool},
        "next_question": _symptom_payload(nxt),
    }, 200


# -------------------------------------------------------
# 4) Get report/result (always works)
# -------------------------------------------------------
@diagnosis_bp.get("/assessments/<int:assessment_id>/report")
@jwt_required()
@require_permission("DIAGNOSIS_VIEW")
def report(assessment_id: int):
    a = Assessment.query.get_or_404(assessment_id)

    forbid = _ensure_owner_or_perm(a, "CASE_VIEW_ALL")
    if forbid:
        return forbid

    return build_report(a.id), 200


# -------------------------------------------------------
# 5) View user history
# -------------------------------------------------------
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
            AssessmentResult.query
            .filter_by(assessment_id=a.id)
            .order_by(AssessmentResult.id.desc())
            .first()
        )
        items.append({
            "assessment_id": a.id,
            "status": a.status,
            "diagnosis_code": res.diagnosis_code if res else None,
            "risk_level": res.risk_level if res else None,
        })

    return {"items": items}, 200


# import json
# from flask import Blueprint, request
# from flask_jwt_extended import jwt_required, get_jwt_identity

# from app.extensions import db
# from app.models import Assessment, AssessmentAnswer, AssessmentResult, Advice, Symptom
# from app.services.inference_engine import infer_if_complete, next_question

# diagnosis_bp = Blueprint("diagnosis", __name__)


# @diagnosis_bp.post("/assessments")
# @jwt_required()
# def start_assessment():
#     user_id = int(get_jwt_identity())

#     assessment = Assessment(user_id=user_id, status="IN_PROGRESS")
#     db.session.add(assessment)
#     db.session.commit()

#     symptom = next_question(assessment)

#     return {
#         "assessment_id": assessment.id,
#         "status": assessment.status,
#         "next_question": (
#             {
#                 "symptom_id": symptom.id,
#                 "code": symptom.code,
#                 "question": symptom.question_text
#             }
#             if symptom else None
#         )
#     }, 201


# @diagnosis_bp.get("/assessments/<int:assessment_id>/next")
# @jwt_required()
# def get_next(assessment_id: int):
#     user_id = int(get_jwt_identity())

#     assessment = Assessment.query.get_or_404(assessment_id)
#     if assessment.user_id != user_id:
#         return {"message": "Forbidden"}, 403

#     # already completed?
#     if assessment.status == "COMPLETED":
#         return _result_payload(assessment_id)

#     # try infer now (in case rules match already)
#     result = infer_if_complete(assessment)
#     if result:
#         return _result_payload(assessment_id)

#     symptom = next_question(assessment)
#     if not symptom:
#         return {"message": "No more questions, but no rule matched."}, 200

#     return {
#         "assessment_id": assessment.id,
#         "status": assessment.status,
#         "next_question": {"symptom_id": symptom.id, "code": symptom.code, "question": symptom.question_text}
#     }


# @diagnosis_bp.post("/assessments/<int:assessment_id>/answer")
# @jwt_required()
# def answer_question(assessment_id: int):
#     user_id = int(get_jwt_identity())
#     assessment = Assessment.query.get_or_404(assessment_id)

#     if assessment.user_id != user_id:
#         return {"message": "Forbidden"}, 403
#     if assessment.status == "COMPLETED":
#         return {"message": "Assessment already completed"}, 400

#     data = request.get_json() or {}
#     symptom_id = data.get("symptom_id")
#     answer = data.get("answer")  # allow True/False or "YES"/"NO"

#     if symptom_id is None or answer is None:
#         return {"message": "symptom_id and answer are required"}, 400

#     # normalize answer
#     if isinstance(answer, str):
#         answer_norm = answer.strip().lower()
#         if answer_norm in ("yes", "y", "true", "1"):
#             answer_bool = True
#         elif answer_norm in ("no", "n", "false", "0"):
#             answer_bool = False
#         else:
#             return {"message": "answer must be YES/NO or true/false"}, 400
#     else:
#         answer_bool = bool(answer)

#     # validate symptom exists + active
#     symptom = Symptom.query.get(symptom_id)
#     if not symptom or not symptom.is_active:
#         return {"message": "Invalid symptom_id"}, 400

#     # upsert: if already answered, update it
#     existing = AssessmentAnswer.query.filter_by(assessment_id=assessment.id, symptom_id=symptom.id).first()
#     if existing:
#         existing.answer_bool = answer_bool
#     else:
#         db.session.add(AssessmentAnswer(assessment_id=assessment.id, symptom_id=symptom.id, answer_bool=answer_bool))
#     db.session.commit()

#     # after each answer, run inference
#     result = infer_if_complete(assessment)
#     if result:
#         return _result_payload(assessment_id)

#     # otherwise return next question
#     nxt = next_question(assessment)
#     return {
#         "assessment_id": assessment.id,
#         "status": assessment.status,
#         "next_question": (
#             {"symptom_id": nxt.id, "code": nxt.code, "question": nxt.question_text}
#             if nxt else None
#         )
#     }


# @diagnosis_bp.get("/assessments/<int:assessment_id>/result")
# @jwt_required()
# def get_result(assessment_id: int):
#     user_id = int(get_jwt_identity())
#     assessment = Assessment.query.get_or_404(assessment_id)
#     if assessment.user_id != user_id:
#         return {"message": "Forbidden"}, 403
#     return _result_payload(assessment_id)


# @diagnosis_bp.get("/history")
# @jwt_required()
# def history():
#     user_id = int(get_jwt_identity())
#     rows = (
#         Assessment.query.filter_by(user_id=user_id)
#         .order_by(Assessment.started_at.desc())
#         .limit(50)
#         .all()
#     )
#     return {
#         "items": [
#             {
#                 "assessment_id": a.id,
#                 "status": a.status,
#                 "started_at": a.started_at.isoformat() if a.started_at else None,
#                 "completed_at": a.completed_at.isoformat() if a.completed_at else None,
#             }
#             for a in rows
#         ]
#     }


# def _result_payload(assessment_id: int):
#     result = AssessmentResult.query.filter_by(assessment_id=assessment_id).first()
#     if not result:
#         return {"message": "No result yet"}, 200

#     advice = None
#     if result.explanation_json:
#         try:
#             exp = json.loads(result.explanation_json)
#             advice_id = exp.get("advice_id")
#             if advice_id:
#                 a = Advice.query.get(advice_id)
#                 if a and a.is_active:
#                     advice = {"title": a.title, "content": a.content, "severity": a.severity}
#         except Exception:
#             pass

#     payload = {
#         "assessment_id": assessment_id,
#         "diagnosis_code": result.diagnosis_code,
#         "risk_level": result.risk_level,
#         "advice": advice,
#         "explanation_json": result.explanation_json,
#     }
#     return payload, 200
