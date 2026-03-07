from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


# Canonical key labs used to explain confidence limits.
KEY_LAB_ALIASES: Dict[str, Set[str]] = {
    "FBS": {"fbs", "fpg", "fasting_glucose", "fasting_plasma_glucose", "glucose_fasting"},
    "HBA1C": {"hba1c", "hb_a1c", "a1c", "glycated_hemoglobin"},
    "OGTT": {"ogtt", "oral_glucose_tolerance_test", "oral_glucose_tolerance"},
}


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            return default
    return default


def _as_pct(value: Any) -> Optional[float]:
    raw = _to_float(value)
    if raw is None:
        return None
    if raw <= 1.0:
        raw *= 100.0
    return max(0.0, min(100.0, raw))


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return None


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _rule_disease_id(rule: Any) -> Optional[int]:
    return _get_attr(rule, "disease_id")


def _rule_type(rule: Any) -> str:
    return str(_get_attr(rule, "rule_type", "screening") or "screening").strip().lower()


def _iter_conditions(rule: Any) -> Iterable[Any]:
    return _get_attr(rule, "conditions", []) or []


def _condition_code(condition: Any) -> Optional[str]:
    code = _get_attr(condition, "finding_code")
    if code:
        return str(code).strip()
    code = _get_attr(condition, "symptom_code")
    if code:
        return str(code).strip()
    return None


def _rule_id(rule: Any) -> Optional[int]:
    rid = _get_attr(rule, "id")
    try:
        return int(rid) if rid is not None else None
    except Exception:
        return None


def _finding_input_type(finding: Any) -> str:
    return str(_get_attr(finding, "input_type", "BOOLEAN") or "BOOLEAN").strip().upper()


def _finding_weight(finding: Any) -> float:
    weight = _to_float(_get_attr(finding, "importance_weight", 1.0), default=1.0) or 1.0
    return max(0.0, min(10.0, weight))


def _extract_answer(answer: Any) -> Tuple[Optional[str], Optional[bool], Any]:
    state = _get_attr(answer, "state")
    state = str(state).strip().lower() if state is not None else None

    is_provided = _get_attr(answer, "is_provided")
    if not isinstance(is_provided, bool):
        is_provided = _coerce_bool(is_provided)

    if isinstance(answer, dict):
        value = answer.get("value")
        if value is None:
            for key in ("value_bool", "value_number", "value_text", "value_json"):
                if key in answer and answer.get(key) is not None:
                    value = answer.get(key)
                    break
    else:
        value = None
        for key in ("value_bool", "value_number", "value_text", "value_json", "value"):
            field = getattr(answer, key, None)
            if field is not None:
                value = field
                break

    return state, is_provided, value


def _is_answered(finding: Any, answer: Any) -> bool:
    if answer is None:
        return False

    input_type = _finding_input_type(finding)
    state, is_provided, value = _extract_answer(answer)

    if input_type == "BOOLEAN":
        if state in {"true", "false"}:
            return True
        if state == "unknown":
            return False
        return _coerce_bool(value) is not None

    if input_type == "NUMBER":
        if is_provided is not True:
            return False
        return _to_float(value) is not None

    # Text/single/multi fallback.
    if is_provided is True:
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list):
            return len(value) > 0
        return value is not None
    return False


def _normalize_status(status: Optional[str]) -> str:
    if status is None:
        return ""
    return str(status).strip().lower()


def _is_match_state(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"match", "matched"}


def compute_relevant_findings(disease_id: Optional[int], rules: Sequence[Any]) -> Set[str]:
    relevant: Set[str] = set()
    for rule in rules or []:
        rid = _rule_disease_id(rule)
        if disease_id is not None and rid is not None and rid != disease_id:
            continue
        for condition in _iter_conditions(rule):
            code = _condition_code(condition)
            if code:
                relevant.add(code)
    return relevant


def compute_completeness(
    relevant_finding_codes: Set[str],
    findings_by_code: Dict[str, Any],
    answers_by_code: Dict[str, Any],
) -> Dict[str, Any]:
    total_weight = 0.0
    answered_weight = 0.0
    missing_finding_codes: List[str] = []

    for code in sorted(relevant_finding_codes):
        finding = findings_by_code.get(code)
        if not finding:
            continue
        weight = _finding_weight(finding)
        total_weight += weight

        answer = answers_by_code.get(code)
        if _is_answered(finding, answer):
            answered_weight += weight
        else:
            missing_finding_codes.append(code)

    completeness_pct = (answered_weight / total_weight * 100.0) if total_weight > 0 else 0.0
    return {
        "total_weight": round(total_weight, 3),
        "answered_weight": round(answered_weight, 3),
        "completeness_pct": round(max(0.0, min(100.0, completeness_pct)), 2),
        "missing_finding_codes": missing_finding_codes,
    }


