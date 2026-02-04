import json
from app.models import CaseFact, DiagnosisRun, Disease, Rule, Symptom


def build_report(assessment_id: int):
    facts_rows = CaseFact.query.filter_by(assessment_id=assessment_id).all()
    symptom_ids = [a.symptom_id for a in facts_rows]
    symptoms = {s.id: s for s in Symptom.query.filter(Symptom.id.in_(symptom_ids)).all()} if symptom_ids else {}

    yes_list, no_list = [], []
    for row in facts_rows:
        symptom = symptoms.get(row.symptom_id)
        if not symptom:
            continue
        if symptom.input_type == "BOOLEAN" and row.value_bool is not None:
            label = symptom.question_text or symptom.name or symptom.code
            if row.value_bool:
                yes_list.append(label)
            else:
                no_list.append(label)

    result = (
        DiagnosisRun.query
        .filter_by(assessment_id=assessment_id)
        .order_by(DiagnosisRun.id.desc())
        .first()
    )
    if not result:
        return {"assessment_id": assessment_id, "status": "IN_PROGRESS", "next_question": None}

    trace = result.trace_json or {}
    if isinstance(trace, str):
        try:
            trace = json.loads(trace)
        except Exception:
            trace = {}

    reasoning = []
    fired_rule_id = trace.get("fired_rule_id")
    if fired_rule_id:
        rule = Rule.query.get(fired_rule_id)
        if rule and rule.explanation_text:
            reasoning.append(rule.explanation_text)
        if not reasoning:
            reasoning = [f"Rule fired: {rule.rule_code if rule else fired_rule_id}"]

    disease = Disease.query.get(result.disease_id) if result.disease_id else None
    advice = None
    if disease and disease.advice:
        advice = {
            "title": disease.name,
            "content": disease.advice,
            "severity": disease.severity,
            "recommendations": disease.recommendations_json or {},
        }

    return {
        "assessment_id": assessment_id,
        "key_symptoms": {"yes": yes_list, "no": no_list},
        "risk_assessment": {
            "diagnosis_code": disease.code if disease else None,
            "diagnosis_name": disease.name if disease else None,
            "risk_level": result.risk_level,
            "confidence": result.confidence,
        },
        "reasoning": reasoning,
        "advice": advice,
        "top_candidates": trace.get("ranked_candidates_top3") or [],
        "next_best_questions": trace.get("next_best_questions") or [],
        "explanation_trace": trace,
    }
