# Inference Service Design (Rule-Based Diabetes Expert System)

This design uses the logical entities:
- `assessments`
- `assessment_answers`
- `diseases`
- `findings`
- `rule_sets`
- `rules`
- `rule_conditions`
- `assessment_rule_results`
- `assessment_diagnosis_results`

## 1) Engine Pipeline

1. Load active context
- Load `assessment` by id.
- Load latest active `rule_set` and its active `rules`.
- Load active `diseases`.
- Load `findings` metadata (`input_type`, `importance_weight`, lab markers, options, ranges).
- Load `assessment_answers` for the assessment.

2. Build base fact map
- Build a dictionary keyed by `finding_code`.
- For each answer, preserve tri-state for booleans:
  - `state = true` -> fact value `TRUE`
  - `state = false` -> fact value `FALSE`
  - `state = unknown` -> fact value `UNKNOWN`
- For labs, if `is_provided = false`, mark as `MISSING_LAB` (not FALSE).

3. Derive secondary facts
- Deterministic derivations before rule evaluation, for example:
  - If sex is male -> `pregnant = FALSE`.
  - BMI from height/weight -> bmi group flags (`bmi_overweight`, `bmi_obese`).
  - Symptom cluster counts (e.g., count of classic symptoms).
- Write derived facts into in-memory fact map with `source = DERIVED`.

4. Prepare rule execution order
- Sort rules by:
  - `priority DESC`
  - `id ASC` (stable tie-break)

5. Evaluate each rule
- Evaluate all `rule_conditions` of rule using supported operators:
  - `EQ`, `NEQ`, `GT`, `GTE`, `LT`, `LTE`, `BETWEEN`, `IN`, `PRESENT`
- Apply `is_required` and `rules.min_required_matches` (k-of-n):
  - required conditions must not contradict.
  - for optional conditions, at least `k` optional matches if `k` is set.
- Apply rule-type semantics:
  - `SCREENING`: soft scoring (+score, +confidence increments).
  - `DIAGNOSTIC`: hard confirmation candidate when matched.
  - `EXCLUSION`: block/reduce disease score/confidence.
- Persist per-rule explainability row in `assessment_rule_results`:
  - `matched_state` (`match`/`no_match`/`unknown`)
  - `score_added`
  - `confidence_added`
  - `missing_findings_json`
  - `explain_text`

6. Aggregate disease outcomes
- Maintain per-disease accumulator:
  - `score_total`
  - evidence list
  - missing key facts list
  - candidate `confirmed_by_rule_id`
- Merge rule impacts into the accumulator.

7. Compute confidence per disease
- Compute completeness from findings:
  - denominator: sum of `findings.importance_weight` for relevant findings
  - numerator: sum weights for provided (non-UNKNOWN and, for labs, `is_provided=true`) findings
  - `completeness = numerator / denominator` (0..1)
- Combine base evidence confidence with completeness.
- If disease is not hard-confirmed and labs are missing:
  - `confidence = min(confidence, rules.max_conf_without_labs)` using the most restrictive applicable cap.

8. Determine final status per disease
- Suggested mapping:
  - hard diagnostic matched -> `CONFIRMED`
  - else high score/confidence -> `HIGH_LIKELIHOOD`
  - else medium evidence -> `POSSIBLE`
  - else -> `UNLIKELY`

9. Persist ranked disease results
- Upsert one row per disease in `assessment_diagnosis_results`:
  - `assessment_id`, `disease_id`
  - `score_total`, `confidence`, `status`
  - `confirmed_by_rule_id`
  - `top_evidence_json`
  - `missing_key_facts_json`
- Sort ranking by `score_total DESC`, then `confidence DESC`.

10. Mark assessment engine metadata
- Save `assessments.engine_version` and completion timestamps/status when appropriate.

## 2) Pseudocode

