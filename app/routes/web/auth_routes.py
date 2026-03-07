from flask import render_template, request, redirect, url_for, flash, session, jsonify
import requests

from . import web_bp
from .utils import api_base, wants_json, dashboard_redirect_target
from app.services.audit_service import record_audit_event


@web_bp.get("/login")
def login_page():
    if session.get("access_token"):
        return redirect(url_for("web.dashboard"))
    next_target = request.args.get("next", "")
    return render_template("login.html", next=next_target)


@web_bp.get("/register")
def register_page():
    if session.get("access_token"):
        return redirect(url_for("web.dashboard"))
    return render_template("register.html")


@web_bp.post("/login")
def login_submit():
    payload = request.get_json(silent=True) if request.is_json else None
    form = payload or request.form
    email = form.get("email", "").strip()
    password = form.get("password", "")

    if not email or not password:
        msg = "Please enter email and password."
        if wants_json():
            return jsonify({"ok": False, "message": msg}), 400
        flash(msg, "danger")
        return redirect(url_for("web.login_page"))

    try:
        resp = requests.post(
            api_base() + "/auth/login",
            json={"email": email, "password": password},
            timeout=10,
        )
    except requests.RequestException:
        msg = "API not reachable. Check server is running."
        if wants_json():
            return jsonify({"ok": False, "message": msg}), 502
        flash(msg, "danger")
        return redirect(url_for("web.login_page"))

    if resp.status_code != 200:
        msg = "Invalid credentials."
        try:
            msg = resp.json().get("message", msg)
        except Exception:
            pass
        if wants_json():
            return jsonify({"ok": False, "message": msg}), resp.status_code
        flash(msg, "danger")
        return redirect(url_for("web.login_page"))

    data = resp.json()
    access_token = data.get("access_token") or data.get("token")
    if not access_token:
        msg = "Login succeeded but token missing in response."
        if wants_json():
            return jsonify({"ok": False, "message": msg}), 502
        flash(msg, "danger")
        return redirect(url_for("web.login_page"))

    session["access_token"] = access_token
    session["me"] = {
        "user_id": data.get("user_id"),
        "email": data.get("email"),
    }

    try:
        me = requests.get(
            api_base() + "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        me_data = me.json() if me.status_code == 200 else {}
    except requests.RequestException:
        me_data = {}

    if me_data:
        session["me"].update(me_data)

    # Allow a client-specified `next` target
    requested_next = None
    if isinstance(form, dict):
        requested_next = form.get("next")
    requested_next = requested_next or request.args.get("next")

    safe_next = None
    if requested_next and isinstance(requested_next, str) and requested_next.startswith("/"):
        safe_next = requested_next

    redirect_target = safe_next or dashboard_redirect_target()

    if wants_json():
        return jsonify({"ok": True, "redirect": redirect_target})
    return redirect(redirect_target)


@web_bp.get("/logout")
def logout():
    me = session.get("me") or {}
    user_id = me.get("user_id")
    try:
        actor_user_id = int(user_id)
    except (TypeError, ValueError):
        actor_user_id = None

    if actor_user_id:
        record_audit_event(
            action="LOGOUT",
            entity="AUTH",
            actor_user_id=actor_user_id,
            entity_id=actor_user_id,
            meta={
                "details": "User logged out from web session.",
                "ip": request.headers.get("X-Forwarded-For") or request.remote_addr or "",
                "user_agent": request.headers.get("User-Agent", ""),
            },
        )

    session.clear()
    return redirect(url_for("web.login_page"))
