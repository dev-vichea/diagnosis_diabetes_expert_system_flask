from datetime import datetime
from sqlalchemy import Index
from sqlalchemy.orm import synonym, validates
from app.extensions import db


class Disease(db.Model):
    __tablename__ = "tbl_diseases"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(
        db.Enum("type1", "type2", "prediabetes", "gestational", "other", name="disease_category"),
        default="other",
        nullable=False,
    )
    severity_level = db.Column(
        db.Enum("low", "medium", "high", name="disease_severity_level"),
        default="low",
        nullable=False,
    )
    default_recommendation = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @validates("severity_level")
    def _normalize_severity_level(self, _key, value):
        text = str(value or "low").strip().lower()
        if text == "urgent":
            return "high"
        if text not in {"low", "medium", "high"}:
            return "low"
        return text

    @validates("category")
    def _normalize_category(self, _key, value):
        text = str(value or "other").strip().lower()
        if text in {"t1dm", "type1dm", "type 1", "type-1", "type_1"}:
            return "type1"
        if text in {"t2dm", "type2dm", "type 2", "type-2", "type_2", "diabetes"}:
            return "type2"
        if text in {"predm", "pre-diabetes", "pre_diabetes"}:
            return "prediabetes"
        if text in {"gdm", "pregnancy"}:
            return "gestational"
        if text not in {"type1", "type2", "prediabetes", "gestational", "other"}:
            return "other"
        return text

    @property
    def is_active(self):
        return self.active

    @is_active.setter
    def is_active(self, value):
        self.active = bool(value)

    @property
    def default_next_steps(self):
        return self.default_recommendation

    @default_next_steps.setter
    def default_next_steps(self, value):
        self.default_recommendation = value

    @property
    def patient_label_screening(self):
        return f"Possible {self.name} (screening)" if self.name else None

    @patient_label_screening.setter
    def patient_label_screening(self, _value):
        return None

    @property
    def patient_label_confirmed(self):
        return self.name

    @patient_label_confirmed.setter
    def patient_label_confirmed(self, _value):
        return None

    @property
    def red_flag_message(self):
        return None

    @red_flag_message.setter
    def red_flag_message(self, _value):
        return None

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
    facts_json = db.Column(db.JSON)
    engine_version = db.Column(db.String(40))
    final_message = db.Column(db.String(255))

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    assessment = db.relationship("Assessment", back_populates="runs")
    disease = db.relationship("Disease")

    __table_args__ = (
        Index("ix_runs_assessment", "assessment_id"),
        Index("ix_runs_disease", "disease_id"),
    )

    def __repr__(self) -> str:
        return f"<DiagnosisRun {self.id} disease={self.disease_id}>"


class AssessmentRuleResult(db.Model):
    __tablename__ = "tbl_assessment_rule_results"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("tbl_assessments.id", ondelete="CASCADE"), nullable=False)
    rule_id = db.Column(db.Integer, db.ForeignKey("tbl_rules.id", ondelete="RESTRICT"), nullable=False)

    matched_state = db.Column(
        db.Enum("match", "no_match", "unknown", name="assessment_rule_match_state"),
        default="unknown",
        nullable=False,
    )
    score_added = db.Column(db.Integer, default=0, nullable=False)
    confidence_added = db.Column(db.Numeric(6, 3), default=0.000, nullable=False)
    missing_findings_json = db.Column(db.JSON)
    explain_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    assessment = db.relationship("Assessment", back_populates="rule_results")
    rule = db.relationship("Rule")

    __table_args__ = (
        db.UniqueConstraint("assessment_id", "rule_id", name="uq_assessment_rule_result"),
        Index("ix_assessment_rule_results_assessment", "assessment_id"),
        Index("ix_assessment_rule_results_rule", "rule_id"),
    )

    def __repr__(self) -> str:
        return f"<AssessmentRuleResult assessment={self.assessment_id} rule={self.rule_id} state={self.matched_state}>"


class AssessmentDiagnosisResult(db.Model):
    __tablename__ = "tbl_assessment_diagnosis_results"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("tbl_assessments.id", ondelete="CASCADE"), nullable=False)
    disease_id = db.Column(db.Integer, db.ForeignKey("tbl_diseases.id", ondelete="RESTRICT"), nullable=False)

    score_total = db.Column(db.Integer, nullable=False)
    score = synonym("score_total")
    confidence = db.Column(db.Numeric(4, 3), nullable=False)
    status = db.Column(
        db.Enum("confirmed", "high", "possible", "unlikely", name="diagnosis_result_status"),
        nullable=True,
    )
    confirmed_by_rule_id = db.Column(db.Integer, db.ForeignKey("tbl_rules.id", ondelete="SET NULL"), nullable=True)
    evidence_level = db.Column(
        db.Enum("HIGH", "MODERATE", "LOW", name="diagnosis_evidence_level"),
        nullable=False,
    )
    risk_level = db.Column(
        db.Enum("LOW", "MEDIUM", "HIGH", name="diagnosis_candidate_risk_level"),
        nullable=False,
    )
    top_evidence_json = db.Column(db.JSON, nullable=False)
    trace_json = synonym("top_evidence_json")
    missing_key_facts_json = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    assessment = db.relationship("Assessment", back_populates="diagnosis_results")
    disease = db.relationship("Disease")
    confirmed_by_rule = db.relationship("Rule")

    __table_args__ = (
        Index("ix_assessment_diag_results_assessment", "assessment_id"),
        Index("ix_assessment_diag_results_disease", "disease_id"),
        Index("ix_assessment_diag_results_evidence", "evidence_level"),
        db.UniqueConstraint("assessment_id", "disease_id", name="uq_assessment_diagnosis_disease"),
    )

    def __repr__(self) -> str:
        return f"<AssessmentDiagnosisResult assessment={self.assessment_id} disease={self.disease_id}>"