```python
def run_engine(assessment_id: int):
    assessment = load_assessment(assessment_id)
    ruleset = load_active_ruleset()
    rules = load_active_rules(ruleset.id, order_by=["priority DESC", "id ASC"])
    findings = load_active_findings()
    diseases = load_active_diseases()
    answers = load_assessment_answers(assessment_id)

    facts = build_base_facts(answers, findings)  # keeps TRUE/FALSE/UNKNOWN and MISSING_LAB
    derived = derive_facts(facts, findings)
    facts.update(derived)

    disease_state = init_disease_accumulators(diseases)

    for rule in rules:
        rr = evaluate_rule(rule, facts, findings)
        save_assessment_rule_result(
            assessment_id=assessment_id,
            rule_id=rule.id,
            matched_state=rr.matched_state,
            score_added=rr.score_added,
            confidence_added=rr.confidence_added,
            missing_findings_json=rr.missing_findings,
            explain_text=build_explanation(rule, rr),
        )

        apply_rule_impact(disease_state, rule, rr)  # screening add, diagnostic confirm, exclusion reduce/block

        if rule.stop_engine_on_match and rr.matched_state == "match":
            break

    outputs = []
    for disease_id, ds in disease_state.items():
        confidence = compute_confidence(ds, facts, findings)
        status = classify_status(ds, confidence)

        outputs.append({
            "disease_id": disease_id,
            "score_total": ds.score_total,
            "confidence": confidence,
            "status": status,
            "confirmed_by_rule_id": ds.confirmed_by_rule_id,
            "top_evidence_json": ds.top_evidence,
            "missing_key_facts_json": ds.missing_key_facts,
        })

    ranked = sort_desc(outputs, keys=["score_total", "confidence"])
    save_assessment_diagnosis_results(assessment_id, ranked)
    update_assessment_engine_metadata(assessment_id)
    return ranked
```

```python
def evaluate_rule(rule, facts, findings):
    conds = load_rule_conditions(rule.id)

    required = [c for c in conds if c.is_required]
    optional = [c for c in conds if not c.is_required]

    required_ok = True
    matched_optional = 0
    missing = []
    evidence = []

    for c in required:
        out = eval_condition(c, facts)
        if out.state == "contradiction":
            required_ok = False
        if out.state == "unknown":
            missing.append(c.finding_code)
        if out.state == "match":
            evidence.append(out)

    for c in optional:
        out = eval_condition(c, facts)
        if out.state == "match":
            matched_optional += 1
            evidence.append(out)
        elif out.state == "unknown":
            missing.append(c.finding_code)

    k = rule.min_required_matches if rule.min_required_matches is not None else 0
    optional_ok = (matched_optional >= k)

    if not required_ok:
        matched_state = "no_match"
    elif required_ok and optional_ok:
        matched_state = "match"
    else:
        matched_state = "unknown"

    score_added, confidence_added = score_rule(rule, matched_state, evidence, missing)
    return RuleEval(matched_state, score_added, confidence_added, missing, evidence)
```

```python
def eval_condition(cond, facts):
    v = facts.get(cond.finding_code, UNKNOWN)

    # UNKNOWN means unanswered / not provided lab / derived unknown
    if v is UNKNOWN:
        return CondEval(state="unknown")

    op = cond.operator
    vals = cond.values if cond.values is not None else cond.value

    if op == "PRESENT":
        ok = (v is not UNKNOWN)
    elif op == "EQ":
        ok = (v == vals)
    elif op == "NEQ":
        ok = (v != vals)
    elif op == "GT":
        ok = (to_num(v) > to_num(vals))
    elif op == "GTE":
        ok = (to_num(v) >= to_num(vals))
    elif op == "LT":
        ok = (to_num(v) < to_num(vals))
    elif op == "LTE":
        ok = (to_num(v) <= to_num(vals))
    elif op == "BETWEEN":
        lo, hi = vals[0], vals[1]
        ok = (to_num(lo) <= to_num(v) <= to_num(hi))
    elif op == "IN":
        ok = (v in vals)
    else:
        ok = False

    if cond.negate:
        ok = not ok

    return CondEval(state=("match" if ok else "contradiction"), actual=v, expected=vals)
```

