import json
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, Optional, Tuple, List

from app.extensions import db
from app.models import (
    Rule,
    Advice,
    Assessment,
    AssessmentAnswer,
    AssessmentResult,
    Symptom,
)


def _facts_for_assessment(assessment_id: int) -> Dict[int, bool]:
    rows = AssessmentAnswer.query.filter_by(assessment_id=assessment_id).all()
    return {r.symptom_id: bool(r.answer_bool) for r in rows}


def _rule_status(rule: Rule, facts: Dict[int, bool]) -> Tuple[str, list, list]:
    """
    Returns (status, matched_conditions, missing_conditions)

    status:
    - "MATCHED": all conditions satisfied
    - "POSSIBLE": no contradictions, but missing facts
    - "IMPOSSIBLE": contradicted by existing facts
    """
    matched = []
    missing = []

    for cond in rule.conditions:
        sid = cond.symptom_id
        expected = bool(cond.expected_value)

        if sid not in facts:
            missing.append({"symptom_id": sid, "expected": expected})
            continue

        actual = facts[sid]
        if actual != expected:
            return "IMPOSSIBLE", [], []
        matched.append({"symptom_id": sid, "expected": expected, "actual": actual})

    if missing:
        return "POSSIBLE", matched, missing
    return "MATCHED", matched, []


def infer_if_complete(assessment: Assessment) -> Optional[AssessmentResult]:
    """
    Improved: do NOT finalize a lower-priority MATCHED rule if a higher-priority
    rule is still POSSIBLE, or if a more specific rule at the same priority is still POSSIBLE.
    """
    facts = _facts_for_assessment(assessment.id)

    rules: List[Rule] = (
        Rule.query.filter_by(is_active=True)
        .order_by(Rule.priority.desc(), Rule.id.asc())
        .all()
    )

    statuses = []
    for r in rules:
        status, matched, missing = _rule_status(r, facts)
        statuses.append((r, status, matched, missing))

    # Find best matched rule
    matched_rules = [(r, matched) for (r, st, matched, _) in statuses if st == "MATCHED"]
    if not matched_rules:
        return None

    best_rule, best_matched = matched_rules[0]  # already sorted by priority desc

    # Check if any higher priority rule is still POSSIBLE
    for (r, st, _, _) in statuses:
        if r.priority > best_rule.priority and st == "POSSIBLE":
            return None

    # If another rule shares priority but is more specific and still POSSIBLE, wait.
    best_conditions = len(best_rule.conditions)
    for (r, st, _, _) in statuses:
        if r.priority == best_rule.priority and st == "POSSIBLE":
            if len(r.conditions) > best_conditions:
                return None

    # Finalize best_rule
    explanation = {
        "fired_rule_id": best_rule.id,
        "fired_rule_name": best_rule.name,
        "matched_conditions": best_matched,
        "facts": {str(k): v for k, v in facts.items()},
    }

    advice = Advice.query.filter_by(
        is_active=True,
        diagnosis_code=best_rule.diagnosis_code,
        risk_level=best_rule.risk_level
    ).first()

    advice_id = advice.id if advice else None

    result = AssessmentResult(
        assessment_id=assessment.id,
        diagnosis_code=best_rule.diagnosis_code,
        risk_level=best_rule.risk_level,
        explanation_json=json.dumps({**explanation, "advice_id": advice_id}),
        created_at=datetime.utcnow(),
    )
    db.session.add(result)

    assessment.status = "COMPLETED"
    assessment.completed_at = datetime.utcnow()
    db.session.commit()

    return result


