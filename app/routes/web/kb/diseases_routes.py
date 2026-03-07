from flask import jsonify, render_template, request
from sqlalchemy.exc import IntegrityError

from app.routes.web import web_bp
from app.routes.web.utils import require_login, require_permissions, wants_json
from app.models import Disease
from app.extensions import db
from app.services.admin_disease_service import (
    create_disease_from_payload,
    disease_related_symptoms_payload,
    list_diseases_payloads,
    update_disease_from_payload,
)


@web_bp.get("/knowledge/diseases")
def kb_diseases():
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("KB_VIEW")
    if guard:
        return guard
    return render_template("knowledge/diseases.html", diseases=list_diseases_payloads())


@web_bp.get("/knowledge/diseases/data")
def kb_diseases_data():
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
    return jsonify({"items": list_diseases_payloads()})


@web_bp.get("/knowledge/diseases/<int:disease_id>/related-symptoms")
def kb_disease_related_symptoms(disease_id: int):
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

    disease = Disease.query.get_or_404(disease_id)
    payload = disease_related_symptoms_payload(disease.id)
    return jsonify(payload)


@web_bp.post("/knowledge/diseases")
def kb_diseases_create_submit():
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

    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()

    payload, error, status = create_disease_from_payload(data)
    if error:
        return jsonify({"message": error}), status
    return jsonify({"message": "created", "disease": payload}), status


@web_bp.put("/knowledge/diseases/<int:disease_id>")
def kb_diseases_update_submit(disease_id: int):
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

    disease = Disease.query.get_or_404(disease_id)
    data = request.get_json(silent=True) or {}
    payload, error, status = update_disease_from_payload(disease, data)
    if error:
        return jsonify({"message": error}), status
    return jsonify({"message": "updated", "disease": payload}), status


@web_bp.delete("/knowledge/diseases/<int:disease_id>")
def kb_diseases_delete_submit(disease_id: int):
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

    disease = Disease.query.get_or_404(disease_id)
    try:
        db.session.delete(disease)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Cannot delete disease because it is used by rules or diagnosis history."}), 409

    return jsonify({"message": "deleted"})
