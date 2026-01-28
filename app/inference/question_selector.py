from collections import Counter, defaultdict
from typing import Dict, Optional, Tuple, List

from app.models import Assessment, AssessmentAnswer, AssessmentMetric, Rule, Symptom

BASE_SYMPTOM_CODES = {
    "polyuria",
    "polydipsia",
    "polyphagia",
    "weight_loss",
    "fatigue",
    "blurred_vision",
    "slow_healing",
    "tingling",
    "recurrent_infections",
    "darkened_skin",
    "family_history",
    "high_bp",
    "overweight",
    "inactive",
    "gestational_diabetes",
    "prediabetes_history",
}

DERIVED_SYMPTOM_CODES = {
    "classic_diabetes_symptoms",
    "severe_symptoms",
    "metabolic_risk",
    "lifestyle_risk",
    "multiple_symptoms",
    "age_over_45",
    "age_over_35",
    "has_fatigue",
    "has_thirst",
    "obese",
}

DERIVED_DEPENDENCIES = {
    "classic_diabetes_symptoms": ["polyuria", "polydipsia", "polyphagia", "weight_loss"],
    "severe_symptoms": ["weight_loss", "blurred_vision", "slow_healing", "recurrent_infections", "tingling"],
    "metabolic_risk": ["overweight", "high_bp", "inactive"],
    "lifestyle_risk": ["overweight", "inactive"],
    "multiple_symptoms": [
        "polyuria",
        "polydipsia",
        "polyphagia",
        "weight_loss",
        "fatigue",
        "blurred_vision",
        "slow_healing",
        "tingling",
        "recurrent_infections",
    ],
    "has_fatigue": ["fatigue"],
    "has_thirst": ["polydipsia"],
    "obese": ["overweight"],
    "age_over_45": [],
    "age_over_35": [],
}


def _facts_for_assessment(assessment_id: int) -> Dict[int, bool]:
    rows = AssessmentAnswer.query.filter_by(assessment_id=assessment_id).all()
    base_facts = {r.symptom_id: bool(r.answer_bool) for r in rows}
    derived = _derive_facts(assessment_id, base_facts)
    if derived:
        base_facts.update(derived)
    return base_facts


def _derive_facts(assessment_id: int, base_facts: Dict[int, bool]) -> Dict[int, bool]:
    codes_needed = BASE_SYMPTOM_CODES.union(DERIVED_SYMPTOM_CODES)
    code_map = {s.code: s.id for s in Symptom.query.filter(Symptom.code.in_(codes_needed)).all()}
    if not code_map:
        return {}

    base_id_to_code = {code_map[code]: code for code in BASE_SYMPTOM_CODES if code in code_map}
    derived: Dict[int, bool] = {}

    def base_value(code: str) -> Optional[bool]:
        sid = code_map.get(code)
        if sid is None or sid not in base_facts:
            return None
        return bool(base_facts[sid])

    def set_derived(code: str, value: Optional[bool]):
        if value is None:
            return
        sid = code_map.get(code)
        if sid is None:
            return
        derived[sid] = bool(value)

    metric = AssessmentMetric.query.filter_by(assessment_id=assessment_id).first()
    if metric and metric.age_years is not None:
        set_derived("age_over_45", metric.age_years >= 45)
        set_derived("age_over_35", metric.age_years >= 35)

    obese_set = None
    if metric and metric.height_cm and metric.weight_kg:
        height_m = metric.height_cm / 100.0
        if height_m > 0:
            bmi = metric.weight_kg / (height_m * height_m)
            obese_set = bmi >= 30
            set_derived("obese", obese_set)
    if obese_set is None:
        overweight_val = base_value("overweight")
        if overweight_val is not None:
            set_derived("obese", overweight_val)

    set_derived("has_fatigue", base_value("fatigue"))
    set_derived("has_thirst", base_value("polydipsia"))

    polyuria = base_value("polyuria")
    polydipsia = base_value("polydipsia")
    polyphagia = base_value("polyphagia")
    weight_loss = base_value("weight_loss")

    if polyuria is True and polydipsia is True and (polyphagia is True or weight_loss is True):
        set_derived("classic_diabetes_symptoms", True)
    elif polyuria is False or polydipsia is False:
        set_derived("classic_diabetes_symptoms", False)
    elif polyphagia is False and weight_loss is False and polyuria is True and polydipsia is True:
        set_derived("classic_diabetes_symptoms", False)

    blurred = base_value("blurred_vision")
    slow_healing = base_value("slow_healing")
    infections = base_value("recurrent_infections")
    tingling = base_value("tingling")

    if (
        weight_loss is True
        and (blurred is True or slow_healing is True)
        and (infections is True or tingling is True)
    ):
        set_derived("severe_symptoms", True)
    else:
        if weight_loss is False:
            set_derived("severe_symptoms", False)
        elif (blurred is False and slow_healing is False) or (infections is False and tingling is False):
            set_derived("severe_symptoms", False)

    overweight = base_value("overweight")
    high_bp = base_value("high_bp")
    inactive = base_value("inactive")

    if overweight is True and high_bp is True and inactive is True:
        set_derived("metabolic_risk", True)
    elif overweight is False or high_bp is False or inactive is False:
        set_derived("metabolic_risk", False)

    if overweight is True and inactive is True:
        set_derived("lifestyle_risk", True)
    elif overweight is False or inactive is False:
        set_derived("lifestyle_risk", False)

    symptom_group = [
        "polyuria",
        "polydipsia",
        "polyphagia",
        "weight_loss",
        "fatigue",
        "blurred_vision",
        "slow_healing",
        "tingling",
        "recurrent_infections",
    ]
    yes_count = 0
    answered_count = 0
    for code in symptom_group:
        value = base_value(code)
        if value is None:
            continue
        answered_count += 1
        if value:
            yes_count += 1

    if yes_count >= 2:
        set_derived("multiple_symptoms", True)
    elif answered_count >= 2 and yes_count == 0:
        set_derived("multiple_symptoms", False)

    return derived


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
    derived_rows = Symptom.query.filter(Symptom.is_derived.is_(True)).all()
    derived_ids = {s.id for s in derived_rows}
    derived_id_to_code = {s.id: s.code for s in derived_rows}
    base_code_map = {
        s.code: s.id
        for s in Symptom.query.filter(Symptom.code.in_(BASE_SYMPTOM_CODES)).all()
    }

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
            expected_val = bool(c.expected_value)
            if sid in derived_ids:
                derived_code = derived_id_to_code.get(sid)
                for dep_code in DERIVED_DEPENDENCIES.get(derived_code, []):
                    dep_id = base_code_map.get(dep_code)
                    if not dep_id:
                        continue
                    if dep_id in answered_ids or dep_id in seen_in_rule:
                        continue
                    seen_in_rule.add(dep_id)
                    coverage[dep_id] += 1
                    expected_tf[dep_id][expected_val] += 1
                continue

            if sid in answered_ids or sid in seen_in_rule:
                continue
            seen_in_rule.add(sid)

            coverage[sid] += 1
            expected_tf[sid][expected_val] += 1

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
