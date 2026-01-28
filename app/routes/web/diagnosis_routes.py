from flask import render_template, request, session, redirect, url_for

from app.extensions import db
from app.models import Assessment, AssessmentAnswer, AssessmentMetric, Symptom
from app.services.inference_engine import infer_if_complete, next_question, ensure_fallback_result
from app.services.report_builder import build_report

from . import web_bp
from .utils import require_login

AGE_OPTIONS = [
    {"label": "Under 45", "value": 40},
    {"label": "45-54", "value": 50},
    {"label": "55-64", "value": 60},
    {"label": "65+", "value": 70},
]


def _current_user_id():
    me = session.get("me") or {}
    uid = me.get("user_id")
    return int(uid) if uid is not None else None


def _get_or_create_assessment(user_id: int) -> Assessment:
    active = Assessment.query.filter_by(user_id=user_id, status="IN_PROGRESS").first()
    if active:
        return active
    assessment = Assessment(user_id=user_id, status="IN_PROGRESS")
    db.session.add(assessment)
    db.session.commit()
    return assessment


def _age_label(age_years: int) -> str:
    if age_years < 45:
        return "Under 45"
    if age_years < 55:
        return "45-54"
    if age_years < 65:
        return "55-64"
    return "65+"

@web_bp.get("/patient/diagnosis")
def patient_diagnosis():
    guard = require_login()
    if guard:
        return guard
    return render_template("patient/diagnosis.html")


@web_bp.get("/patient/history")
def patient_history():
    guard = require_login()
    if guard:
        return guard
    return render_template("patient/history.html")


@web_bp.get("/patient/profile")
def patient_profile():
    guard = require_login()
    if guard:
        return guard
    return render_template("patient/profile.html")