```python
def compute_confidence(disease_state, facts, findings):
    relevant = select_relevant_findings_for_disease(disease_state, findings)

    denom = sum(f.importance_weight for f in relevant)
    num = 0.0
    labs_missing = False

    for f in relevant:
        a = facts.get(f.code, UNKNOWN)
        provided = (a is not UNKNOWN)

        # if this finding is a lab and answer.is_provided == false, treat as missing
        if is_lab_finding(f) and is_lab_not_provided(f.code, facts):
            provided = False
            labs_missing = True

        if provided:
            num += f.importance_weight

    completeness = 0.0 if denom == 0 else (num / denom)

    # blend evidence confidence with completeness
    base = disease_state.evidence_confidence  # from matched rules
    confidence = clamp(0.0, 1.0, 0.7 * base + 0.3 * completeness)

    # cap when unconfirmed and labs missing
    if disease_state.confirmed_by_rule_id is None and labs_missing:
        cap = disease_state.max_conf_without_labs_cap  # min applicable cap among supporting rules
        if cap is not None:
            confidence = min(confidence, cap)

    return confidence
```

```python
def build_explanation(rule, rule_eval):
    return {
        "rule_id": rule.id,
        "rule_type": rule.rule_type,
        "priority": rule.priority,
        "matched_state": rule_eval.matched_state,
        "score_added": rule_eval.score_added,
        "confidence_added": rule_eval.confidence_added,
        "matched_conditions": [e.to_dict() for e in rule_eval.evidence],
        "missing_findings": rule_eval.missing,
        "reason": make_human_reason(rule, rule_eval),
    }
```

## 3) UNKNOWN Handling (Critical Behavior)

Principle: `UNKNOWN` is not `FALSE`.

Rules:
- Boolean tri-state:
  - `TRUE` means explicitly present/yes.
  - `FALSE` means explicitly absent/no.
  - `UNKNOWN` means unanswered/insufficient evidence.
- For lab findings:
  - `is_provided=false` => value is missing (`UNKNOWN`/`MISSING_LAB`), never FALSE.
- Condition evaluation:
  - If fact is `UNKNOWN`, condition result is `unknown` (not contradiction), except hard `PRESENT` which still returns `unknown` when missing.
- Rule evaluation:
  - Required contradiction -> `no_match`.
  - Required unknown (without contradiction) -> rule `unknown`.
  - Unknown optional conditions do not count as matches.
- Scoring:
  - Unknown should not add score.
  - Unknown should increase missing findings logs.
- Confidence:
  - Unknown lowers completeness because weighted coverage is smaller.
  - Missing labs trigger confidence cap for unconfirmed outputs.

This preserves medical safety semantics: lack of data reduces certainty instead of creating false negatives.

## 4) Rule Evaluation Logic (Implementation Notes)

This section documents the concrete behavior implemented in `app/inference/rule_eval.py`.

### 4.1 Condition State Contract

- Every condition returns one of: `MATCH`, `NO_MATCH`, `UNKNOWN`.
- `UNKNOWN` rules:
  - Boolean answer with `state=unknown` (or no usable boolean value) -> `UNKNOWN`.
  - Numeric/lab answer with `is_provided=false` or null numeric value -> `UNKNOWN`.
  - Missing finding in fact map -> `UNKNOWN`.
- `UNKNOWN` never implies `NO_MATCH`.

### 4.2 Rule-Type Behavior

- `SCREENING`
  - Soft scoring.
  - `score_added` is the sum of `condition.score_points` for matched conditions only.
  - Uses k-of-n via `rules.min_required_matches` across required + optional conditions.
  - If a required condition is explicit `NO_MATCH`, rule is `no_match`.
  - If k is not reached and any unknown exists, rule is `unknown`.
- `DIAGNOSTIC`
  - Hard confirm.
  - `match` only when all required conditions match (and k-of-n threshold is met when configured).
  - Any required `UNKNOWN` -> rule `unknown`.
  - Partial matches do not add score.
- `EXCLUSION`
  - Block/penalty semantics.
  - `match` when required conditions match (and k threshold if configured).
  - Required unknown -> `unknown`.
  - On match, `score_added` is negative penalty (or zero if no points configured).

### 4.3 Pseudocode

