from flask import Flask
from .config import Config
from .extensions import db, migrate, jwt


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # Import models AFTER db is ready (prevents circular import)
    from app import models  # noqa: F401

    # Register blueprints
    from .routes.auth import auth_bp
    from .routes.admin_kb import admin_kb_bp
    from .routes.diagnosis import diagnosis_bp
    from .routes.admin_users import admin_users_bp
    from .routes.kb import kb_bp
    from .routes.kb_rules import kb_rules_bp
    from .routes.kb_advices import kb_advices_bp



    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(admin_kb_bp, url_prefix="/api/admin/kb")
    app.register_blueprint(admin_users_bp, url_prefix="/api/admin")
    app.register_blueprint(diagnosis_bp, url_prefix="/api/diagnosis")
    app.register_blueprint(kb_bp, url_prefix="/api/kb")
    app.register_blueprint(kb_rules_bp, url_prefix="/api/kb")
    app.register_blueprint(kb_advices_bp, url_prefix="/api/kb")



    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
