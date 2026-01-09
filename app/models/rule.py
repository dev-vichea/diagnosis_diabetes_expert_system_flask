from datetime import datetime
from sqlalchemy import UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.extensions import db


class Rule(db.Model):
    __tablename__ = "tbl_rules"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)

    diagnosis_code = db.Column(db.String(80), nullable=False)  # TYPE1, TYPE2, DIABETES_RISK...
    risk_level = db.Column(db.String(30), nullable=False)      # LOW, MODERATE, HIGH

    priority = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    conditions = relationship("RuleCondition", back_populates="rule", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Rule {self.id} {self.name}>"


class RuleCondition(db.Model):
    __tablename__ = "tbl_rule_conditions"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("tbl_rules.id", ondelete="CASCADE"), nullable=False)
    symptom_id = db.Column(db.Integer, db.ForeignKey("tbl_symptoms.id", ondelete="CASCADE"), nullable=False)
    expected_value = db.Column(db.Boolean, nullable=False)  # True=YES, False=NO

    rule = relationship("Rule", back_populates="conditions")
    symptom = relationship("Symptom", back_populates="rule_conditions")

    explanation_text = db.Column(db.Text)

    __table_args__ = (
        UniqueConstraint("rule_id", "symptom_id", name="uq_rule_symptom"),
        Index("ix_rule_conditions_rule_id", "rule_id"),
        Index("ix_rule_conditions_symptom_id", "symptom_id"),
    )