def compute_evidence_bonus(
    disease_id: Optional[int],
    rules: Sequence[Any],
    matched_rule_results: Sequence[Dict[str, Any]],
    strong_rule_bonus_pct: float = 5.0,
) -> Dict[str, Any]:
    rules_by_id: Dict[int, Any] = {}
    for rule in rules or []:
        rid = _rule_id(rule)
        if rid is not None:
            rules_by_id[rid] = rule

    strong_rule_ids: List[int] = []
    bonus_cap_candidates: List[float] = []

    for row in matched_rule_results or []:
        if not _is_match_state(row.get("matched_state")):
            continue

        rule_id = row.get("rule_id")
        try:
            rule_id = int(rule_id) if rule_id is not None else None
        except Exception:
            rule_id = None
        if rule_id is None:
            continue

        rule = rules_by_id.get(rule_id)
        if not rule:
            continue
        if disease_id is not None and _rule_disease_id(rule) not in {None, disease_id}:
            continue
        if _rule_type(rule) != "screening":
            continue

        matched_required = int(row.get("matched_required_count") or 0)
        total_required = int(row.get("total_required_count") or 0)
        score_added = _to_float(row.get("score_added"), default=0.0) or 0.0

        strong = False
        if total_required > 0 and matched_required >= total_required:
            strong = True
        elif score_added > 0:
            strong = True

        if not strong:
            continue

        strong_rule_ids.append(rule_id)
        cap_pct = _as_pct(_get_attr(rule, "confidence_bonus_max"))
        if cap_pct is not None:
            bonus_cap_candidates.append(cap_pct)

    raw_bonus_pct = len(strong_rule_ids) * max(0.0, float(strong_rule_bonus_pct))
    # Conservative cap: use the smallest configured cap across contributing screening rules.
    bonus_cap_pct = min(bonus_cap_candidates) if bonus_cap_candidates else raw_bonus_pct
    bonus_applied_pct = min(raw_bonus_pct, bonus_cap_pct)

    return {
        "strong_rule_ids": strong_rule_ids,
        "strong_rule_count": len(strong_rule_ids),
        "raw_bonus_pct": round(raw_bonus_pct, 2),
        "bonus_cap_pct": round(max(0.0, bonus_cap_pct), 2),
        "bonus_applied_pct": round(max(0.0, bonus_applied_pct), 2),
    }


def compute_missing_key_facts(
    relevant_finding_codes: Set[str],
    findings_by_code: Dict[str, Any],
    answers_by_code: Dict[str, Any],
    key_lab_aliases: Optional[Dict[str, Set[str]]] = None,
) -> List[str]:
    aliases = key_lab_aliases or KEY_LAB_ALIASES
    relevant_lower = {c.lower() for c in relevant_finding_codes}
    missing: List[str] = []

    for canonical, keys in aliases.items():
        if not (relevant_lower & {k.lower() for k in keys}):
            continue

        provided_any = False
        for key in keys:
            actual_code = next((c for c in relevant_finding_codes if c.lower() == key.lower()), None)
            if not actual_code:
                continue
            finding = findings_by_code.get(actual_code)
            if finding and _is_answered(finding, answers_by_code.get(actual_code)):
                provided_any = True
                break

        if not provided_any:
            missing.append(canonical)

    return missing


