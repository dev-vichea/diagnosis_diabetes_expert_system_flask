from typing import Dict
from app.models import AssessmentAnswer, AssessmentMetric, Symptom
from app.extensions import db
from app.inference.bmi import calculate_bmi, bmi_to_overweight

def facts_for_assessment(assessment_id: int) -> Dict[int, bool]:
    rows = AssessmentAnswer.query.filter_by(assessment_id=assessment_id).all()
    facts = {r.symptom_id: bool(r.answer_bool) for r in rows}

    # Derived facts from metrics → store as boolean symptom answer
    metric = AssessmentMetric.query.filter_by(assessment_id=assessment_id).first()
    if metric and metric.height_cm and metric.weight_kg:
        bmi = calculate_bmi(metric.weight_kg, metric.height_cm)
        overweight = bmi_to_overweight(bmi)

        s_over = Symptom.query.filter_by(code="overweight").first()
        if s_over:
            # ensure consistent: persist derived boolean as an answer
            existing = AssessmentAnswer.query.filter_by(
                assessment_id=assessment_id, symptom_id=s_over.id
            ).first()
            if not existing:
                db.session.add(AssessmentAnswer(
                    assessment_id=assessment_id,
                    symptom_id=s_over.id,
                    answer_bool=overweight
                ))
                db.session.commit()
            facts[s_over.id] = overweight

    return facts