def infer_diagnosis(facts: Dict[int, bool]):
    matched_rules = []

    active_rules: List[Rule] = (
        Rule.query.filter_by(is_active=True)
        .order_by(Rule.priority.desc(), Rule.id.asc())
        .all()
    )

    for rule in active_rules:
        status, _, _ = _rule_status(rule, facts)
        if status == "MATCHED":
            matched_rules.append(rule)

    if matched_rules:
        matched_rules.sort(key=lambda r: r.priority, reverse=True)
        fired_rule = matched_rules[0]
        return {
            "diagnosis_code": fired_rule.diagnosis_code,
            "risk_level": fired_rule.risk_level,
            "fired_rule": fired_rule,
        }

    # FALLBACK
    return {
        "diagnosis_code": "DIABETES_RISK",
        "risk_level": "LOW",
        "fired_rule": None,
    }


def ensure_fallback_result(assessment: Assessment) -> AssessmentResult:
    """
    Create a fallback result if the assessment cannot proceed (no rules/questions).
    Safe to call multiple times; only creates a result if missing.
    """
    existing = AssessmentResult.query.filter_by(assessment_id=assessment.id).first()
    if existing:
        return existing

    facts = _facts_for_assessment(assessment.id)
    fallback = infer_diagnosis(facts)

    explanation = {
        "fired_rule_id": None,
        "fired_rule_name": None,
        "matched_conditions": [],
        "facts": {str(k): v for k, v in facts.items()},
    }

    result = AssessmentResult(
        assessment_id=assessment.id,
        diagnosis_code=fallback["diagnosis_code"],
        risk_level=fallback["risk_level"],
        explanation_json=json.dumps(explanation),
        created_at=datetime.utcnow(),
    )
    db.session.add(result)

    assessment.status = "COMPLETED"
    assessment.completed_at = datetime.utcnow()
    db.session.commit()

    return result


def next_question(assessment: Assessment) -> Optional[Symptom]:
    """
    Smart question selection:
    - Keep only rules that are still POSSIBLE given current facts.
    - Choose an unanswered symptom that best distinguishes remaining rules.
    Scoring:
      score = (coverage_weight * how many remaining rules include this symptom)
            + (balance_weight * how balanced expected True vs False is among remaining rules)
      Tie-breaker: Symptom.priority_order (lower number = earlier)
    """
    facts = _facts_for_assessment(assessment.id)
    answered_ids = set(facts.keys())

    rules = (
        Rule.query
        .filter_by(is_active=True)
        .order_by(Rule.priority.desc(), Rule.id.asc())
        .all()
    )
    if not rules:
        return None

    possible_rules: List[Rule] = []
    for r in rules:
        possible = True
        for c in r.conditions:
            sid = c.symptom_id
            expected = bool(c.expected_value)
            if sid in facts and facts[sid] != expected:
                possible = False
                break
        if possible:
            possible_rules.append(r)

    if not possible_rules:
        return None

    coverage = Counter()                 # symptom_id -> number of rules containing it
    expected_tf = defaultdict(Counter)   # symptom_id -> Counter({True: n, False: n})

    for r in possible_rules:
        seen_in_rule = set()
        for c in r.conditions:
            sid = c.symptom_id
            if sid in answered_ids or sid in seen_in_rule:
                continue
            seen_in_rule.add(sid)

            coverage[sid] += 1
            expected_tf[sid][bool(c.expected_value)] += 1

    if not coverage:
        return None

    candidates: List[Tuple[float, int]] = []  # (score, symptom_id)

    coverage_weight = 10.0
    balance_weight = 4.0

    for sid, cov in coverage.items():
        t = expected_tf[sid][True]
        f = expected_tf[sid][False]
        balance_score = min(t, f)
        score = (coverage_weight * cov) + (balance_weight * balance_score)
        candidates.append((score, sid))

    candidates.sort(key=lambda x: (-x[0], x[1]))
    top_score = candidates[0][0]
    top_ids = [sid for (sc, sid) in candidates if sc == top_score]

    symptom = (
        Symptom.query
        .filter(Symptom.id.in_(top_ids), Symptom.is_active.is_(True))
        .order_by(Symptom.priority_order.asc(), Symptom.id.asc())
        .first()
    )

    if not symptom:
        best_id = candidates[0][1]
        symptom = Symptom.query.get(best_id)

    return symptom
