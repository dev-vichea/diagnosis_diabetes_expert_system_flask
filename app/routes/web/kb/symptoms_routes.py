from flask import jsonify, render_template, request

from app.routes.web import web_bp
from app.routes.web.utils import require_login, require_permissions, wants_json
from app.models import Symptom
from app.services.admin_symptom_service import (
    create_symptom_from_payload,
    delete_symptom,
    list_symptoms_payloads,
    update_symptom_from_payload,
)


@web_bp.get("/knowledge/symptoms")
def kb_symptoms():
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("KB_VIEW")
    if guard:
        return guard
    return render_template("knowledge/symptoms.html", symptoms=list_symptoms_payloads())


@web_bp.get("/knowledge/symptoms/data")
def kb_symptoms_data():
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
    return jsonify({"items": list_symptoms_payloads()})


@web_bp.post("/knowledge/symptoms")
def kb_symptoms_create_submit():
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

    payload, error, status = create_symptom_from_payload(data)
    if error:
        return jsonify({"message": error}), status
    return jsonify({"message": "created", "symptom": payload}), status


@web_bp.put("/knowledge/symptoms/<int:symptom_id>")
def kb_symptoms_update_submit(symptom_id: int):
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

    symptom = Symptom.query.get_or_404(symptom_id)
    data = request.get_json(silent=True) or {}
    payload, error, status = update_symptom_from_payload(symptom, data)
    if error:
        return jsonify({"message": error}), status
    return jsonify({"message": "updated", "symptom": payload}), status


@web_bp.delete("/knowledge/symptoms/<int:symptom_id>")
def kb_symptoms_delete_submit(symptom_id: int):
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

    symptom = Symptom.query.get_or_404(symptom_id)
    deleted, error, status = delete_symptom(symptom)
    if not deleted:
        return jsonify({"message": error or "Failed to delete symptom."}), status
    return jsonify({"message": "deleted"}), 200


@web_bp.get("/knowledge/symptoms/create")
def kb_symptoms_create():
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("KB_CREATE")
    if guard:
        return guard
    return render_template("knowledge/symptoms_create.html", symptoms=list_symptoms_payloads())
