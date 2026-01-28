import json
from datetime import datetime
from typing import Dict, Optional, Tuple, List

from app.extensions import db
from app.models import Rule, Advice, Assessment, AssessmentResult
from app.inference.confidence import confidence_score
from app.inference.facts import facts_for_assessment

def rule_status(rule: Rule, facts: Dict[int, bool]) -> Tuple[str, list, list]:
    matched, missing = [], []
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
    facts = facts_for_assessment(assessment.id)

    rules: List[Rule] = (
        Rule.query.filter_by(is_active=True)
        .order_by(Rule.priority.desc(), Rule.id.asc())
        .all()
    )
    if not rules:
        return None

    max_conditions = max((len(r.conditions) for r in rules), default=1)

    statuses = []
    for r in rules:
        st, matched, missing = rule_status(r, facts)
        statuses.append((r, st, matched, missing))

    matched_rules = [(r, matched) for (r, st, matched, _) in statuses if st == "MATCHED"]
    if not matched_rules:
        return None

    best_rule, best_matched = matched_rules[0]  # already sorted by priority desc

    # Wait if higher-priority rule is still possible
    for (r, st, _, _) in statuses:
        if r.priority > best_rule.priority and st == "POSSIBLE":
            return None

    # Wait if same priority but more specific rule is still possible
    best_conditions = len(best_rule.conditions)
    for (r, st, _, _) in statuses:
        if r.priority == best_rule.priority and st == "POSSIBLE":
            if len(r.conditions) > best_conditions:
                return None

    # Confidence details
    conf = confidence_score(
        matched=len(best_matched),
        total=len(best_rule.conditions),
        max_total=max_conditions,
    )

    advice = Advice.query.filter_by(
        is_active=True,
        diagnosis_code=best_rule.diagnosis_code,
        risk_level=best_rule.risk_level
    ).first()

    explanation = {
        "fired_rule_id": best_rule.id,
        "fired_rule_name": best_rule.name,
        "matched_conditions": best_matched,
        "facts": {str(k): v for k, v in facts.items()},
        "confidence": conf,
        "advice_id": advice.id if advice else None,
    }

    result = AssessmentResult(
        assessment_id=assessment.id,
        diagnosis_code=best_rule.diagnosis_code,
        risk_level=best_rule.risk_level,
        explanation_json=json.dumps(explanation),
        created_at=datetime.utcnow(),
    )
    db.session.add(result)
    assessment.status = "COMPLETED"
    assessment.completed_at = datetime.utcnow()
    db.session.commit()

    return result
