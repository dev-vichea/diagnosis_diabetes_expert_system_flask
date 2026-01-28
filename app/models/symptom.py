from datetime import datetime
from sqlalchemy.orm import relationship
from app.extensions import db


class Symptom(db.Model):
    __tablename__ = "tbl_symptoms"


    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False)  # polyuria, polydipsia...
    name = db.Column(db.String(160))
    question_text = db.Column(db.String(255), nullable=False)
    input_type = db.Column(db.String(20), default="BOOLEAN", nullable=False)
    unit = db.Column(db.String(40))
    options_json = db.Column(db.JSON)
    is_derived = db.Column(db.Boolean, default=False, nullable=False)
    category = db.Column(db.String(80))

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    priority_order = db.Column(db.Integer, default=0, nullable=False)
    info_yes = db.Column(db.Text)   # explanation shown when answer is YES
    info_no = db.Column(db.Text)    # optional: explanation when answer is NO
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    # created_at = db.Column(
    #     db.TIMESTAMP,
    #     server_default=text("CURRENT_TIMESTAMP"),
    #     nullable=False
    # )

    rule_conditions = relationship("RuleCondition", back_populates="symptom", cascade="all, delete-orphan")
    answers = relationship("AssessmentAnswer", back_populates="symptom")

    def __repr__(self) -> str:
        return f"<Symptom {self.code}>"
