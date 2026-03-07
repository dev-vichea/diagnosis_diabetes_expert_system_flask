import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.extensions import db
from app.inference.engine_core import Condition, RulePayload, run_inference
from app.inference.facts import facts_for_assessment
from app.models import (
    Assessment,
    AssessmentDiagnosisResult,
    AssessmentRuleResult,
    CaseFact,
    DiagnosisRun,
    Disease,
    Rule,
    RuleAction,
    Symptom,
)

PARTIAL_MATCH_MIN_COVERAGE = 0.75
ENGINE_VERSION = "multi-candidate-v1"
MAX_SCORE_PER_DISEASE = 150
MIN_SCORE_TO_STORE = 1
EVIDENCE_THRESHOLDS = {
    "HIGH": 120,
    "MODERATE": 70,
    "LOW": 40,
}


LAB_FACT_KEYS = {
    "fpg": {"fpg", "fasting_plasma_glucose", "fasting_glucose", "fbs", "glucose_fasting"},
    "hba1c": {"hba1c", "hb_a1c", "a1c", "glycated_hemoglobin"},
}

KEY_LAB_ALIAS_MAP = {
    "FBS": {"fbs", "fpg", "fasting_plasma_glucose", "fasting_glucose", "glucose_fasting"},
    "HBA1C": {"hba1c", "hb_a1c", "a1c", "glycated_hemoglobin"},
    "OGTT": {"ogtt75_fast", "ogtt75_1h", "ogtt75_2h", "ogtt", "oral_glucose_tolerance"},
}


def _risk_from_disease(disease: Optional[Disease]) -> str:
    if not disease:
        return "LOW"
    severity_level = (disease.severity_level or "LOW").upper()
    if severity_level == "HIGH":
        return "HIGH"
    if severity_level == "MEDIUM":
        return "MEDIUM"
    return "LOW"


def _severity_level_from_risk_level(risk_level: Optional[str]) -> str:
    level = (risk_level or "").upper()
    if level == "HIGH":
        return "high"
    if level == "MEDIUM":
        return "medium"
    return "low"


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
    value_json = None
    state = "unknown"
    is_provided = False

    if input_type == "BOOLEAN":
        if value in (None, ""):
            value_bool = None
            state = "unknown"
        else:
            value_bool = bool(value)
            state = "true" if value_bool else "false"
            is_provided = True
    elif input_type == "NUMBER":
        value_number = float(value) if value not in (None, "") else None
        is_provided = value_number is not None
        state = "true" if is_provided else "unknown"
    elif input_type in {"TEXT", "SINGLE"}:
        value_text = str(value).strip() if value is not None else None
        is_provided = bool(value_text)
        state = "true" if is_provided else "unknown"
    elif input_type == "MULTI":
        if isinstance(value, list):
            value_json = value
        elif value in (None, ""):
            value_json = []
        else:
            value_json = [value]
        is_provided = bool(value_json)
        state = "true" if is_provided else "unknown"
    else:
        value_bool = bool(value)
        input_type = "BOOLEAN"
        is_provided = True
        state = "true" if value_bool else "false"

    existing = CaseFact.query.filter_by(
        assessment_id=assessment_id,
        symptom_id=symptom_id,
    ).first()
    if existing:
        existing.finding_code = symptom.code
        existing.value_bool = value_bool
        existing.value_number = value_number
        existing.value_text = value_text
        existing.value_json = value_json
        existing.state = state
        existing.is_provided = is_provided
        existing.confidence = confidence
        existing.source = source
    else:
        db.session.add(CaseFact(
            assessment_id=assessment_id,
            symptom_id=symptom_id,
            finding_code=symptom.code,
            value_bool=value_bool,
            value_number=value_number,
            value_text=value_text,
            value_json=value_json,
            state=state,
            is_provided=is_provided,
            confidence=confidence,
            source=source,
        ))


