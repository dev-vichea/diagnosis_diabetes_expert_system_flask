from typing import Optional, Dict, Any

from app.models import Assessment, DiagnosisRun, Symptom
from app.services.assessment_service import (
    finalize_if_ready,
    ensure_fallback_result as _ensure_fallback_result,
    get_ranked_candidates as _get_ranked_candidates,
    get_next_symptom,
)


def infer_if_complete(assessment: Assessment) -> Optional[DiagnosisRun]:
    return finalize_if_ready(assessment)


def ensure_fallback_result(assessment: Assessment) -> DiagnosisRun:
    return _ensure_fallback_result(assessment)


def get_ranked_candidates(assessment: Assessment, limit: int = 3) -> Dict[str, Any]:
    return _get_ranked_candidates(assessment, limit=limit)


def next_question(assessment: Assessment, excluded_ids: Optional[set] = None) -> Optional[Symptom]:
    return get_next_symptom(assessment, excluded_ids=excluded_ids)