def apply_caps(
    disease_id: Optional[int],
    status: Optional[str],
    confidence_raw_pct: float,
    rules: Sequence[Any],
    matched_rule_results: Sequence[Dict[str, Any]],
    missing_key_labs: Sequence[str],
) -> Dict[str, Any]:
    final_conf_pct = max(0.0, min(100.0, float(confidence_raw_pct)))
    applied: Dict[str, Any] = {}
    normalized_status = _normalize_status(status)

    relevant_rules = [
        r for r in (rules or [])
        if disease_id is None or _rule_disease_id(r) in {None, disease_id}
    ]

    if normalized_status != "confirmed" and (missing_key_labs or []):
        cap_candidates = [
            _as_pct(_get_attr(rule, "max_conf_without_labs"))
            for rule in relevant_rules
            if _as_pct(_get_attr(rule, "max_conf_without_labs")) is not None
        ]
        if cap_candidates:
            lab_cap_pct = min(cap_candidates)
            if final_conf_pct > lab_cap_pct:
                final_conf_pct = lab_cap_pct
                applied["max_conf_without_labs"] = round(lab_cap_pct, 2)

    if normalized_status == "confirmed":
        rules_by_id: Dict[int, Any] = {}
        for rule in relevant_rules:
            rid = _rule_id(rule)
            if rid is not None:
                rules_by_id[rid] = rule

        diagnostic_floor_candidates: List[float] = []
        for row in matched_rule_results or []:
            if not _is_match_state(row.get("matched_state")):
                continue
            rule_id = row.get("rule_id")
            try:
                rule_id = int(rule_id) if rule_id is not None else None
            except Exception:
                rule_id = None
            if rule_id is None or rule_id not in rules_by_id:
                continue
            rule = rules_by_id[rule_id]
            if _rule_type(rule) != "diagnostic":
                continue
            floor = _as_pct(_get_attr(rule, "base_confidence"))
            if floor is not None:
                diagnostic_floor_candidates.append(floor)

        if diagnostic_floor_candidates:
            floor_pct = max(diagnostic_floor_candidates)
            if final_conf_pct < floor_pct:
                final_conf_pct = floor_pct
                applied["diagnostic_floor_base_confidence"] = round(floor_pct, 2)

    return {
        "confidence_final_pct": round(max(0.0, min(100.0, final_conf_pct)), 2),
        "applied_caps": applied,
    }


def compute_disease_confidence(
    disease_id: Optional[int],
    status: Optional[str],
    rules: Sequence[Any],
    findings_by_code: Dict[str, Any],
    answers_by_code: Dict[str, Any],
    matched_rule_results: Sequence[Dict[str, Any]],
    strong_rule_bonus_pct: float = 5.0,
) -> Dict[str, Any]:
    relevant_codes = compute_relevant_findings(disease_id=disease_id, rules=rules)
    completeness = compute_completeness(
        relevant_finding_codes=relevant_codes,
        findings_by_code=findings_by_code,
        answers_by_code=answers_by_code,
    )
    bonus = compute_evidence_bonus(
        disease_id=disease_id,
        rules=rules,
        matched_rule_results=matched_rule_results,
        strong_rule_bonus_pct=strong_rule_bonus_pct,
    )

    confidence_raw_pct = min(100.0, completeness["completeness_pct"] + bonus["bonus_applied_pct"])
    missing_key_facts = compute_missing_key_facts(
        relevant_finding_codes=relevant_codes,
        findings_by_code=findings_by_code,
        answers_by_code=answers_by_code,
    )
    capped = apply_caps(
        disease_id=disease_id,
        status=status,
        confidence_raw_pct=confidence_raw_pct,
        rules=rules,
        matched_rule_results=matched_rule_results,
        missing_key_labs=missing_key_facts,
    )

    final_pct = capped["confidence_final_pct"]
    return {
        "confidence_pct": round(final_pct, 2),
        "confidence": round(final_pct / 100.0, 3),
        "confidence_raw_pct": round(confidence_raw_pct, 2),
        "status": _normalize_status(status),
        "relevant_finding_codes": sorted(relevant_codes),
        "completeness": completeness,
        "evidence_bonus": bonus,
        "missing_key_facts_json": missing_key_facts,
        "applied_caps": capped.get("applied_caps", {}),
    }


def confidence_score(matched: int, total: int, max_total: int) -> Dict[str, float]:
    """Backward-compatible helper retained for older callers."""
    if total <= 0 or max_total <= 0:
        return {"match_pct": 0.0, "specificity_pct": 0.0, "confidence": 0.0}

    match_pct = (matched / total) * 100.0
    specificity_pct = (total / max_total) * 100.0
    confidence = (0.7 * match_pct) + (0.3 * specificity_pct)
    return {
        "match_pct": round(match_pct, 2),
        "specificity_pct": round(specificity_pct, 2),
        "confidence": round(confidence, 2),
    }
