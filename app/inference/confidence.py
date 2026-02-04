def confidence_score(matched: int, total: int, max_total: int) -> dict:
    if total <= 0 or max_total <= 0:
        return {"match_pct": 0.0, "specificity_pct": 0.0, "confidence": 0.0}

    match_pct = (matched / total) * 100.0
    specificity_pct = (total / max_total) * 100.0

    # Weighted score: evidence match + rule strength
    confidence = (0.7 * match_pct) + (0.3 * specificity_pct)

    return {
        "match_pct": round(match_pct, 2),
        "specificity_pct": round(specificity_pct, 2),
        "confidence": round(confidence, 2),
    }