@web_bp.route("/patient/messages", methods=["GET", "POST"])
def patient_messages():
    guard = require_login()
    if guard:
        return guard

    user_id = _current_user_id()
    if not user_id:
        return redirect(url_for("web.login_page"))

    if request.method == "POST":
        action = request.form.get("action")
        if action == "start":
            assessment = _get_or_create_assessment(user_id)
            session["active_assessment_id"] = assessment.id
            return redirect(url_for("web.patient_messages"))
        if action == "reset":
            session.pop("active_assessment_id", None)
            return redirect(url_for("web.patient_messages", start=1))

        assessment_id = request.form.get("assessment_id") or session.get("active_assessment_id")
        try:
            assessment_id = int(assessment_id)
        except (TypeError, ValueError):
            assessment_id = None

        assessment = None
        if assessment_id:
            assessment = Assessment.query.filter_by(id=assessment_id, user_id=user_id).first()

        if not assessment:
            return redirect(url_for("web.patient_messages", start=1))

        if assessment.status != "IN_PROGRESS":
            session["active_assessment_id"] = assessment.id
            return redirect(url_for("web.patient_messages"))

        answer_type = request.form.get("answer_type")
        if answer_type == "age":
            age_value = request.form.get("age_years")
            try:
                age_years = int(age_value)
            except (TypeError, ValueError):
                age_years = None
            if age_years is not None:
                metric = AssessmentMetric.query.filter_by(assessment_id=assessment.id).first()
                if not metric:
                    metric = AssessmentMetric(assessment_id=assessment.id)
                    db.session.add(metric)
                metric.age_years = age_years
                db.session.commit()
                infer_if_complete(assessment)
        elif answer_type == "symptom":
            symptom_id = request.form.get("symptom_id")
            answer_value = request.form.get("answer")
            try:
                symptom_id = int(symptom_id)
            except (TypeError, ValueError):
                symptom_id = None
            answer_bool = True if answer_value == "yes" else False if answer_value == "no" else None
            if symptom_id and answer_bool is not None:
                existing = AssessmentAnswer.query.filter_by(
                    assessment_id=assessment.id,
                    symptom_id=symptom_id
                ).first()
                if not existing:
                    db.session.add(AssessmentAnswer(
                        assessment_id=assessment.id,
                        symptom_id=symptom_id,
                        answer_bool=answer_bool
                    ))
                    db.session.commit()
                    infer_if_complete(assessment)

        session["active_assessment_id"] = assessment.id
        return redirect(url_for("web.patient_messages"))

    start_flag = request.args.get("start") in {"1", "true", "yes"}
    assessment = None
    session_assessment_id = session.get("active_assessment_id")

    if start_flag:
        assessment = _get_or_create_assessment(user_id)
        session["active_assessment_id"] = assessment.id
    elif session_assessment_id:
        assessment = Assessment.query.filter_by(id=session_assessment_id, user_id=user_id).first()
    else:
        assessment = Assessment.query.filter_by(user_id=user_id, status="IN_PROGRESS").first()
        if assessment:
            session["active_assessment_id"] = assessment.id

    report = None
    current_question = None
    current_step = None
    metric = None
    answers = []

    if assessment:
        metric = AssessmentMetric.query.filter_by(assessment_id=assessment.id).first()
        answers = (
            AssessmentAnswer.query
            .filter_by(assessment_id=assessment.id)
            .order_by(AssessmentAnswer.answered_at.asc())
            .all()
        )
        if assessment.status != "IN_PROGRESS":
            report = build_report(assessment.id)
            current_step = "result"
        elif not metric or metric.age_years is None:
            current_step = "age"
        else:
            current_question = next_question(assessment)
            if not current_question:
                ensure_fallback_result(assessment)
                report = build_report(assessment.id)
                current_step = "result"
            else:
                current_step = "symptom"

    symptoms = {}
    if answers:
        symptom_ids = [a.symptom_id for a in answers]
        symptoms = {
            s.id: s for s in Symptom.query.filter(Symptom.id.in_(symptom_ids)).all()
        }

    messages = [{
        "role": "bot",
        "text": "Hi there! I'm Dr. DiaBot. I will ask a few questions to check your diabetes risk.",
    }]

    if assessment:
        if metric and metric.age_years is not None:
            messages.append({"role": "bot", "text": "What is your age?"})
            messages.append({"role": "user", "text": _age_label(metric.age_years)})

        for answer in answers:
            symptom = symptoms.get(answer.symptom_id)
            question_text = (
                symptom.question_text if symptom and symptom.question_text else
                symptom.name if symptom and symptom.name else
                symptom.code if symptom else "Question"
            )
            messages.append({"role": "bot", "text": question_text})
            messages.append({"role": "user", "text": "Yes" if answer.answer_bool else "No"})

        if report:
            risk = report.get("risk_assessment", {})
            diagnosis_code = risk.get("diagnosis_code") or "N/A"
            risk_level = risk.get("risk_level") or "N/A"
            summary_lines = [
                "Assessment complete.",
                f"Diagnosis: {diagnosis_code}",
                f"Risk level: {risk_level}",
            ]
            advice = report.get("advice")
            if advice and advice.get("content"):
                summary_lines.append(advice.get("content"))
            messages.append({"role": "bot", "text": " ".join(summary_lines)})
        elif current_step == "age":
            messages.append({"role": "bot", "text": "What is your age?"})
        elif current_step == "symptom" and current_question:
            question_text = current_question.question_text or current_question.name or current_question.code
            messages.append({"role": "bot", "text": question_text})

    total_questions = 1 + Symptom.query.filter_by(is_active=True).count()
    question_index = 1
    if assessment and current_step == "symptom":
        question_index = 1 + len(answers) + 1
    elif assessment and current_step == "result":
        question_index = total_questions

    return render_template(
        "patient/messages.html",
        assessment=assessment,
        messages=messages,
        current_step=current_step,
        current_question=current_question,
        age_options=AGE_OPTIONS,
        report=report,
        total_questions=total_questions,
        question_index=question_index,
    )


@web_bp.get("/patient/calendar")
def patient_calendar():
    guard = require_login()
    if guard:
        return guard
    return render_template("calendar.html")
