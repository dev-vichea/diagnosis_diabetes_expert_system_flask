import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.extensions import db
from app.inference.engine_core import Condition, RulePayload, run_inference
from app.inference.facts import facts_for_assessment
from app.models import (
    Assessment,
    CaseFact,
    DiagnosisRun,
    Disease,
    Rule,
    RuleAction,
    Symptom,
)


def _upsert_fact(
    assessment_id: int,
    symptom_id: int,
    value: Any,
    input_type: Optional[str] = None,
    source: str = "USER",
    confidence: float = 1.0,
):
    symptom = Symptom.query.get(symptom_id)
    if not symptom:
        return
    input_type = (input_type or symptom.input_type or "BOOLEAN").upper()

    value_bool = None
    value_number = None
    value_text = None

    if input_type == "BOOLEAN":
        value_bool = bool(value)
    elif input_type == "NUMBER":
        value_number = float(value) if value not in (None, "") else None
    elif input_type in {"TEXT", "SINGLE"}:
        value_text = str(value).strip() if value is not None else None
    else:
        value_bool = bool(value)
        input_type = "BOOLEAN"

    existing = CaseFact.query.filter_by(
        assessment_id=assessment_id,
        symptom_id=symptom_id,
    ).first()
    if existing:
        existing.value_bool = value_bool
        existing.value_number = value_number
        existing.value_text = value_text
        existing.confidence = confidence
        existing.source = source
    else:
        db.session.add(CaseFact(
            assessment_id=assessment_id,
            symptom_id=symptom_id,
            value_bool=value_bool,
            value_number=value_number,
            value_text=value_text,
            confidence=confidence,
            source=source,
        ))


def _rules_payload() -> Tuple[List[RulePayload], Dict[int, Rule], Dict[int, Optional[RuleAction]]]:
    rules = (
        Rule.query.filter_by(is_active=True)
        .order_by(Rule.priority.desc(), Rule.id.asc())
        .all()
    )
    condition_symptom_ids = {c.symptom_id for rule in rules for c in rule.conditions}
    symptom_map = {}
    parent_map = {}
    if condition_symptom_ids:
        symptom_map = {
            s.id: s
            for s in Symptom.query.filter(Symptom.id.in_(condition_symptom_ids)).all()
        }
        parent_ids = {s.parent_symptom_id for s in symptom_map.values() if s.parent_symptom_id}
        if parent_ids:
            parent_map = {
                s.id: s
                for s in Symptom.query.filter(Symptom.id.in_(parent_ids)).all()
            }

    # Preload actions/diseases
    action_map: Dict[int, Optional[RuleAction]] = {}
    if rules:
        action_rows = (
            RuleAction.query
            .filter(RuleAction.rule_id.in_([r.id for r in rules]))
            .all()
        )
        actions_by_rule: Dict[int, List[RuleAction]] = {}
        for action in action_rows:
            actions_by_rule.setdefault(action.rule_id, []).append(action)
        for rule in rules:
            options = actions_by_rule.get(rule.id) or []
            if options:
                action_map[rule.id] = sorted(options, key=lambda a: float(a.confidence or 0), reverse=True)[0]
            else:
                action_map[rule.id] = None

    payloads: List[RulePayload] = []
    rule_map: Dict[int, Rule] = {}
    for rule in rules:
        rule_map[rule.id] = rule
        conditions = []
        for c in rule.conditions:
            symptom = symptom_map.get(c.symptom_id)
            parent_symptom = parent_map.get(symptom.parent_symptom_id) if symptom and symptom.parent_symptom_id else None
            conditions.append(Condition(
                symptom_id=c.symptom_id,
                symptom_code=(symptom.code if symptom else None),
                operator=c.operator or "==",
                value=c.value,
                logic_group=None,
                is_required=bool(c.is_required),
                weight=float(c.weight or 0),
                parent_symptom_id=(symptom.parent_symptom_id if symptom else None),
                parent_symptom_code=(parent_symptom.code if parent_symptom else None),
                parent_show_if_operator=(parent_symptom.show_if_operator if parent_symptom else None),
                parent_show_if_value=(parent_symptom.show_if_value if parent_symptom else None),
                parent_parent_symptom_code=None,
                show_if_operator=(symptom.show_if_operator if symptom else None),
                show_if_value=(symptom.show_if_value if symptom else None),
                is_derived=False,
            ))

        action = action_map.get(rule.id)
        disease = Disease.query.get(action.disease_id) if action else None
        diagnosis_code = disease.code if disease else rule.rule_code
        risk_level = disease.urgency if disease else None
        confidence = float(action.confidence) if action and action.confidence is not None else None

        payloads.append(RulePayload(
            id=rule.id,
            name=rule.title,
            diagnosis_code=diagnosis_code,
            risk_level=risk_level or "UNKNOWN",
            priority=rule.priority or 0,
            confidence=confidence,
            conditions=conditions,
        ))

    return payloads, rule_map, action_map


