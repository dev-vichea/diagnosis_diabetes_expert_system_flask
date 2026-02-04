from flask import render_template, redirect, url_for, session

from . import web_bp
from .utils import require_login, dashboard_redirect_target


@web_bp.get("/")
def root():
    if session.get("access_token"):
        return redirect(url_for("web.dashboard"))
    return redirect(url_for("web.home"))


@web_bp.get("/home")
def home():
    if session.get("access_token"):
        return redirect(url_for("web.dashboard"))
    return render_template("home.html")


@web_bp.get("/dashboard")
def dashboard():
    guard = require_login()
    if guard:
        return guard
    return redirect(dashboard_redirect_target())