```python
def eval_condition(cond, facts):
    fact = lookup_fact(cond.finding_code or cond.symptom_code or cond.symptom_id)
    if fact is missing:
        return UNKNOWN

    value, state, is_provided = unpack(fact)
    if state == "unknown":
        return UNKNOWN

    if cond.input_type == "BOOLEAN" and value is None:
        return UNKNOWN
    if cond.input_type == "NUMBER" and (is_provided is False or value is None):
        return UNKNOWN

    # evaluate EQ/NEQ/GT/GTE/LT/LTE/BETWEEN/IN/PRESENT
    matched = compare(cond.operator, value, cond.values or cond.value)

    if cond.negate and matched is not UNKNOWN:
        matched = not matched

    return MATCH if matched else NO_MATCH
```

```python
def eval_rule(rule, facts):
    cond_results = [eval_condition(c, facts) for c in rule.conditions]

    matched = [r for r in cond_results if r.state == MATCH]
    unknown = [r for r in cond_results if r.state == UNKNOWN]
    no_match = [r for r in cond_results if r.state == NO_MATCH]

    required = [r for r in cond_results if r.is_required]
    required_unknown = any(r.state == UNKNOWN for r in required)
    required_no_match = any(r.state == NO_MATCH for r in required)

    k = normalize_k(rule.min_required_matches, default=len(required) or len(cond_results))
    enough_matches = len(matched) >= k

    if rule.rule_type == "SCREENING":
        if required_no_match:
            state = "no_match"
        elif enough_matches:
            state = "match"
        elif unknown:
            state = "unknown"
        else:
            state = "no_match"
        score_added = sum(r.score_points for r in matched)

    elif rule.rule_type == "DIAGNOSTIC":
        if required_no_match:
            state = "no_match"
        elif required_unknown:
            state = "unknown"
        elif all_required_matched(required) and enough_matches:
            state = "match"
        elif unknown:
            state = "unknown"
        else:
            state = "no_match"
        score_added = sum(r.score_points for r in matched) if state == "match" else 0

    elif rule.rule_type == "EXCLUSION":
        if required_no_match:
            state = "no_match"
        elif required_unknown:
            state = "unknown"
        elif required_match(required) and enough_matches:
            state = "match"
        elif unknown:
            state = "unknown"
        else:
            state = "no_match"
        score_added = -abs(sum(r.score_points for r in matched)) if state == "match" else 0

    return RuleEval(
        matched_state=state,
        score_added=score_added,
        missing_findings=[r.finding_code for r in unknown],
        matched_required_count=count_required_matches(required),
        total_required_count=len(required),
        matched_conditions=[r.detail for r in matched],
        explain_text=build_explanation(...),
    )
```

```python
def apply_rule_to_disease(disease_state, rule, rule_eval):
    if rule_eval.matched_state == "match":
        if rule.rule_type == "SCREENING":
            disease_state.score_total += rule_eval.score_added
        elif rule.rule_type == "DIAGNOSTIC":
            disease_state.score_total += rule_eval.score_added
            disease_state.confirmed_by_rule_id = rule.id
        elif rule.rule_type == "EXCLUSION":
            disease_state.blocked = True
            disease_state.score_total += rule_eval.score_added
    elif rule_eval.matched_state == "unknown":
        disease_state.missing_key_facts.extend(rule_eval.missing_findings)
    return disease_state
```

### 4.4 Worked Examples

1. Screening with missing BMI:
- Rule: `SCREENING`, `min_required_matches=2`
- Conditions: `family_history == true` (required), `bmi >= 25` (optional), `thirst == true` (optional)
- Facts: `family_history=true`, `thirst=true`, `bmi` missing (`is_provided=false`)
- Outcome:
  - Condition states: `MATCH`, `MATCH`, `UNKNOWN`
  - Matched count = 2 meets k=2
  - Rule = `match`
  - Score adds only matched points; BMI contributes 0 and is listed in `missing_findings`.

2. Diagnostic with missing FBS:
- Rule: `DIAGNOSTIC`
- Required conditions: `fbs >= 126`, `polyuria == true`
- Facts: `polyuria=true`, `fbs` missing (`is_provided=false`)
- Outcome:
  - `fbs` condition = `UNKNOWN`
  - Required unknown exists
  - Rule = `unknown` (not `no_match`, not confirmed).

