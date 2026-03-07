from datetime import datetime
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import synonym
from app.extensions import db


class Assessment(db.Model):
    __tablename__ = "tbl_assessments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("tbl_users.id", ondelete="CASCADE"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("tbl_users.id", ondelete="SET NULL"), nullable=True)
    status = db.Column(db.Enum("IN_PROGRESS", "COMPLETED", name="assessment_status"), default="IN_PROGRESS", nullable=False)

    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)
    engine_version = db.Column(db.String(40))

    user = db.relationship("User", back_populates="assessments", foreign_keys=[user_id])
    facts = db.relationship("CaseFact", back_populates="assessment", cascade="all, delete-orphan")
    runs = db.relationship("DiagnosisRun", back_populates="assessment", cascade="all, delete-orphan")
    rule_results = db.relationship(
        "AssessmentRuleResult",
        back_populates="assessment",
        cascade="all, delete-orphan",
    )
    diagnosis_results = db.relationship(
        "AssessmentDiagnosisResult",
        back_populates="assessment",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Assessment {self.id} user={self.user_id} status={self.status}>"


class CaseFact(db.Model):
    __tablename__ = "tbl_case_facts"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("tbl_assessments.id", ondelete="CASCADE"), nullable=False)
    symptom_id = db.Column(db.Integer, db.ForeignKey("tbl_symptoms.id", ondelete="RESTRICT"), nullable=False)
    finding_code = db.Column(db.String(80))

    value_bool = db.Column(db.Boolean)
    value_number = db.Column(db.Numeric(10, 3))
    value_text = db.Column(db.String(255))
    value_json = db.Column(db.JSON)
    state = db.Column(
        db.Enum("true", "false", "unknown", name="assessment_answer_state"),
        default="unknown",
        nullable=False,
    )
    is_provided = db.Column(db.Boolean, default=False, nullable=False)

    confidence = db.Column(db.Numeric(4, 3), default=1.000, nullable=False)
    source = db.Column(db.Enum("USER", "DOCTOR", "SYSTEM", name="fact_source"), default="USER", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    answered_at = synonym("created_at")

    assessment = db.relationship("Assessment", back_populates="facts")
    symptom = db.relationship("Symptom")

    __table_args__ = (
        UniqueConstraint("assessment_id", "symptom_id", name="uq_assessment_symptom"),
    )
