from datetime import datetime
from app.extensions import db


class Symptom(db.Model):
    __tablename__ = "tbl_symptoms"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    question_text = db.Column(db.String(255), nullable=False)

    input_type = db.Column(db.Enum("BOOLEAN", "NUMBER", "TEXT", "SINGLE", name="symptom_input_type"), nullable=False)
    unit = db.Column(db.String(40))
    options_json = db.Column(db.JSON)

    category = db.Column(db.String(80))
    ui_section = db.Column(db.String(80))

    parent_symptom_id = db.Column(db.Integer, db.ForeignKey("tbl_symptoms.id", ondelete="SET NULL"))
    show_if_operator = db.Column(
        db.Enum("==", "!=", ">", "<", ">=", "<=", "PRESENT", "ABSENT", name="symptom_show_if_operator")
    )
    show_if_value = db.Column(db.String(120))

    priority_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    parent = db.relationship("Symptom", remote_side=[id])

    def __repr__(self) -> str:
        return f"<Symptom {self.code}>"