3. Exclusion for GDM when pregnant=false:
- Rule: `EXCLUSION` for GDM pathway
- Required condition: `pregnant == false`
- Facts: `pregnant=false`
- Outcome:
  - Condition = `MATCH`
  - Rule = `match`
  - Exclusion applies block/penalty and should suppress or reduce GDM ranking.

## 5) Confidence Module Design

Goal:
- Confidence means **how sure the system is given available evidence quality/completeness**, not probability of disease occurrence.

Inputs per disease:
- Disease-scoped rules (`SCREENING`, `DIAGNOSTIC`, `EXCLUSION`) and their confidence policy fields.
- Rule results (`matched_state`, `score_added`, matched coverage).
- Findings metadata (`input_type`, `importance_weight`).
- Assessment answers (tri-state + `is_provided` for labs).
- Current disease `status` (`confirmed`, `high`, `possible`, `unlikely`).

### 5.1 Step-by-step algorithm

1. Compute relevant findings:
- Collect all finding codes referenced by the disease's rule conditions.

2. Compute completeness:
- Denominator = sum of `importance_weight` for relevant findings.
- Numerator = sum weights for answered findings only:
  - Boolean answered only if `TRUE` or `FALSE`.
  - Boolean `UNKNOWN` is not answered.
  - Number/lab answered only if `is_provided=true` and value is not null.
- `completeness_pct = (answered_weight / total_weight) * 100`.

3. Compute optional evidence bonus:
- Count strong matched `SCREENING` rules (for example, fully matched required conditions).
- Add bonus (default `+5` per strong rule).
- Cap bonus by `rules.confidence_bonus_max` (conservative cap across contributing rules).

4. Compute raw confidence:
- `confidence_raw_pct = min(100, completeness_pct + bonus_pct)`.

5. Detect missing key labs:
- From relevant findings, check if key labs are missing (e.g., `FBS`, `HBA1C`, `OGTT`).
- Store in `missing_key_facts_json`.

6. Apply caps/floors:
- If disease status is not `CONFIRMED` and key labs missing:
  - `confidence_final = min(confidence_raw, rules.max_conf_without_labs)` using the most restrictive cap.
- If diagnostic rule confirms:
  - `confidence_final = max(confidence_raw, rules.base_confidence)` using matched diagnostic rules.

7. Persist:
- Save final confidence into `assessment_diagnosis_results.confidence`.
- Save missing key labs in `missing_key_facts_json`.

### 5.2 Required pseudocode

```python
def compute_relevant_findings(disease_id, rules):
    relevant = set()
    for rule in rules:
        if rule.disease_id not in {None, disease_id}:
            continue
        for cond in rule.conditions:
            code = cond.finding_code or cond.symptom_code
            if code:
                relevant.add(code)
    return relevant
```

```python
def compute_completeness(relevant_codes, findings_by_code, answers_by_code):
    total_weight = 0
    answered_weight = 0
    for code in relevant_codes:
        finding = findings_by_code[code]
        w = finding.importance_weight
        total_weight += w

        ans = answers_by_code.get(code)
        if finding.input_type == "BOOLEAN":
            answered = ans.state in {"true", "false"}
        elif finding.input_type == "NUMBER":
            answered = (ans.is_provided is True) and (ans.value is not None)
        else:
            answered = ans is not None and ans.is_provided is True

        if answered:
            answered_weight += w

    completeness_pct = 0 if total_weight == 0 else (answered_weight / total_weight) * 100
    return completeness_pct
```

```python
def compute_evidence_bonus(disease_id, rules, matched_rule_results):
    strong_count = 0
    bonus_caps = []
    for rr in matched_rule_results:
        if rr.matched_state != "match":
            continue
        rule = rules_by_id[rr.rule_id]
        if rule.rule_type != "screening":
            continue
        if is_strong(rule, rr):
            strong_count += 1
            if rule.confidence_bonus_max is not None:
                bonus_caps.append(to_pct(rule.confidence_bonus_max))

    raw_bonus = strong_count * 5
    cap = min(bonus_caps) if bonus_caps else raw_bonus
    return min(raw_bonus, cap)
```

