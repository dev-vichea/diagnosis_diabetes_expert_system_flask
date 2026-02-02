from datetime import datetime
from sqlalchemy import Index
from app.extensions import db


class Disease(db.Model):
    __tablename__ = "tbl_diseases"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    urgency = db.Column(db.Enum("LOW", "MEDIUM", "HIGH", name="disease_urgency"), default="LOW", nullable=False)
    advice = db.Column(db.Text)
    recommendations_json = db.Column(db.JSON)
    severity = db.Column(db.Enum("INFO", "WARN", "DANGER", name="disease_severity"), default="INFO", nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Disease {self.code}>"


class DiagnosisRun(db.Model):
    __tablename__ = "tbl_diagnosis_runs"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("tbl_assessments.id", ondelete="CASCADE"), nullable=False)
    disease_id = db.Column(db.Integer, db.ForeignKey("tbl_diseases.id", ondelete="RESTRICT"), nullable=False)

    risk_level = db.Column(db.Enum("LOW", "MEDIUM", "HIGH", name="diagnosis_risk_level"))
    confidence = db.Column(db.Numeric(4, 3))
    trace_json = db.Column(db.JSON, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    assessment = db.relationship("Assessment", back_populates="runs")
    disease = db.relationship("Disease")

    __table_args__ = (
        Index("ix_runs_assessment", "assessment_id"),
        Index("ix_runs_disease", "disease_id"),
    )

    def __repr__(self) -> str:
        return f"<DiagnosisRun {self.id} disease={self.disease_id}>"
