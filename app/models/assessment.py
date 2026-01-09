from datetime import datetime
from sqlalchemy import UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.extensions import db


class Assessment(db.Model):
    __tablename__ = "tbl_assessments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("tbl_users.id", ondelete="CASCADE"), nullable=False)

    status = db.Column(db.String(20), default="IN_PROGRESS", nullable=False)  # IN_PROGRESS, COMPLETED
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)

    user = relationship("User", back_populates="assessments")
    answers = relationship("AssessmentAnswer", back_populates="assessment", cascade="all, delete-orphan")
    result = relationship("AssessmentResult", back_populates="assessment", uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Assessment {self.id} user={self.user_id} status={self.status}>"


class AssessmentAnswer(db.Model):
    __tablename__ = "tbl_assessment_answers"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("tbl_assessments.id", ondelete="CASCADE"), nullable=False)
    symptom_id = db.Column(db.Integer, db.ForeignKey("tbl_symptoms.id", ondelete="RESTRICT"), nullable=False)

    answer_bool = db.Column(db.Boolean, nullable=False)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    assessment = relationship("Assessment", back_populates="answers")
    symptom = relationship("Symptom", back_populates="answers")

    __table_args__ = (
        UniqueConstraint("assessment_id", "symptom_id", name="uq_assessment_symptom"),
        Index("ix_answers_assessment_id", "assessment_id"),
    )


class AssessmentResult(db.Model):
    __tablename__ = "tbl_assessment_results"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_assessments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    diagnosis_code = db.Column(db.String(80), nullable=False)
    risk_level = db.Column(db.String(30), nullable=False)

    explanation_json = db.Column(db.Text)  # fired rule + matched conditions + facts
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    assessment = relationship("Assessment", back_populates="result")

    __table_args__ = (
        Index("ix_results_assessment_id", "assessment_id"),
    )