```python
def apply_caps(status, confidence_raw_pct, rules, matched_rule_results, missing_key_labs):
    conf = confidence_raw_pct

    if status.upper() != "CONFIRMED" and missing_key_labs:
        caps = [to_pct(r.max_conf_without_labs) for r in rules if r.max_conf_without_labs is not None]
        if caps:
            conf = min(conf, min(caps))

    if status.upper() == "CONFIRMED":
        diagnostic_floors = []
        for rr in matched_rule_results:
            if rr.matched_state != "match":
                continue
            rule = rules_by_id[rr.rule_id]
            if rule.rule_type == "diagnostic" and rule.base_confidence is not None:
                diagnostic_floors.append(to_pct(rule.base_confidence))
        if diagnostic_floors:
            conf = max(conf, max(diagnostic_floors))

    return conf
```

### 5.3 Worked example (missing labs cap behavior)

Scenario:
- Disease: Type 2 Diabetes (`status=possible`, not confirmed).
- Relevant findings: `polyuria`(w=3), `polydipsia`(w=2), `BMI`(w=2), `FBS`(w=5), `HBA1C`(w=5).
- Answers:
  - `polyuria=true`, `polydipsia=true`, `BMI=31` (provided),
  - `FBS` missing (`is_provided=false`),
  - `HBA1C` unknown/not provided.
- Matched screening rules: 2 strong -> bonus raw `+10`.
- Rule caps:
  - `confidence_bonus_max=0.10` (10%),
  - `max_conf_without_labs=0.70` (70%).

Computation:
- Total weight = `3+2+2+5+5 = 17`.
- Answered weight = `3+2+2 = 7`.
- Completeness = `7/17*100 = 41.18%`.
- Bonus = `min(10%, 10%) = 10%`.
- Raw confidence = `41.18 + 10 = 51.18%`.
- Missing key labs = `["FBS", "HBA1C"]`.
- Not confirmed + key labs missing -> apply cap 70%.
- Final confidence = `min(51.18, 70) = 51.18%` (cap not binding in this case).

If raw confidence had been `78%`, final would be capped to `70%` until labs are provided or diagnosis is confirmed by diagnostic rule.

## 6) Real Clinical Thresholds -> DIAGNOSTIC Rule Encoding

This section maps ADA diagnostic thresholds into your rule engine schema.

### 6.1 ADA criteria for non-pregnant adults (diagnosis)

Diabetes (any one criterion):
- FPG/FBS `>=126 mg/dL`
- A1C `>=6.5%`
- 2-hour 75 g OGTT `>=200 mg/dL`
- Random plasma glucose `>=200 mg/dL` **with classic hyperglycemia symptoms or hyperglycemic crisis**

Prediabetes:
- FPG/FBS `100–125 mg/dL`
- A1C `5.7–6.4%`
- 2-hour 75 g OGTT `140–199 mg/dL`

Normal/negative-evidence ranges for rule modeling:
- FPG `<100 mg/dL`
- A1C `<5.7%`

Note:
- The “normal” lines above are inference for rule design from ADA prediabetes lower bounds.

### 6.2 Confirmatory testing concept

In the absence of unequivocal hyperglycemia (for example, no hyperglycemic crisis and no classic symptomatic presentation with very high random glucose), ADA guidance requires confirmation:
- either two abnormal results from different tests at the same time, or
- the same abnormal test on a different day.

Rule engine implication:
- A single abnormal lab can produce a strong diagnostic result,
- but you should represent `confirmation_pending` when criteria requiring repeat confirmation are not yet fulfilled.

### 6.3 Gestational diabetes thresholds

Preferred 1-step 75 g OGTT (IADPSG):
- Fasting `>=92 mg/dL`
- 1 hour `>=180 mg/dL`
- 2 hour `>=153 mg/dL`
- Diagnosis if **any one** value is abnormal.

Alternative 2-step concept:
- Step 1: 50 g nonfasting screen (GLT), if positive then
- Step 2: 100 g OGTT; diagnosis typically requires **2 or more abnormal values**.

### 6.4 How to encode with your DB fields

Use:
- `rules.rule_type = diagnostic`
- `rules.min_required_matches` for “any of these” or “2+ abnormal”
- `rule_conditions.operator` = `GTE`, `BETWEEN`, `PRESENT`

