from datetime import datetime
from sqlalchemy import Index
from app.extensions import db


class Advice(db.Model):
    __tablename__ = "tbl_advices"

    id = db.Column(db.Integer, primary_key=True)

    diagnosis_code = db.Column(db.String(80), nullable=False)
    risk_level = db.Column(db.String(30), nullable=False)

    title = db.Column(db.String(160), nullable=False)
    content = db.Column(db.Text, nullable=False)

    severity = db.Column(db.String(20), default="INFO", nullable=False)  # INFO, WARNING, ALERT
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_advices_code_risk", "diagnosis_code", "risk_level"),
    )
