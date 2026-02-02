from datetime import datetime, timedelta
from typing import Optional

from flask import render_template, redirect, url_for
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.routes.web import web_bp
from app.routes.web.utils import require_login, current_roles
from app.models import Assessment, DiagnosisRun, Rule, Symptom, CaseFact


def _percent_change(current: int, previous: int) -> Optional[float]:
    if not previous:
        return None
    return ((current - previous) / previous) * 100


@web_bp.get("/admin/dashboard")
def admin_dashboard():
    guard = require_login()
    if guard:
        return guard
    if "ADMIN" not in current_roles():
        return redirect(url_for("web.dashboard"))

    now = datetime.utcnow()
    period_days = 30
    period_start = now - timedelta(days=period_days)
    prev_start = period_start - timedelta(days=period_days)

    total_consultations = (
        Assessment.query.filter(Assessment.started_at >= period_start).count()
    )
    prev_total_consultations = (
        Assessment.query.filter(
            Assessment.started_at >= prev_start,
            Assessment.started_at < period_start,
        ).count()
    )
    consultations_delta = _percent_change(total_consultations, prev_total_consultations)

    high_risk = (
        DiagnosisRun.query.filter(
            DiagnosisRun.created_at >= period_start,
            DiagnosisRun.risk_level == "HIGH",
        ).count()
    )
    prev_high_risk = (
        DiagnosisRun.query.filter(
            DiagnosisRun.created_at >= prev_start,
            DiagnosisRun.created_at < period_start,
            DiagnosisRun.risk_level == "HIGH",
        ).count()
    )
    high_risk_delta = _percent_change(high_risk, prev_high_risk)

    symptoms_count = Symptom.query.count()
    rules_count = Rule.query.count()

    avg_confidence_value = (
        DiagnosisRun.query.with_entities(func.avg(DiagnosisRun.confidence))
        .filter(DiagnosisRun.created_at >= period_start)
        .scalar()
    )
    prev_avg_confidence_value = (
        DiagnosisRun.query.with_entities(func.avg(DiagnosisRun.confidence))
        .filter(
            DiagnosisRun.created_at >= prev_start,
            DiagnosisRun.created_at < period_start,
        )
        .scalar()
    )
    avg_confidence = float(avg_confidence_value) if avg_confidence_value is not None else None
    prev_avg_confidence = (
        float(prev_avg_confidence_value) if prev_avg_confidence_value is not None else None
    )
    avg_confidence_pct = avg_confidence * 100 if avg_confidence is not None else None
    prev_avg_confidence_pct = (
        prev_avg_confidence * 100 if prev_avg_confidence is not None else None
    )
    confidence_delta = None
    if avg_confidence_pct is not None and prev_avg_confidence_pct is not None:
        confidence_delta = avg_confidence_pct - prev_avg_confidence_pct

    stats = {
        "consultations": {
            "value": total_consultations,
            "delta": consultations_delta,
            "delta_label": "this period",
        },
        "high_risk": {
            "value": high_risk,
            "delta": high_risk_delta,
            "delta_label": "this period",
        },
        "knowledge_base": {
            "symptoms": symptoms_count,
            "rules": rules_count,
        },
        "avg_confidence": {
            "value": avg_confidence_pct,
            "delta": confidence_delta,
            "delta_label": f"last {period_days} days",
        },
    }

    recent_assessments = (
        Assessment.query.options(selectinload(Assessment.user))
        .order_by(Assessment.started_at.desc())
        .limit(5)
        .all()
    )
    assessment_ids = [a.id for a in recent_assessments]

    recent_runs = {}
    if assessment_ids:
        runs = (
            DiagnosisRun.query.options(selectinload(DiagnosisRun.disease))
            .filter(DiagnosisRun.assessment_id.in_(assessment_ids))
            .order_by(DiagnosisRun.created_at.desc())
            .all()
        )
        for run in runs:
            if run.assessment_id not in recent_runs:
                recent_runs[run.assessment_id] = run

    fact_codes = {"bmi_value", "height_cm", "weight_kg", "age", "patient_age"}
    facts_by_assessment = {}
    if assessment_ids:
        fact_rows = (
            CaseFact.query.join(Symptom)
            .filter(
                CaseFact.assessment_id.in_(assessment_ids),
                Symptom.code.in_(fact_codes),
            )
            .with_entities(CaseFact.assessment_id, Symptom.code, CaseFact.value_number)
            .all()
        )
        for assessment_id, code, value in fact_rows:
            facts_by_assessment.setdefault(assessment_id, {})[code] = value

    def _to_float(value):
        return float(value) if value is not None else None

    def _compute_bmi(facts):
        bmi_value = _to_float(facts.get("bmi_value")) if facts else None
        if bmi_value:
            return bmi_value
        height_cm = _to_float(facts.get("height_cm")) if facts else None
        weight_kg = _to_float(facts.get("weight_kg")) if facts else None
        if height_cm and weight_kg:
            height_m = height_cm / 100
            if height_m > 0:
                return weight_kg / (height_m * height_m)
        return None

    def _badge_class(result_text: str) -> str:
        value = (result_text or "").lower()
        if "normal" in value:
            return "bg-success"
        if "prediabetes" in value:
            return "bg-warning"
        if "high" in value:
            return "bg-danger"
        if "type 1" in value or "type1" in value:
            return "bg-info"
        return "bg-secondary"

    recent_consultations = []
    for assessment in recent_assessments:
        run = recent_runs.get(assessment.id)
        result_text = "Inconclusive"
        if run and run.disease and run.disease.name:
            result_text = run.disease.name
        elif run and run.risk_level:
            result_text = run.risk_level.title()

        facts = facts_by_assessment.get(assessment.id, {})
        bmi = _compute_bmi(facts)
        age_val = _to_float(facts.get("age") or facts.get("patient_age"))
        age_text = f"{int(age_val)}" if age_val is not None else "--"
        bmi_text = f"{bmi:.1f}" if bmi is not None else "--"

        patient_name = (
            assessment.user.name
            if assessment.user and assessment.user.name
            else f"Patient #{assessment.user_id}"
        )
        timestamp = assessment.completed_at or assessment.started_at

        recent_consultations.append(
            {
                "case_id": f"C-{assessment.id}",
                "assessment_id": assessment.id,
                "patient": patient_name,
                "age_bmi": f"{age_text} / {bmi_text}",
                "result": result_text,
                "result_class": _badge_class(result_text),
                "date": timestamp.strftime("%Y-%m-%d %H:%M") if timestamp else "--",
            }
        )

    avg_confidence_chart = int(round(avg_confidence_pct)) if avg_confidence_pct is not None else 0

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        period_days=period_days,
        recent_consultations=recent_consultations,
        avg_confidence_chart=avg_confidence_chart,
    )
