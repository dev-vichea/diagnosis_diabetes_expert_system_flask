from flask import jsonify, render_template, request

from app.routes.web import web_bp
from app.routes.web.utils import require_login, require_permissions, wants_json
from app.extensions import db
from app.models import Advice


def _normalize_recommendations(raw):
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    return None


def _advice_payload(advice: Advice, include_recommendations: bool = False):
    payload = {
        "id": advice.id,
        "diagnosis_code": advice.diagnosis_code,
        "risk_level": advice.risk_level,
        "title": advice.title,
        "content": advice.content,
        "severity": advice.severity,
        "is_active": bool(advice.is_active),
        "created_at": advice.created_at.isoformat() if advice.created_at else None,
    }
    if include_recommendations:
        payload["recommendations"] = advice.recommendations_json
    return payload


@web_bp.get("/knowledge/advices")
def kb_advices():
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("KB_VIEW")
    if guard:
        return guard
    advices = Advice.query.order_by(Advice.diagnosis_code.asc(), Advice.risk_level.asc(), Advice.id.desc()).all()
    return render_template("knowledge/advices.html", advices=[_advice_payload(a) for a in advices])


@web_bp.get("/knowledge/advices/data")
def kb_advices_data():
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("KB_VIEW")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "KB_VIEW"}), 403
        return guard
    advices = Advice.query.order_by(Advice.diagnosis_code.asc(), Advice.risk_level.asc(), Advice.id.desc()).all()
    return jsonify({"items": [_advice_payload(a) for a in advices]})


@web_bp.get("/knowledge/advices/<int:advice_id>")
def kb_advices_detail(advice_id: int):
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("KB_VIEW")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "KB_VIEW"}), 403
        return guard
    advice = Advice.query.get_or_404(advice_id)
    return jsonify(_advice_payload(advice, include_recommendations=True))


@web_bp.post("/knowledge/advices")
def kb_advices_create():
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("KB_CREATE")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "KB_CREATE"}), 403
        return guard

    data = request.get_json(silent=True) or request.form.to_dict()

    diagnosis_code = (data.get("diagnosis_code") or "").strip().upper()
    risk_level = (data.get("risk_level") or "").strip().upper()
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    severity = (data.get("severity") or "INFO").strip().upper()
    is_active = bool(data.get("is_active", True))
    recommendations = _normalize_recommendations(data.get("recommendations"))

    if not diagnosis_code or not risk_level or not title or not content:
        return jsonify({"message": "diagnosis_code, risk_level, title, content are required"}), 400

    exists = Advice.query.filter_by(
        diagnosis_code=diagnosis_code,
        risk_level=risk_level,
        is_active=True,
    ).first()
    if exists:
        return jsonify({
            "message": "active advice already exists for this diagnosis_code + risk_level",
            "existing_advice_id": exists.id
        }), 409

    advice = Advice(
        diagnosis_code=diagnosis_code,
        risk_level=risk_level,
        title=title,
        content=content,
        severity=severity,
        is_active=is_active,
        recommendations_json=recommendations,
    )
    db.session.add(advice)
    db.session.commit()
    return jsonify({"message": "created", "advice": _advice_payload(advice)}), 201


@web_bp.put("/knowledge/advices/<int:advice_id>")
def kb_advices_update(advice_id: int):
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("KB_UPDATE")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "KB_UPDATE"}), 403
        return guard

    advice = Advice.query.get_or_404(advice_id)
    data = request.get_json(silent=True) or {}

    if "diagnosis_code" in data:
        advice.diagnosis_code = (data.get("diagnosis_code") or "").strip().upper()
    if "risk_level" in data:
        advice.risk_level = (data.get("risk_level") or "").strip().upper()
    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify({"message": "title cannot be empty"}), 400
        advice.title = title
    if "content" in data:
        content = (data.get("content") or "").strip()
        if not content:
            return jsonify({"message": "content cannot be empty"}), 400
        advice.content = content
    if "severity" in data:
        advice.severity = (data.get("severity") or "INFO").strip().upper()
    if "is_active" in data:
        advice.is_active = bool(data.get("is_active"))
    if "recommendations" in data:
        advice.recommendations_json = _normalize_recommendations(data.get("recommendations"))

    if advice.is_active:
        dup = Advice.query.filter(
            Advice.id != advice.id,
            Advice.diagnosis_code == advice.diagnosis_code,
            Advice.risk_level == advice.risk_level,
            Advice.is_active == True,
        ).first()
        if dup:
            return jsonify({
                "message": "another active advice already exists for this diagnosis_code + risk_level",
                "existing_advice_id": dup.id
            }), 409

    db.session.commit()
    return jsonify({"message": "updated", "advice": _advice_payload(advice)})


@web_bp.delete("/knowledge/advices/<int:advice_id>")
def kb_advices_delete(advice_id: int):
    guard = require_login()
    if guard:
        if wants_json():
            return jsonify({"message": "Unauthorized"}), 401
        return guard
    guard = require_permissions("KB_DELETE")
    if guard:
        if wants_json():
            return jsonify({"message": "Forbidden", "missing_permission": "KB_DELETE"}), 403
        return guard

    advice = Advice.query.get_or_404(advice_id)
    db.session.delete(advice)
    db.session.commit()
    return jsonify({"message": "deleted"})
