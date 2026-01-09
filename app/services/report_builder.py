import json
from app.models import (
    AssessmentAnswer, Symptom,
    AssessmentResult, Rule, Advice
)

def build_report(assessment_id: int):
    # facts (answers)
    answers = AssessmentAnswer.query.filter_by(assessment_id=assessment_id).all()
    symptom_ids = [a.symptom_id for a in answers]
    symptoms = {s.id: s for s in Symptom.query.filter(Symptom.id.in_(symptom_ids)).all()} if symptom_ids else {}

    yes_list, no_list = [], []
    facts = {}

    for a in answers:
        facts[a.symptom_id] = bool(a.answer_bool)
        s = symptoms.get(a.symptom_id)
        label = getattr(s, "label", None) or (s.question_text if s else f"symptom#{a.symptom_id}")
        if a.answer_bool:
            yes_list.append(label)
        else:
            no_list.append(label)

    # result
    result = AssessmentResult.query.filter_by(assessment_id=assessment_id).order_by(AssessmentResult.id.desc()).first()
    if not result:
        return {"assessment_id": assessment_id, "status": "IN_PROGRESS", "next_question": None}

    exp = {}
    if result.explanation_json:
        try:
            exp = json.loads(result.explanation_json)
        except Exception:
            exp = {}

    fired_rule_id = exp.get("fired_rule_id")
    reasoning = []

    if fired_rule_id:
        rule = Rule.query.get(fired_rule_id)
        if rule:
            # if you added explanation_text to Rule model
            rule_explain = getattr(rule, "explanation_text", None)
            if rule_explain:
                reasoning.append(rule_explain)

            # collect condition reason_text if available
            for c in rule.conditions:
                rt = getattr(c, "reason_text", None)
                if rt:
                    reasoning.append(rt)

            # fallback if none
            if not reasoning:
                reasoning = [f"Rule fired: {rule.name} (priority {rule.priority})"]

    # advice
    advice_obj = Advice.query.filter_by(
        is_active=True,
        diagnosis_code=result.diagnosis_code,
        risk_level=result.risk_level
    ).first()

    advice = None
    if advice_obj:
        advice = {
            "title": advice_obj.title,
            "content": advice_obj.content,
            "severity": advice_obj.severity,
        }

    return {
        "assessment_id": assessment_id,
        "key_symptoms": {
            "yes": yes_list,
            "no": no_list,
        },
        "risk_assessment": {
            "diagnosis_code": result.diagnosis_code,
            "risk_level": result.risk_level,
        },
        "reasoning": reasoning,
        "advice": advice,
    }
