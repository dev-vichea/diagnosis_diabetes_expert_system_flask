import json
from typing import Any, Dict, List, Optional

from app.models import AssessmentDiagnosisResult, CaseFact, DiagnosisRun, Disease, Rule, Symptom


def _severity_badge_from_level(level: str | None) -> str:
    key = (level or "LOW").upper()
    if key == "HIGH":
        return "DANGER"
    if key == "MEDIUM":
        return "WARN"
    return "INFO"


def _recommendation_to_actions(default_recommendation: str | None) -> list[str]:
    if not default_recommendation:
        return []
    lines = [line.strip(" -\t") for line in default_recommendation.splitlines()]
    cleaned = [line for line in lines if line]
    if not cleaned:
        return []
    return cleaned


def _candidate_payload_from_row(row: AssessmentDiagnosisResult) -> Dict[str, Any]:
    trace = row.trace_json or {}
    if isinstance(trace, str):
        try:
            trace = json.loads(trace)
        except Exception:
            trace = {}

    disease = row.disease
    return {
        "disease_id": row.disease_id,
        "diagnosis_code": disease.code if disease else None,
        "diagnosis_name": disease.name if disease else None,
        "disease_name": disease.name if disease else None,
        "score": int(row.score or 0),
        "confidence": float(row.confidence or 0),
        "est_confidence": round(float(row.confidence or 0) * 100.0, 1),
        "evidence_level": row.evidence_level,
        "risk_level": row.risk_level,
        "summary": trace.get("summary"),
        "trace_json": trace,
    }


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

    candidate_rows = (
        AssessmentDiagnosisResult.query
        .filter_by(assessment_id=assessment_id)
        .order_by(
            AssessmentDiagnosisResult.score.desc(),
            AssessmentDiagnosisResult.confidence.desc(),
            AssessmentDiagnosisResult.id.asc(),
        )
        .all()
    )
    candidates = [_candidate_payload_from_row(row) for row in candidate_rows]
    likely_conditions = [item for item in candidates if item.get("evidence_level") == "HIGH"]
    possible_conditions = [item for item in candidates if item.get("evidence_level") in {"MODERATE", "LOW"}]

    if not result and not candidates:
        return {"assessment_id": assessment_id, "status": "IN_PROGRESS", "next_question": None}

    trace = (result.trace_json if result else {}) or {}
    if isinstance(trace, str):
        try:
            trace = json.loads(trace)
        except Exception:
            trace = {}

    primary_candidate = candidates[0] if candidates else None

    disease: Optional[Disease] = None
    if primary_candidate:
        disease = Disease.query.get(primary_candidate["disease_id"]) if primary_candidate.get("disease_id") else None
    elif result and result.disease_id:
        disease = Disease.query.get(result.disease_id)

    reasoning = []
    fired_rule_id = trace.get("fired_rule_id")
    fired_rule = None
    if fired_rule_id:
        fired_rule = Rule.query.get(fired_rule_id)
        if fired_rule and fired_rule.explanation_text:
            reasoning.append(fired_rule.explanation_text)
        if not reasoning:
            reasoning = [f"Rule fired: {fired_rule.rule_code if fired_rule else fired_rule_id}"]

    if not reasoning and primary_candidate:
        primary_trace = primary_candidate.get("trace_json") or {}
        matched_rules = primary_trace.get("matched_rules") or []
        if matched_rules:
            reasoning = [f"Matched rules: {', '.join([str(item.get('name') or item.get('rule_id')) for item in matched_rules[:3]])}"]

    advice = None
    prediction_mode = str(trace.get("prediction_mode") or "").strip().lower()
    is_partial_prediction = prediction_mode == "partial_match_prediction"
    rule_type = (fired_rule.rule_type or "").strip().lower() if fired_rule else ""
    summary_text = (fired_rule.patient_summary_template if fired_rule else None) or None
    if not summary_text:
        if is_partial_prediction:
            summary_text = "Preliminary screening result based on partial rule evidence. Add more information to improve certainty."
        elif rule_type == "screening":
            summary_text = "Screening result based on current answers. Lab confirmation is recommended when available."

    if disease:
        advice_title = disease.name
        actions = _recommendation_to_actions(disease.default_recommendation)
        if fired_rule and fired_rule.advice_template:
            actions = _recommendation_to_actions(fired_rule.advice_template) or actions
        recommendations = {}
        if actions:
            recommendations["actions"] = actions

        advice = {
            "title": advice_title,
            "content": (
                (fired_rule.doctor_response_template if fired_rule else None)
                or disease.description
                or disease.default_recommendation
            ),
            "severity": _severity_badge_from_level(disease.severity_level),
            "recommendations": recommendations,
        }

    primary_confidence = None
    primary_risk_level = None
    primary_diagnosis_code = None
    primary_diagnosis_name = None

    if primary_candidate:
        primary_confidence = primary_candidate.get("confidence")
        primary_risk_level = primary_candidate.get("risk_level")
        primary_diagnosis_code = primary_candidate.get("diagnosis_code")
        primary_diagnosis_name = primary_candidate.get("diagnosis_name")
    elif result:
        primary_confidence = float(result.confidence) if result.confidence is not None else None
        primary_risk_level = result.risk_level
        primary_diagnosis_code = disease.code if disease else None
        primary_diagnosis_name = disease.name if disease else None

    top_candidates = []
    for item in candidates[:3]:
        top_candidates.append(
            {
                "diagnosis_code": item.get("diagnosis_code"),
                "diagnosis_name": item.get("diagnosis_name"),
                "risk_level": item.get("risk_level"),
                "est_confidence": item.get("est_confidence"),
                "score": item.get("score"),
                "evidence_level": item.get("evidence_level"),
                "status": "MATCHED",
            }
        )

    final_message = (
        (result.final_message if result else None)
        or trace.get("final_message")
    )

    return {
        "assessment_id": assessment_id,
        "key_symptoms": {"yes": yes_list, "no": no_list},
        "risk_assessment": {
            "diagnosis_code": primary_diagnosis_code,
            "diagnosis_name": primary_diagnosis_name,
            "risk_level": primary_risk_level,
            "confidence": primary_confidence,
            "summary": summary_text,
            "final_message": final_message,
        },
        "reasoning": reasoning,
        "advice": advice,
        "top_candidates": top_candidates,
        "likely_conditions": likely_conditions,
        "possible_conditions": possible_conditions,
        "next_best_questions": trace.get("next_best_questions") or [],
        "explanation_trace": trace,
    }