def _rules_payload() -> Tuple[List[RulePayload], Dict[int, Rule], Dict[int, Dict[str, Any]]]:
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
                action_map[rule.id] = sorted(
                    options,
                    key=lambda a: float(a.confidence or 0),
                    reverse=True,
                )[0]
            else:
                action_map[rule.id] = None

    disease_ids = {rule.disease_id for rule in rules if rule.disease_id}
    for action in action_map.values():
        if action and action.disease_id:
            disease_ids.add(action.disease_id)
    diseases_by_id = {
        disease.id: disease
        for disease in Disease.query.filter(Disease.id.in_(disease_ids)).all()
    } if disease_ids else {}

    payloads: List[RulePayload] = []
    rule_map: Dict[int, Rule] = {}
    target_map: Dict[int, Dict[str, Any]] = {}
    for rule in rules:
        rule_map[rule.id] = rule
        conditions = []
        for c in rule.conditions:
            symptom = symptom_map.get(c.symptom_id)
            parent_symptom = parent_map.get(symptom.parent_symptom_id) if symptom and symptom.parent_symptom_id else None
            conditions.append(Condition(
                symptom_id=c.symptom_id,
                symptom_code=(symptom.code if symptom else None),
                finding_code=(c.finding_code or (symptom.code if symptom else None)),
                operator=c.operator or "==",
                value=c.value,
                values=(c.values_json if c.values_json is not None else c.value),
                logic_group=None,
                is_required=bool(c.is_required),
                weight=float(c.weight or 0),
                score_points=int(c.score_points or 0),
                negate=bool(c.negate),
                input_type=(symptom.input_type if symptom else None),
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
        disease = diseases_by_id.get(rule.disease_id) if rule.disease_id else None
        if not disease and action and action.disease_id:
            disease = diseases_by_id.get(action.disease_id)
        diagnosis_code = disease.code if disease else rule.rule_code
        risk_level = (rule.risk_level or _risk_from_disease(disease) or "LOW").upper()

        configured_conf = _normalize_confidence(float(rule.base_confidence) if rule.base_confidence is not None else None)
        legacy_conf = _normalize_confidence(float(action.confidence) if action and action.confidence is not None else None)
        confidence = configured_conf if configured_conf is not None else legacy_conf

        target_map[rule.id] = {
            "disease": disease,
            "risk_level": risk_level,
            "confidence": confidence,
        }

        payloads.append(RulePayload(
            id=rule.id,
            name=rule.title,
            diagnosis_code=diagnosis_code,
            risk_level=risk_level,
            rule_type=(rule.rule_type or "screening"),
            stop_on_match=bool(rule.stop_on_match),
            confidence_cap_if_unconfirmed=(
                float(rule.confidence_cap_if_unconfirmed)
                if rule.confidence_cap_if_unconfirmed is not None
                else None
            ),
            confidence_bonus_max=(
                float(rule.confidence_bonus_max)
                if rule.confidence_bonus_max is not None
                else None
            ),
            min_required_matches=(
                int(rule.min_required_matches)
                if rule.min_required_matches is not None
                else None
            ),
            priority=rule.priority or 0,
            confidence=confidence,
            conditions=conditions,
        ))

    return payloads, rule_map, target_map


def _ensure_rule_disease(rule: Rule, fallback_risk: Optional[str] = None) -> Disease:
    disease = Disease.query.get(rule.disease_id) if rule.disease_id else None
    if disease:
        return disease

    disease = Disease.query.filter_by(code=rule.rule_code).first()
    if not disease:
        risk_level = (fallback_risk or rule.risk_level or "LOW").upper()
        disease = Disease(
            code=rule.rule_code,
            name=rule.title or rule.rule_code,
            severity_level=_severity_level_from_risk_level(risk_level),
            active=True,
        )
        db.session.add(disease)
        db.session.flush()

    rule.disease_id = disease.id
    if not rule.risk_level:
        rule.risk_level = (fallback_risk or _risk_from_disease(disease) or "LOW").upper()
    return disease


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


def _inference_for_assessment(assessment_id: int) -> Tuple[Dict[str, Any], Dict[int, Rule], Dict[int, Dict[str, Any]]]:
    facts = facts_for_assessment(assessment_id)
    rules_payload, rule_map, target_map = _rules_payload()
    inference = run_inference(facts, rules_payload)
    inference["facts"] = facts
    return inference, rule_map, target_map


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


def _normalize_confidence(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return None
    if conf > 1.0:
        conf = conf / 100.0
    return max(0.0, min(1.0, conf))


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _truthy_fact(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return float(value) > 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"", "false", "0", "no", "none", "unknown", "dont_know", "don't know"}:
            return False
        return True
    return bool(value)


def _rule_weight_points(rule: Rule) -> int:
    priority = int(rule.priority or 0)
    if priority <= 0:
        priority = 10

    base_confidence = _normalize_confidence(float(rule.base_confidence) if rule.base_confidence is not None else 0.5)
    confidence_bonus = int(round((base_confidence or 0.5) * 20))
    return priority + confidence_bonus


def _symptom_points_for_fact(fact_code: str, value: Any) -> int:
    if not _truthy_fact(value):
        return 0
    numeric = _safe_float(value)
    if numeric is not None:
        return 1
    if isinstance(value, bool):
        return 1
    return 1


def _find_fact_value(facts: Dict[str, Any], accepted_keys: set[str]) -> Optional[float]:
    if not facts:
        return None
    lowered = {str(k).lower(): v for k, v in facts.items()}
    for key in accepted_keys:
        direct = facts.get(key)
        parsed = _safe_float(direct)
        if parsed is not None:
            return parsed
        parsed = _safe_float(lowered.get(str(key).lower()))
        if parsed is not None:
            return parsed
    return None


def _lab_points(fpg: Optional[float], hba1c: Optional[float]) -> Tuple[int, List[Dict[str, Any]]]:
    points = 0
    detail: List[Dict[str, Any]] = []

    if fpg is not None:
        if fpg >= 126:
            points += 30
            detail.append({"fact": "fpg", "points": 30})
        elif fpg >= 100:
            points += 15
            detail.append({"fact": "fpg", "points": 15})

    if hba1c is not None:
        if hba1c >= 6.5:
            points += 30
            detail.append({"fact": "hba1c", "points": 30})
        elif hba1c >= 5.7:
            points += 15
            detail.append({"fact": "hba1c", "points": 15})

    return points, detail


def _labs_info(facts: Dict[str, Any]) -> Dict[str, Any]:
    fpg = _find_fact_value(facts, LAB_FACT_KEYS["fpg"])
    hba1c = _find_fact_value(facts, LAB_FACT_KEYS["hba1c"])

    has_labs_flag = facts.get("has_labs")
    has_labs = bool(has_labs_flag) if isinstance(has_labs_flag, bool) else bool(fpg is not None or hba1c is not None)

    labs_invalid = False
    if fpg is not None and (fpg < 50 or fpg > 600):
        labs_invalid = True
    if hba1c is not None and (hba1c < 3 or hba1c > 20):
        labs_invalid = True

    missing_critical: List[str] = []
    if labs_invalid:
        missing_critical.append("Lab values are out of valid range and were ignored")
    if fpg is None and hba1c is None:
        missing_critical.append("FPG/HbA1c not provided")

    return {
        "has_labs": has_labs,
        "labs_invalid": labs_invalid,
        "fpg": fpg,
        "hba1c": hba1c,
        "missing_critical": missing_critical,
    }


def _match_state(row: Dict[str, Any]) -> str:
    state = str(row.get("matched_state") or "").strip().lower()
    if state in {"match", "no_match", "unknown"}:
        return state
    status = str(row.get("status") or "").strip().upper()
    if status == "MATCHED":
        return "match"
    if status == "POSSIBLE":
        return "unknown"
    return "no_match"


def _canonical_missing_key_labs(missing_codes: List[str]) -> List[str]:
    code_set = {str(code or "").strip().lower() for code in missing_codes if str(code or "").strip()}
    labels: List[str] = []
    for label, aliases in KEY_LAB_ALIAS_MAP.items():
        if code_set & {a.lower() for a in aliases}:
            labels.append(label)
    return sorted(set(labels))


def _evidence_level_from_score(score: int) -> Optional[str]:
    if score >= EVIDENCE_THRESHOLDS["HIGH"]:
        return "HIGH"
    if score >= EVIDENCE_THRESHOLDS["MODERATE"]:
        return "MODERATE"
    if score >= EVIDENCE_THRESHOLDS["LOW"]:
        return "LOW"
    if score > 0:
        return "LOW"
    return None


def _row_match_coverage(row: Dict[str, Any]) -> float:
    total = float(row.get("total_conditions") or 0)
    matched = float(row.get("matched_count") or 0)
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, matched / total))


def _build_candidate_rows(
    assessment: Assessment,
) -> Dict[str, Any]:
    inference, rule_map, target_map = _inference_for_assessment(assessment.id)
    facts = inference.get("facts") or {}
    labs = _labs_info(facts)

    candidates_by_disease: Dict[int, Dict[str, Any]] = {}

    for row in (inference.get("evaluated") or []):
        rule = rule_map.get(row.get("rule_id"))
        if not rule:
            continue

        target = target_map.get(rule.id) or {}
        disease = target.get("disease")
        base_risk = (target.get("risk_level") or rule.risk_level or _risk_from_disease(disease) or "LOW").upper()
        if not disease:
            disease = _ensure_rule_disease(rule, base_risk)
        if not disease:
            continue

        candidate = candidates_by_disease.get(disease.id)
        if not candidate:
            candidate = {
                "disease": disease,
                "risk_level": base_risk,
                "score": 0,
                "matched_rules": [],
                "missing_rules": [],
                "contributing_fact_codes": set(),
                "symptom_points": [],
                "lab_points": [],
                "confirmed_by_rule_id": None,
                "missing_finding_codes": set(),
            }
            candidates_by_disease[disease.id] = candidate

        matched_conditions = row.get("matched_conditions") or []
        missing_conditions = row.get("missing_conditions") or []
        missing_findings = row.get("missing_findings") or []
        total_conditions = int(row.get("total_conditions") or 0)
        matched_state = _match_state(row)
        rule_type = str(row.get("rule_type") or rule.rule_type or "screening").strip().lower()
        is_rule_fired = matched_state == "match"

        if is_rule_fired:
            rule_weight = _rule_weight_points(rule)
            candidate["score"] += rule_weight
            matched_codes = []
            for cond in matched_conditions:
                cond_code = cond.get("finding_code") or cond.get("symptom_code")
                if cond_code:
                    matched_codes.append(cond_code)
                    if cond_code in facts and _truthy_fact(facts.get(cond_code)):
                        candidate["contributing_fact_codes"].add(cond_code)
            candidate["matched_rules"].append(
                {
                    "rule_id": rule.id,
                    "name": rule.title,
                    "rule_type": rule_type,
                    "weight": rule_weight,
                    "matched_conditions": sorted(set(matched_codes)),
                }
            )
            if rule_type == "diagnostic":
                current = candidate.get("confirmed_by_rule_id")
                if current is None:
                    candidate["confirmed_by_rule_id"] = rule.id
                else:
                    current_rule = rule_map.get(current)
                    current_priority = int(current_rule.priority or 0) if current_rule else -1
                    if int(rule.priority or 0) > current_priority:
                        candidate["confirmed_by_rule_id"] = rule.id
        elif matched_state == "unknown":
            candidate["missing_finding_codes"].update(str(code) for code in missing_findings if code)
            candidate["missing_rules"].append(
                {
                    "rule_id": rule.id,
                    "name": rule.title,
                    "rule_type": rule_type,
                    "missing_conditions": [
                        cond.get("finding_code") or cond.get("symptom_code") or str(cond.get("symptom_id"))
                        for cond in missing_conditions
                    ] or [str(code) for code in missing_findings if code],
                }
            )

    ranked_candidates: List[Dict[str, Any]] = []
    for candidate in candidates_by_disease.values():
        if not candidate["matched_rules"]:
            continue

        for fact_code in sorted(candidate["contributing_fact_codes"]):
            points = _symptom_points_for_fact(fact_code, facts.get(fact_code))
            if points <= 0:
                continue
            candidate["score"] += points
            candidate["symptom_points"].append({"fact": fact_code, "points": points})

        if not labs["labs_invalid"]:
            lab_score, lab_points = _lab_points(labs.get("fpg"), labs.get("hba1c"))
            candidate["score"] += lab_score
            candidate["lab_points"] = lab_points

        score = int(candidate["score"])
        if score < MIN_SCORE_TO_STORE:
            continue

        confidence = min(0.95, score / float(MAX_SCORE_PER_DISEASE))
        evidence_level = _evidence_level_from_score(score)
        if not evidence_level:
            continue

        status = "possible"
        if candidate.get("confirmed_by_rule_id"):
            status = "confirmed"
        elif evidence_level == "HIGH":
            status = "high"
        elif evidence_level in {"LOW", "MODERATE"}:
            status = "possible"
        else:
            status = "unlikely"

        missing_key_facts = _canonical_missing_key_labs(list(candidate.get("missing_finding_codes") or []))

        missing_critical = list(labs.get("missing_critical") or [])
        summary = f"{len(candidate['matched_rules'])} matched rule(s), {len(candidate['symptom_points'])} fact contribution(s)."

        trace = {
            "disease_code": candidate["disease"].code,
            "score": score,
            "max_score": MAX_SCORE_PER_DISEASE,
            "confidence": round(confidence, 3),
            "evidence_level": evidence_level,
            "facts": facts,
            "labs": {
                "has_labs": bool(labs.get("has_labs")),
                "labs_invalid": bool(labs.get("labs_invalid")),
                "fpg": labs.get("fpg"),
                "hba1c": labs.get("hba1c"),
            },
            "matched_rules": candidate["matched_rules"],
            "symptom_points": candidate["symptom_points"],
            "lab_points": candidate["lab_points"],
            "missing_critical": missing_critical,
            "missing_rules": candidate["missing_rules"],
            "status": status,
            "confirmed_by_rule_id": candidate.get("confirmed_by_rule_id"),
            "missing_key_facts_json": missing_key_facts,
        }

        ranked_candidates.append(
            {
                "disease": candidate["disease"],
                "disease_id": candidate["disease"].id,
                "disease_code": candidate["disease"].code,
                "disease_name": candidate["disease"].name,
                "risk_level": candidate["risk_level"],
                "score": score,
                "confidence": round(confidence, 3),
                "evidence_level": evidence_level,
                "summary": summary,
                "status": status,
                "confirmed_by_rule_id": candidate.get("confirmed_by_rule_id"),
                "missing_key_facts_json": missing_key_facts,
                "trace_json": _sanitize_json(trace),
            }
        )

    ranked_candidates.sort(
        key=lambda item: (item["score"], item["confidence"], item["disease_name"]),
        reverse=True,
    )

    return {
        "inference": inference,
        "facts": facts,
        "labs": labs,
        "candidates": ranked_candidates,
    }


def _group_candidates(candidates: List[Dict[str, Any]], limit: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
    likely = [c for c in candidates if c.get("evidence_level") == "HIGH"]
    possible = [c for c in candidates if c.get("evidence_level") in {"MODERATE", "LOW"}]

    if limit is not None and limit > 0:
        likely = likely[:limit]
        possible = possible[:limit]

    return {
        "likely_conditions": likely,
        "possible_conditions": possible,
    }


def _candidate_payload(candidate: Dict[str, Any], include_trace: bool = False) -> Dict[str, Any]:
    payload = {
        "disease_id": candidate.get("disease_id"),
        "disease_code": candidate.get("disease_code"),
        "disease_name": candidate.get("disease_name"),
        "score": candidate.get("score"),
        "confidence": candidate.get("confidence"),
        "status": candidate.get("status"),
        "confirmed_by_rule_id": candidate.get("confirmed_by_rule_id"),
        "evidence_level": candidate.get("evidence_level"),
        "risk_level": candidate.get("risk_level"),
        "summary": candidate.get("summary"),
        "details_available": True,
    }
    if include_trace:
        payload["trace_json"] = candidate.get("trace_json") or {}
    return payload


def _candidate_payload_from_row(row: AssessmentDiagnosisResult, include_trace: bool = False) -> Dict[str, Any]:
    disease = row.disease
    payload = {
        "disease_id": row.disease_id,
        "disease_code": disease.code if disease else None,
        "disease_name": disease.name if disease else None,
        "score": int(row.score or 0),
        "confidence": float(row.confidence or 0),
        "status": row.status,
        "confirmed_by_rule_id": row.confirmed_by_rule_id,
        "evidence_level": row.evidence_level,
        "risk_level": row.risk_level,
        "summary": None,
        "details_available": True,
    }
    trace = row.trace_json or {}
    if isinstance(trace, str):
        try:
            trace = json.loads(trace)
        except Exception:
            trace = {}
    payload["summary"] = trace.get("summary") or f"Evidence level: {row.evidence_level}"
    if include_trace:
        payload["trace_json"] = trace
    return payload


def _results_from_db(assessment_id: int) -> List[AssessmentDiagnosisResult]:
    return (
        AssessmentDiagnosisResult.query
        .filter_by(assessment_id=assessment_id)
        .order_by(
            AssessmentDiagnosisResult.score.desc(),
            AssessmentDiagnosisResult.confidence.desc(),
            AssessmentDiagnosisResult.id.asc(),
        )
        .all()
    )


def _final_message(candidates: List[Dict[str, Any]], labs: Dict[str, Any]) -> Optional[str]:
    if labs.get("labs_invalid"):
        return "Lab values are out of valid range; scoring used symptoms/risk only."
    if not candidates:
        return "No condition reached the minimum evidence threshold."

    top = candidates[0]
    if top.get("evidence_level") in {"MODERATE", "LOW"} and labs.get("fpg") is None and labs.get("hba1c") is None:
        return "Recommend lab confirmation (FPG/HbA1c)."
    return None


def _persist_assessment_results(
    assessment: Assessment,
    candidates: List[Dict[str, Any]],
) -> None:
    AssessmentDiagnosisResult.query.filter_by(assessment_id=assessment.id).delete()

    now = datetime.utcnow()
    for candidate in candidates:
        trace = candidate.get("trace_json") or {}
        if isinstance(trace, dict) and "summary" not in trace:
            trace["summary"] = candidate.get("summary")
        db.session.add(
            AssessmentDiagnosisResult(
                assessment_id=assessment.id,
                disease_id=candidate["disease_id"],
                score=int(candidate["score"]),
                confidence=float(candidate["confidence"]),
                status=str(candidate.get("status") or "possible").lower(),
                confirmed_by_rule_id=candidate.get("confirmed_by_rule_id"),
                evidence_level=candidate["evidence_level"],
                risk_level=(candidate.get("risk_level") or "LOW").upper(),
                missing_key_facts_json=_sanitize_json(candidate.get("missing_key_facts_json") or []),
                trace_json=_sanitize_json(trace),
                created_at=now,
            )
        )


def _persist_rule_results(assessment: Assessment, inference: Dict[str, Any]) -> None:
    AssessmentRuleResult.query.filter_by(assessment_id=assessment.id).delete()

    for row in (inference.get("evaluated") or []):
        rule_id = row.get("rule_id")
        if not rule_id:
            continue

        matched_state = _match_state(row)
        missing_findings = row.get("missing_findings")
        if not missing_findings:
            missing_findings = [
                cond.get("finding_code") or cond.get("symptom_code") or str(cond.get("symptom_id"))
                for cond in (row.get("missing_conditions") or [])
            ]

        explain_text = row.get("explain_text") or (
            f"Rule {rule_id} -> {matched_state}; "
            f"matched={int(row.get('matched_count') or 0)}/{int(row.get('total_conditions') or 0)}."
        )

        db.session.add(
            AssessmentRuleResult(
                assessment_id=assessment.id,
                rule_id=int(rule_id),
                matched_state=matched_state,
                score_added=int(round(float(row.get("score_added") or 0))),
                confidence_added=0.0,
                missing_findings_json=_sanitize_json(sorted(set(str(x) for x in (missing_findings or []) if x))),
                explain_text=explain_text,
                created_at=datetime.utcnow(),
            )
        )


def _legacy_top_candidates_payload(candidates: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    rows = []
    for candidate in candidates[:limit]:
        rows.append(
            {
                "diagnosis_code": candidate.get("disease_code"),
                "diagnosis_name": candidate.get("disease_name"),
                "risk_level": candidate.get("risk_level"),
                "status": "MATCHED",
                "est_confidence": round(float(candidate.get("confidence") or 0) * 100.0, 1),
                "score": candidate.get("score"),
                "evidence_level": candidate.get("evidence_level"),
            }
        )
    return rows


def _build_run_trace(
    candidates: List[Dict[str, Any]],
    inference: Dict[str, Any],
    facts: Dict[str, Any],
    final_message: Optional[str],
    labs: Dict[str, Any],
) -> Dict[str, Any]:
    primary = candidates[0] if candidates else None
    primary_trace = primary.get("trace_json") if primary else {}
    primary_trace = primary_trace if isinstance(primary_trace, dict) else {}
    matched_rules = primary_trace.get("matched_rules") or []

    rules_fired = []
    for item in matched_rules:
        matched = []
        for cond_code in (item.get("matched_conditions") or []):
            matched.append({"symptom_code": cond_code, "symptom_id": None})
        rules_fired.append(
            {
                "rule_id": item.get("rule_id"),
                "rule_code": item.get("name"),
                "matched": matched,
                "matched_conditions": matched,
                "weight": item.get("weight"),
            }
        )

    first_rule = rules_fired[0] if rules_fired else {}

    trace = {
        "engine_version": ENGINE_VERSION,
        "fired_rule_id": first_rule.get("rule_id"),
        "fired_rule_code": first_rule.get("rule_code"),
        "disease_id": primary.get("disease_id") if primary else None,
        "disease_code": primary.get("disease_code") if primary else None,
        "prediction_mode": "matched_rule" if primary else "no_match",
        "match_coverage": round(min(1.0, (primary.get("score", 0) / MAX_SCORE_PER_DISEASE)), 4) if primary else 0,
        "selected_candidate_status": "MATCHED" if primary else "NONE",
        "facts_used": facts,
        "facts": facts,
        "rules_fired": rules_fired,
        "final": {
            "disease": primary.get("disease_code") if primary else None,
            "confidence": primary.get("confidence") if primary else None,
        },
        "matched_conditions": first_rule.get("matched") or [],
        "missing_conditions": [],
        "rules_evaluated": inference.get("evaluated") or [],
        "ranked_candidates_top3": _legacy_top_candidates_payload(candidates, limit=3),
        "likely_conditions": [_candidate_payload(item) for item in _group_candidates(candidates)["likely_conditions"]],
        "possible_conditions": [_candidate_payload(item) for item in _group_candidates(candidates)["possible_conditions"]],
        "next_best_questions": _build_next_best_questions(inference.get("next_best_question_ids") or []),
        "labs": {
            "has_labs": bool(labs.get("has_labs")),
            "labs_invalid": bool(labs.get("labs_invalid")),
            "fpg": labs.get("fpg"),
            "hba1c": labs.get("hba1c"),
        },
        "final_message": final_message,
        "primary_disease": {
            "disease_id": primary.get("disease_id") if primary else None,
            "disease_code": primary.get("disease_code") if primary else None,
            "disease_name": primary.get("disease_name") if primary else None,
            "confidence": primary.get("confidence") if primary else None,
            "risk_level": primary.get("risk_level") if primary else None,
            "evidence_level": primary.get("evidence_level") if primary else None,
        },
    }
    return _sanitize_json(trace)


def _create_undetermined_disease() -> Disease:
    disease = Disease.query.filter_by(code="UNDETERMINED").first()
    if disease:
        return disease

    disease = Disease(
        code="UNDETERMINED",
        name="Undetermined",
        severity_level="low",
        active=True,
    )
    db.session.add(disease)
    db.session.flush()
    return disease


def _create_run_record(
    assessment: Assessment,
    primary_candidate: Optional[Dict[str, Any]],
    trace: Dict[str, Any],
    final_message: Optional[str],
    facts: Dict[str, Any],
) -> DiagnosisRun:
    disease_id = primary_candidate.get("disease_id") if primary_candidate else None
    confidence = primary_candidate.get("confidence") if primary_candidate else None
    risk_level = (primary_candidate.get("risk_level") if primary_candidate else "LOW") or "LOW"

    if disease_id is None:
        undetermined = _create_undetermined_disease()
        disease_id = undetermined.id
        risk_level = "LOW"
        confidence = None

    run = DiagnosisRun(
        assessment_id=assessment.id,
        disease_id=disease_id,
        risk_level=risk_level,
        confidence=confidence,
        trace_json=trace,
        facts_json=_sanitize_json(facts),
        engine_version=ENGINE_VERSION,
        final_message=final_message,
        created_at=datetime.utcnow(),
    )
    db.session.add(run)

    assessment.status = "COMPLETED"
    assessment.engine_version = ENGINE_VERSION
    assessment.completed_at = datetime.utcnow()
    return run


def get_ranked_candidates(assessment: Assessment, limit: int = 3) -> Dict[str, Any]:
    result = _build_candidate_rows(assessment)
    candidates = result["candidates"]
    grouped = _group_candidates(candidates, limit=limit)

    next_symptom = _next_symptom_from_rules(assessment.id, result["inference"])
    next_questions = _build_next_best_questions([next_symptom.id] if next_symptom else [])

    likely_payload = [_candidate_payload(item) for item in grouped["likely_conditions"]]
    possible_payload = [_candidate_payload(item) for item in grouped["possible_conditions"]]
    top_flat = likely_payload + possible_payload

    return {
        "candidates": top_flat[:limit] if limit > 0 else top_flat,
        "likely_conditions": likely_payload,
        "possible_conditions": possible_payload,
        "next_best_questions": next_questions,
    }


def get_next_symptom(assessment: Assessment, excluded_ids: Optional[set] = None) -> Optional[Symptom]:
    inference, _, _ = _inference_for_assessment(assessment.id)
    return _next_symptom_from_rules(assessment.id, inference, excluded_ids=excluded_ids)


def finalize_if_ready(assessment: Assessment) -> Optional[DiagnosisRun]:
    inference, _, _ = _inference_for_assessment(assessment.id)
    best_row = inference.get("best_row")
    if not best_row or not inference.get("finalizable"):
        return None

    next_symptom = _next_symptom_from_rules(assessment.id, inference)
    if next_symptom:
        return None

    return run_diagnosis_now(assessment)


def ensure_fallback_result(assessment: Assessment) -> DiagnosisRun:
    existing = DiagnosisRun.query.filter_by(assessment_id=assessment.id).order_by(DiagnosisRun.id.desc()).first()
    if existing:
        return existing

    result = _build_candidate_rows(assessment)
    candidates = result["candidates"]
    final_message = _final_message(candidates, result["labs"])
    trace = _build_run_trace(
        candidates,
        result["inference"],
        result["facts"],
        final_message,
        result["labs"],
    )

    _persist_assessment_results(assessment, candidates)
    _persist_rule_results(assessment, result["inference"])
    run = _create_run_record(
        assessment,
        (candidates[0] if candidates else None),
        trace,
        final_message,
        result["facts"],
    )
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
    result = _build_candidate_rows(assessment)
    candidates = result["candidates"]

    final_message = _final_message(candidates, result["labs"])
    trace = _build_run_trace(
        candidates,
        result["inference"],
        result["facts"],
        final_message,
        result["labs"],
    )

    _persist_assessment_results(assessment, candidates)
    _persist_rule_results(assessment, result["inference"])
    run = _create_run_record(
        assessment,
        (candidates[0] if candidates else None),
        trace,
        final_message,
        result["facts"],
    )

    db.session.commit()
    return run


def get_diagnosis_detail(assessment: Assessment, disease_id: int) -> Optional[Dict[str, Any]]:
    row = AssessmentDiagnosisResult.query.filter_by(
        assessment_id=assessment.id,
        disease_id=disease_id,
    ).first()
    if row:
        payload = _candidate_payload_from_row(row, include_trace=True)
        payload["assessment_id"] = assessment.id
        return payload

    result = _build_candidate_rows(assessment)
    for candidate in result["candidates"]:
        if int(candidate.get("disease_id") or 0) == int(disease_id):
            payload = _candidate_payload(candidate, include_trace=True)
            payload["assessment_id"] = assessment.id
            return payload
    return None


def get_assessment_diagnosis_payload(assessment: Assessment) -> Dict[str, Any]:
    rows = _results_from_db(assessment.id)

    candidates: List[Dict[str, Any]] = []
    for row in rows:
        candidates.append(_candidate_payload_from_row(row))

    grouped = {
        "likely_conditions": [item for item in candidates if item.get("evidence_level") == "HIGH"],
        "possible_conditions": [
            item
            for item in candidates
            if item.get("evidence_level") in {"MODERATE", "LOW"}
        ],
    }

    primary = candidates[0] if candidates else None
    return {
        "primary_disease": primary,
        "primary_confidence": (primary.get("confidence") if primary else None),
        "primary_risk_level": (primary.get("risk_level") if primary else None),
        "likely_conditions": grouped["likely_conditions"],
        "possible_conditions": grouped["possible_conditions"],
        "candidates": candidates,
    }