Patterns:
- “Any one of N thresholds” -> set threshold conditions as non-required, and `min_required_matches = 1`.
- “2+ abnormal values” -> threshold conditions non-required, and `min_required_matches = 2`.
- “Random glucose + symptoms” -> combine `random_glucose GTE 200` with symptoms condition(s), optionally adding `PRESENT` to enforce that symptom data was actually provided.

### 6.5 Example DIAGNOSTIC rules (DB-ready payload style)

1) Diabetes by FBS

```json
{
  "rule_code": "DX_DM_FBS_126",
  "title": "Diabetes diagnosis by fasting plasma glucose",
  "rule_type": "diagnostic",
  "disease_code": "T2DM",
  "priority": 95,
  "base_confidence": 0.92,
  "max_conf_without_labs": 0.70,
  "confidence_bonus_max": 0.00,
  "min_required_matches": 1,
  "conditions": [
    {"finding_code": "fbs", "operator": "GTE", "values": [126], "is_required": true, "score_points": 30}
  ]
}
```

2) Diabetes by HbA1c

```json
{
  "rule_code": "DX_DM_A1C_65",
  "title": "Diabetes diagnosis by HbA1c",
  "rule_type": "diagnostic",
  "disease_code": "T2DM",
  "priority": 95,
  "base_confidence": 0.92,
  "max_conf_without_labs": 0.70,
  "confidence_bonus_max": 0.00,
  "min_required_matches": 1,
  "conditions": [
    {"finding_code": "hba1c", "operator": "GTE", "values": [6.5], "is_required": true, "score_points": 30}
  ]
}
```

3) Prediabetes by HbA1c

```json
{
  "rule_code": "DX_PREDM_A1C_57_64",
  "title": "Prediabetes by HbA1c range",
  "rule_type": "diagnostic",
  "disease_code": "PREDM",
  "priority": 85,
  "base_confidence": 0.88,
  "max_conf_without_labs": 0.75,
  "confidence_bonus_max": 0.00,
  "min_required_matches": 1,
  "conditions": [
    {"finding_code": "hba1c", "operator": "BETWEEN", "values": [5.7, 6.4], "is_required": true, "score_points": 24}
  ]
}
```

4) GDM by 75 g OGTT (1-step IADPSG, any one abnormal)

```json
{
  "rule_code": "DX_GDM_75G_ANY1",
  "title": "Gestational diabetes by one-step 75 g OGTT",
  "rule_type": "diagnostic",
  "disease_code": "GDM",
  "priority": 98,
  "base_confidence": 0.94,
  "max_conf_without_labs": 0.70,
  "confidence_bonus_max": 0.00,
  "min_required_matches": 1,
  "conditions": [
    {"finding_code": "pregnant", "operator": "EQ", "values": [true], "is_required": true, "score_points": 0},
    {"finding_code": "ogtt75_fasting", "operator": "GTE", "values": [92], "is_required": false, "score_points": 20},
    {"finding_code": "ogtt75_1h", "operator": "GTE", "values": [180], "is_required": false, "score_points": 20},
    {"finding_code": "ogtt75_2h", "operator": "GTE", "values": [153], "is_required": false, "score_points": 20}
  ]
}
```

Optional example (random glucose + symptoms, uses `PRESENT`):

```json
{
  "rule_code": "DX_DM_RANDOM_200_SYMPT",
  "title": "Diabetes by random glucose with classic symptoms",
  "rule_type": "diagnostic",
  "disease_code": "T2DM",
  "priority": 97,
  "base_confidence": 0.95,
  "min_required_matches": 3,
  "conditions": [
    {"finding_code": "random_glucose", "operator": "PRESENT", "values": [], "is_required": true, "score_points": 0},
    {"finding_code": "random_glucose", "operator": "GTE", "values": [200], "is_required": true, "score_points": 25},
    {"finding_code": "classic_hyperglycemia_symptoms_count", "operator": "GTE", "values": [1], "is_required": true, "score_points": 20}
  ]
}
```

2-step GDM encoding concept (“2+ abnormal values”):
- Keep fasting/1h/2h/3h as non-required threshold conditions.
- Set `min_required_matches = 2`.
- Add one required condition indicating positive 50 g screen (or store screen result and require it in the rule).
