from datetime import datetime, timezone
from pydoc import text
from sqlalchemy.orm import relationship
from app.extensions import db


class Symptom(db.Model):
    __tablename__ = "tbl_symptoms"


    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False)  # polyuria, polydipsia...
    question_text = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(80))

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    priority_order = db.Column(db.Integer, default=0, nullable=False)
    info_yes = db.Column(db.Text)   # explanation shown when answer is YES
    info_no = db.Column(db.Text)    # optional: explanation when answer is NO
    created_at = db.Column(
        db.DateTime,
        default= datetime.now,
        nullable=False
    )

    # created_at = db.Column(
    #     db.TIMESTAMP,
    #     server_default=text("CURRENT_TIMESTAMP"),
    #     nullable=False
    # )

    rule_conditions = relationship("RuleCondition", back_populates="symptom", cascade="all, delete-orphan")
    answers = relationship("AssessmentAnswer", back_populates="symptom")

    def __repr__(self) -> str:
        return f"<Symptom {self.code}>"