def _trigger_satisfied(symptom: Symptom, facts: Dict[str, Any]) -> bool:
    if not symptom.parent_symptom_id:
        return True
    parent = Symptom.query.get(symptom.parent_symptom_id)
    if not parent or not parent.code:
        return False
    if parent.code not in facts:
        return False
    actual = facts.get(parent.code)
    operator = (symptom.show_if_operator or "==").upper()
    expected = symptom.show_if_value
    if isinstance(actual, bool) and expected is None:
        expected = True
    if isinstance(expected, str) and expected.lower() in {"true", "false"}:
        expected = expected.lower() == "true"
    if isinstance(expected, str) and expected.strip() in {"1", "0"}:
        expected = expected.strip() == "1"

    if operator == "PRESENT":
        if actual is None:
            return False
        if isinstance(actual, bool):
            return actual is True
        return True

    if operator == "ABSENT":
        if actual is None:
            return True
        if isinstance(actual, bool):
            return actual is False
        return False

    if operator == "==":
        return actual == expected
    if operator == "!=":
        return actual != expected
    try:
        actual_num = float(actual)
        expected_num = float(expected)
    except (TypeError, ValueError):
        actual_num = None
        expected_num = None
    if operator == ">":
        return actual_num is not None and expected_num is not None and actual_num > expected_num
    if operator == ">=":
        return actual_num is not None and expected_num is not None and actual_num >= expected_num
    if operator == "<":
        return actual_num is not None and expected_num is not None and actual_num < expected_num
    if operator == "<=":
        return actual_num is not None and expected_num is not None and actual_num <= expected_num
    return False


def _build_next_best_questions(symptom_ids: List[int]) -> List[Dict[str, Any]]:
    if not symptom_ids:
        return []
    symptoms = {s.id: s for s in Symptom.query.filter(Symptom.id.in_(symptom_ids)).all()}
    output = []
    for sid in symptom_ids:
        s = symptoms.get(sid)
        if not s:
            continue
        output.append({
            "symptom_id": s.id,
            "code": s.code,
            "text": s.question_text or s.name or s.code,
        })
    return output


def _next_symptom_from_rules(
    assessment_id: int,
    inference: Dict[str, Any],
    excluded_ids: Optional[set] = None,
) -> Optional[Symptom]:
    excluded_ids = excluded_ids or set()
    answered_ids = {
        r.symptom_id for r in CaseFact.query.filter_by(assessment_id=assessment_id).all()
    }
    if excluded_ids:
        answered_ids.update(excluded_ids)

    candidate_ids = inference.get("next_best_question_ids") or []
    for sid in candidate_ids:
        if sid in answered_ids:
            continue
        symptom = Symptom.query.get(sid)
        if not symptom or not symptom.is_active:
            continue
        facts = inference.get("facts") or {}
        if not _trigger_satisfied(symptom, facts):
            continue
        return symptom

    return _fallback_symptom(assessment_id, excluded_ids=answered_ids)


