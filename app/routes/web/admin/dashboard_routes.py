from flask import render_template

from app.routes.web import web_bp
from app.routes.web.utils import require_login


@web_bp.get("/admin/dashboard")
def admin_dashboard():
    guard = require_login()
    if guard:
        return guard
    return render_template("admin/dashboard.html")
