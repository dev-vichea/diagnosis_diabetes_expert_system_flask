from datetime import datetime
from sqlalchemy import UniqueConstraint
from app.extensions import db


class Assessment(db.Model):
    __tablename__ = "tbl_assessments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("tbl_users.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.Enum("IN_PROGRESS", "COMPLETED", name="assessment_status"), default="IN_PROGRESS", nullable=False)

    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)

    user = db.relationship("User", back_populates="assessments")
    facts = db.relationship("CaseFact", back_populates="assessment", cascade="all, delete-orphan")
    runs = db.relationship("DiagnosisRun", back_populates="assessment", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Assessment {self.id} user={self.user_id} status={self.status}>"


class CaseFact(db.Model):
    __tablename__ = "tbl_case_facts"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("tbl_assessments.id", ondelete="CASCADE"), nullable=False)
    symptom_id = db.Column(db.Integer, db.ForeignKey("tbl_symptoms.id", ondelete="RESTRICT"), nullable=False)

    value_bool = db.Column(db.Boolean)
    value_number = db.Column(db.Numeric(10, 3))
    value_text = db.Column(db.String(255))

    confidence = db.Column(db.Numeric(4, 3), default=1.000, nullable=False)
    source = db.Column(db.Enum("USER", "DOCTOR", "SYSTEM", name="fact_source"), default="USER", nullable=False)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    assessment = db.relationship("Assessment", back_populates="facts")
    symptom = db.relationship("Symptom")

    __table_args__ = (
        UniqueConstraint("assessment_id", "symptom_id", name="uq_assessment_symptom"),
    )
