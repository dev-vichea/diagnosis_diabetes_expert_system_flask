from datetime import datetime
from sqlalchemy import Index
from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = "tbl_audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("tbl_users.id", ondelete="SET NULL"))

    action = db.Column(db.String(120), nullable=False)  # CREATE_RULE, START_ASSESSMENT...
    entity = db.Column(db.String(120), nullable=False)  # tbl_rules, tbl_symptoms...
    entity_id = db.Column(db.Integer)

    meta_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_audit_actor", "actor_user_id"),
        Index("ix_audit_action", "action"),
    )
