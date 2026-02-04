from flask import request, session, redirect, url_for

from app.services.rbac_service import get_user_permission_codes
from app.models import User


def api_base() -> str:
    return request.host_url.rstrip("/") + "/api"


def wants_json() -> bool:
    return (
        request.is_json
        or request.headers.get("X-Requested-With") == "fetch"
        or "application/json" in request.headers.get("Accept", "")
    )


def current_permissions() -> set:
    me = session.get("me") or {}
    perms = set((me.get("permissions")) or [])
    if perms:
        return perms

    user_id = me.get("user_id")
    if user_id:
        try:
            return set(get_user_permission_codes(int(user_id)))
        except Exception:
            return set()

    return set()


def current_roles() -> set:
    me = session.get("me") or {}
    roles = set((me.get("roles")) or [])
    role = me.get("role")
    if role:
        roles.add(role)
    if roles:
        return roles

    user_id = me.get("user_id")
    if user_id:
        try:
            user = User.query.get(int(user_id))
            if user:
                return {r.name for r in user.roles}
        except Exception:
            return set()
    return roles


def require_login():
    if not session.get("access_token"):
        return redirect(url_for("web.login_page", next=request.path))

    me = session.get("me") or {}
    user_id = me.get("user_id")
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        session.clear()
        return redirect(url_for("web.login_page", next=request.path))

    if not User.query.get(user_id):
        session.clear()
        return redirect(url_for("web.login_page", next=request.path))
    return None


def require_permissions(*codes: str):
    if not codes:
        return None
    if "ADMIN" in current_roles():
        return None
    perms = current_permissions()
    if any(code in perms for code in codes):
        return None
    return redirect(url_for("web.dashboard"))


def dashboard_redirect_target() -> str:
    if "ADMIN" in current_roles():
        return url_for("web.admin_dashboard")
    perms = current_permissions()
    if "USER_VIEW" in perms:
        return url_for("web.admin_users")
    if "RBAC_VIEW" in perms:
        return url_for("web.admin_roles")
    if "KB_VIEW" in perms:
        return url_for("web.kb_symptoms")
    if perms.intersection({"DIAGNOSIS_VIEW", "DIAGNOSIS_START", "DIAGNOSIS_ANSWER"}):
        return url_for("web.patient_diagnosis")
    return url_for("web.patient_diagnosis")
