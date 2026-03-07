from datetime import datetime
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import synonym
from app.extensions import db


class RuleSet(db.Model):
    __tablename__ = "tbl_rule_sets"

    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.Integer, nullable=False, unique=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    released_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)

    rules = db.relationship("Rule", back_populates="rule_set")

    def __repr__(self) -> str:
        return f"<RuleSet v{self.version} active={self.active}>"


class Rule(db.Model):
    __tablename__ = "tbl_rules"

    id = db.Column(db.Integer, primary_key=True)
    rule_code = db.Column(db.String(80), unique=True, nullable=False)
    title = db.Column(db.String(160), nullable=False)
    rule_type = db.Column(db.String(20), nullable=False, default="screening", server_default="screening")
    version = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    rule_set_id = db.Column(db.Integer, db.ForeignKey("tbl_rule_sets.id", ondelete="SET NULL"), nullable=True, index=True)
    disease_id = db.Column(db.Integer, db.ForeignKey("tbl_diseases.id", ondelete="RESTRICT"), nullable=True, index=True)
    base_confidence = db.Column(db.Numeric(4, 3), default=0.500, nullable=False, server_default="0.500")
    max_conf_without_labs = db.Column(db.Numeric(4, 3), nullable=True)
    confidence_cap_if_unconfirmed = synonym("max_conf_without_labs")
    confidence_bonus_max = db.Column(db.Numeric(4, 3), nullable=True)
    min_required_matches = db.Column(db.Integer, nullable=True)
    stop_engine_on_match = db.Column(db.Boolean, default=False, nullable=False, server_default=db.text("0"))
    stop_on_match = synonym("stop_engine_on_match")
    risk_level = db.Column(db.Enum("LOW", "MEDIUM", "HIGH", name="rule_risk_level"), default="LOW", nullable=True)

    priority = db.Column(db.Integer, default=0, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    is_active = synonym("active")
    patient_summary_template = db.Column(db.Text)
    doctor_response_template = db.Column(db.Text)
    advice_template = db.Column(db.Text)
    explanation_text = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    conditions = db.relationship("RuleCondition", back_populates="rule", cascade="all, delete-orphan")
    actions = db.relationship("RuleAction", back_populates="rule", cascade="all, delete-orphan")
    disease = db.relationship("Disease")
    rule_set = db.relationship("RuleSet", back_populates="rules")

    def __repr__(self) -> str:
        return f"<Rule {self.rule_code}>"


class RuleCondition(db.Model):
    __tablename__ = "tbl_rule_conditions"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("tbl_rules.id", ondelete="CASCADE"), nullable=False)
    symptom_id = db.Column(db.Integer, db.ForeignKey("tbl_symptoms.id", ondelete="RESTRICT"), nullable=False)
    finding_code = db.Column(db.String(80))

    operator = db.Column(
        db.Enum(
            "PRESENT",
            "ABSENT",
            "==",
            "!=",
            ">=",
            "<=",
            ">",
            "<",
            "EQ",
            "GTE",
            "BETWEEN",
            "IN",
            name="rule_operator",
        ),
        nullable=False,
    )
    value = db.Column(db.String(120))
    values_json = db.Column(db.JSON)
    score_points = db.Column(db.Integer, default=0, nullable=False)
    weight = db.Column(db.Numeric(6, 3), default=1.000, nullable=False)
    is_required = db.Column(db.Boolean, default=True, nullable=False)
    negate = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    rule = db.relationship("Rule", back_populates="conditions")
    symptom = db.relationship("Symptom")

    __table_args__ = (
        UniqueConstraint("rule_id", "symptom_id", name="uq_rule_symptom"),
    )


class RuleAction(db.Model):
    __tablename__ = "tbl_rule_actions"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("tbl_rules.id", ondelete="CASCADE"), nullable=False)
    disease_id = db.Column(db.Integer, db.ForeignKey("tbl_diseases.id", ondelete="RESTRICT"), nullable=False)

    confidence = db.Column(db.Numeric(4, 3), default=0.500, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    rule = db.relationship("Rule", back_populates="actions")
    disease = db.relationship("Disease")

    __table_args__ = (
        UniqueConstraint("rule_id", name="uq_rule_single_disease"),
        UniqueConstraint("rule_id", "disease_id", name="uq_rule_disease"),
    )