def _fallback_symptom(assessment_id: int, excluded_ids: Optional[set] = None) -> Optional[Symptom]:
    excluded_ids = excluded_ids or set()
    facts = facts_for_assessment(assessment_id)
    query = Symptom.query.filter_by(is_active=True)
    if excluded_ids:
        query = query.filter(~Symptom.id.in_(excluded_ids))
    for symptom in query.order_by(Symptom.priority_order.asc(), Symptom.id.asc()).all():
        if _trigger_satisfied(symptom, facts):
            return symptom
    return None


def _inference_for_assessment(assessment_id: int) -> Tuple[Dict[str, Any], Dict[int, Rule], Dict[int, Optional[RuleAction]]]:
    facts = facts_for_assessment(assessment_id)
    rules_payload, rule_map, action_map = _rules_payload()
    inference = run_inference(facts, rules_payload)
    inference["facts"] = facts
    return inference, rule_map, action_map


def get_inference_snapshot(assessment_id: int) -> Dict[str, Any]:
    inference, _, _ = _inference_for_assessment(assessment_id)
    return inference


def _sanitize_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _sanitize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(v) for v in value]
    if isinstance(value, tuple):
        return [_sanitize_json(v) for v in value]
    if isinstance(value, set):
        return [_sanitize_json(v) for v in value]
    return value


def get_ranked_candidates(assessment: Assessment, limit: int = 3) -> Dict[str, Any]:
    inference, _, _ = _inference_for_assessment(assessment.id)
    candidates = inference.get("top_candidates") or []
    top = candidates[:limit]
    next_symptom = _next_symptom_from_rules(assessment.id, inference)
    next_questions = _build_next_best_questions([next_symptom.id] if next_symptom else [])
    return {"candidates": top, "next_best_questions": next_questions}


def get_next_symptom(assessment: Assessment, excluded_ids: Optional[set] = None) -> Optional[Symptom]:
    inference, _, _ = _inference_for_assessment(assessment.id)
    return _next_symptom_from_rules(assessment.id, inference, excluded_ids=excluded_ids)


def finalize_if_ready(assessment: Assessment) -> Optional[DiagnosisRun]:
    inference, rule_map, action_map = _inference_for_assessment(assessment.id)
    best_row = inference.get("best_row")
    if not best_row or not inference.get("finalizable"):
        return None

    next_symptom = _next_symptom_from_rules(assessment.id, inference)
    if next_symptom:
        return None

    best_rule = rule_map.get(best_row["rule_id"])
    if not best_rule:
        return None

    action = action_map.get(best_rule.id)
    disease = Disease.query.get(action.disease_id) if action else None
    if not disease:
        disease = Disease.query.filter_by(code=best_rule.rule_code).first()
    if not disease:
        disease = Disease(
            code=best_rule.rule_code,
            name=best_rule.title or best_rule.rule_code,
            urgency="LOW",
            severity="INFO",
            is_active=True,
        )
        db.session.add(disease)
        db.session.flush()

    diagnosis_code = disease.code
    risk_level = disease.urgency
    confidence = float(action.confidence) if action and action.confidence is not None else None

    next_best_questions = _build_next_best_questions(inference.get("next_best_question_ids") or [])

    trace = {
        "fired_rule_id": best_rule.id,
        "fired_rule_code": best_rule.rule_code,
        "disease_id": disease.id,
        "disease_code": diagnosis_code,
        "matched_conditions": best_row.get("matched_conditions", []),
        "evidence_details": best_row.get("evidence_details", []),
        "facts": inference.get("facts") or {},
        "rules_evaluated": inference.get("evaluated", []),
        "ranked_candidates_top3": inference.get("top_candidates", []),
        "next_best_questions": next_best_questions,
    }
    trace = _sanitize_json(trace)

    run = DiagnosisRun(
        assessment_id=assessment.id,
        disease_id=disease.id,
        risk_level=risk_level,
        confidence=confidence,
        trace_json=trace,
        created_at=datetime.utcnow(),
    )
    db.session.add(run)
    assessment.status = "COMPLETED"
    assessment.completed_at = datetime.utcnow()
    db.session.commit()
    return run


