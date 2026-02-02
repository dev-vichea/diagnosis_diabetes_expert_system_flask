import os

from flask import Flask, send_from_directory, session
from .config import Config
from .extensions import db, migrate, jwt
from app.routes.web import web_bp



def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URL is required (set it in .env).")

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    app.register_blueprint(web_bp) # homepage "/"

    # Import models AFTER db is ready (prevents circular import)
    from app import models  # noqa: F401

    # Register API blueprints
    from .routes.api.auth import auth_bp
    from .routes.api.admin_kb import admin_kb_bp
    from .routes.api.diagnosis import diagnosis_bp
    from .routes.api.admin_users import admin_users_bp
    from .routes.api.admin_rbac import admin_rbac_bp
    from .routes.api.kb import kb_bp
    from .routes.api.kb_rules import kb_rules_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(admin_kb_bp, url_prefix="/api/admin/kb")
    app.register_blueprint(admin_users_bp, url_prefix="/api/admin")
    app.register_blueprint(admin_rbac_bp, url_prefix="/api/admin")
    app.register_blueprint(diagnosis_bp, url_prefix="/api/diagnosis")
    app.register_blueprint(kb_bp, url_prefix="/api/kb")
    app.register_blueprint(kb_rules_bp, url_prefix="/api/kb")

    @app.context_processor
    def inject_rbac():
        session_me = session.get("me") or {}
        perms = set((session_me.get("permissions")) or [])
        roles = set((session_me.get("roles")) or [])
        role = session_me.get("role")
        if role:
            roles.add(role)

        def has_perm(code: str) -> bool:
            return code in perms

        def has_role(name: str) -> bool:
            return name in roles

        return {
            "has_perm": has_perm,
            "has_role": has_role,
            "current_permissions": sorted(perms),
            "current_roles": sorted(roles),
            "current_user_id": (session.get("me") or {}).get("user_id"),
        }

    metis_assets_root = os.path.join(app.static_folder, "metis", "assets")

    @app.get("/assets/<path:filename>")
    def metis_assets(filename: str):
        return send_from_directory(metis_assets_root, filename)


    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
