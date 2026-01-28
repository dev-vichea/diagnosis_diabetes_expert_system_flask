from flask import render_template

from app.routes.web import web_bp
from app.routes.web.utils import require_login, require_permissions


@web_bp.get("/knowledge/questions")
def kb_questions():
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("KB_VIEW")
    if guard:
        return guard
    return render_template("knowledge/questions.html")


@web_bp.get("/knowledge/questions/create")
def kb_questions_create():
    guard = require_login()
    if guard:
        return guard
    guard = require_permissions("KB_CREATE")
    if guard:
        return guard
    return render_template("knowledge/questions_create.html")