def ensure_fallback_result(assessment: Assessment) -> DiagnosisRun:
    existing = DiagnosisRun.query.filter_by(assessment_id=assessment.id).order_by(DiagnosisRun.id.desc()).first()
    if existing:
        return existing

    inference, _, _ = _inference_for_assessment(assessment.id)
    evaluated = inference.get("evaluated", [])
    possible = [row for row in evaluated if row.get("status") == "POSSIBLE"]
    top3 = sorted(possible, key=lambda x: x.get("score", 0), reverse=True)[:3]

    next_best_questions = _build_next_best_questions(inference.get("next_best_question_ids") or [])
    trace = {
        "fired_rule_id": None,
        "fired_rule_code": None,
        "matched_conditions": [],
        "facts": inference.get("facts") or {},
        "rules_evaluated": evaluated,
        "ranked_candidates_top3": top3,
        "next_best_questions": next_best_questions,
    }
    trace = _sanitize_json(trace)

    disease = Disease.query.filter_by(code="UNDETERMINED").first()
    if not disease:
        disease = Disease(
            code="UNDETERMINED",
            name="Undetermined",
            urgency="LOW",
            severity="INFO",
            is_active=True,
        )
        db.session.add(disease)
        db.session.flush()

    run = DiagnosisRun(
        assessment_id=assessment.id,
        disease_id=disease.id,
        risk_level="LOW",
        confidence=None,
        trace_json=trace,
        created_at=datetime.utcnow(),
    )
    db.session.add(run)
    assessment.status = "COMPLETED"
    assessment.completed_at = datetime.utcnow()
    db.session.commit()
    return run


def submit_answer(
    assessment: Assessment,
    symptom_id: int,
    value: Any,
    input_type: Optional[str] = None,
    finalize: bool = True,
) -> Optional[DiagnosisRun]:
    _upsert_fact(assessment.id, symptom_id, value, input_type=input_type)
    db.session.commit()
    return finalize_if_ready(assessment) if finalize else None


def run_diagnosis_now(assessment: Assessment) -> DiagnosisRun:
    inference, rule_map, action_map = _inference_for_assessment(assessment.id)
    best_row = inference.get("best_row")
    if not best_row:
        return ensure_fallback_result(assessment)

    rule = rule_map.get(best_row.get("rule_id"))
    if not rule:
        return ensure_fallback_result(assessment)

    action = action_map.get(rule.id)
    disease = Disease.query.get(action.disease_id) if action else None
    if not disease:
        disease = Disease.query.filter_by(code=rule.rule_code).first()
    if not disease:
        disease = Disease(
            code=rule.rule_code,
            name=rule.title or rule.rule_code,
            urgency="LOW",
            severity="INFO",
            is_active=True,
        )
        db.session.add(disease)
        db.session.flush()

    confidence = None
    if action and action.confidence is not None:
        confidence = float(action.confidence)
    else:
        confidence = best_row.get("confidence")

    matched_conditions = best_row.get("matched_conditions") or []
    trace = {
        "fired_rule_id": rule.id,
        "fired_rule_code": rule.rule_code,
        "disease_id": disease.id,
        "disease_code": disease.code,
        "facts_used": inference.get("facts") or {},
        "rules_fired": [
            {
                "rule_code": rule.rule_code,
                "matched": matched_conditions,
                "action": {"disease": disease.code, "confidence": confidence},
            }
        ],
        "final": {"disease": disease.code, "confidence": confidence},
        "matched_conditions": matched_conditions,
        "rules_evaluated": inference.get("evaluated", []),
        "ranked_candidates_top3": inference.get("top_candidates", []),
        "next_best_questions": _build_next_best_questions(inference.get("next_best_question_ids") or []),
    }
    trace = _sanitize_json(trace)

    run = DiagnosisRun(
        assessment_id=assessment.id,
        disease_id=disease.id,
        risk_level=disease.urgency,
        confidence=confidence,
        trace_json=trace,
        created_at=datetime.utcnow(),
    )
    db.session.add(run)
    assessment.status = "COMPLETED"
    assessment.completed_at = datetime.utcnow()
    db.session.commit()
    return run
