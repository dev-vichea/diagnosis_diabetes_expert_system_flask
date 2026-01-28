from datetime import datetime
from sqlalchemy.orm import relationship
from app.extensions import db

class AssessmentMetric(db.Model):
    __tablename__ = "tbl_assessment_metrics"

    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(
        db.Integer,
        db.ForeignKey("tbl_assessments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False
    )

    height_cm = db.Column(db.Float)
    weight_kg = db.Column(db.Float)
    age_years = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)