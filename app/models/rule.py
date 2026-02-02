from datetime import datetime
from sqlalchemy import UniqueConstraint
from app.extensions import db


class Rule(db.Model):
    __tablename__ = "tbl_rules"

    id = db.Column(db.Integer, primary_key=True)
    rule_code = db.Column(db.String(80), unique=True, nullable=False)
    title = db.Column(db.String(160), nullable=False)

    priority = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    explanation_text = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    conditions = db.relationship("RuleCondition", back_populates="rule", cascade="all, delete-orphan")
    actions = db.relationship("RuleAction", back_populates="rule", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Rule {self.rule_code}>"


class RuleCondition(db.Model):
    __tablename__ = "tbl_rule_conditions"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("tbl_rules.id", ondelete="CASCADE"), nullable=False)
    symptom_id = db.Column(db.Integer, db.ForeignKey("tbl_symptoms.id", ondelete="RESTRICT"), nullable=False)

    operator = db.Column(
        db.Enum("PRESENT", "ABSENT", "==", "!=", ">=", "<=", ">", "<", name="rule_operator"),
        nullable=False,
    )
    value = db.Column(db.String(120))
    weight = db.Column(db.Numeric(6, 3), default=1.000, nullable=False)
    is_required = db.Column(db.Boolean, default=True, nullable=False)
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
        UniqueConstraint("rule_id", "disease_id", name="uq_rule_disease"),
    )
