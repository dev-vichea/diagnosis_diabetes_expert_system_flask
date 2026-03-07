import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    Assessment,
    AssessmentDiagnosisResult,
    CaseFact,
    Disease,
    Rule,
    RuleAction,
    RuleCondition,
    Symptom,
    User,
)
from app.services.assessment_service import run_diagnosis_now


@pytest.fixture()
def app():
    app = create_app()
    app.config.update(TESTING=True)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _seed_user() -> User:
    user = User(name="Case User", email="case@example.com", password_hash="x")
    db.session.add(user)
    db.session.commit()
    return user


def _symptom(code: str, input_type: str = "BOOLEAN") -> Symptom:
    row = Symptom(
        code=code,
        name=code.replace("_", " ").title(),
        question_text=f"{code}?",
        input_type=input_type,
        is_active=True,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _disease(code: str, name: str, severity_level: str = "LOW") -> Disease:
    row = Disease(
        code=code,
        name=name,
        severity_level=severity_level,
        patient_label_screening=f"Possible {name}",
        patient_label_confirmed=name,
        is_active=True,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _rule(
    code: str,
    disease: Disease,
    priority: int,
    conditions: list[tuple[Symptom, str, object]],
):
    rule = Rule(
        rule_code=code,
        title=code,
        disease_id=disease.id,
        risk_level=("HIGH" if disease.severity_level == "HIGH" else "MEDIUM" if disease.severity_level == "MEDIUM" else "LOW"),
        base_confidence=0.8,
        priority=priority,
        is_active=True,
    )
    db.session.add(rule)
    db.session.flush()

    for symptom, operator, value in conditions:
        if isinstance(value, bool):
            value = "true" if value else "false"
        db.session.add(
            RuleCondition(
                rule_id=rule.id,
                symptom_id=symptom.id,
                operator=operator,
                value=value,
                is_required=True,
            )
        )

    db.session.add(RuleAction(rule_id=rule.id, disease_id=disease.id, confidence=0.8))
    db.session.flush()
    return rule


def _assessment(user_id: int) -> Assessment:
    row = Assessment(user_id=user_id, status="IN_PROGRESS")
    db.session.add(row)
    db.session.flush()
    return row


def _fact(assessment: Assessment, symptom: Symptom, value):
    if symptom.input_type == "NUMBER":
        db.session.add(CaseFact(assessment_id=assessment.id, symptom_id=symptom.id, value_number=float(value)))
    else:
        db.session.add(CaseFact(assessment_id=assessment.id, symptom_id=symptom.id, value_bool=bool(value)))


def _result_rows(assessment_id: int) -> list[AssessmentDiagnosisResult]:
    return (
        AssessmentDiagnosisResult.query
        .filter_by(assessment_id=assessment_id)
        .order_by(AssessmentDiagnosisResult.score.desc(), AssessmentDiagnosisResult.id.asc())
        .all()
    )


def test_rule_fires_only_when_all_conditions_met(app):
    with app.app_context():
        user = _seed_user()
        thirst = _symptom("thirst")
        fatigue = _symptom("fatigue")
        type2 = _disease("TYPE2_DM", "Type 2 Diabetes", severity_level="HIGH")
        _rule("R_TYPE2_CORE", type2, 60, [(thirst, "==", True), (fatigue, "==", True)])

        a1 = _assessment(user.id)
        _fact(a1, thirst, True)
        db.session.commit()

        run1 = run_diagnosis_now(a1)
        assert run1.disease.code == "UNDETERMINED"
        assert _result_rows(a1.id) == []

        a2 = _assessment(user.id)
        _fact(a2, thirst, True)
        _fact(a2, fatigue, True)
        db.session.commit()

        run2 = run_diagnosis_now(a2)
        rows = _result_rows(a2.id)
        assert run2.disease.code == "TYPE2_DM"
        assert len(rows) == 1
        trace = rows[0].trace_json or {}
        assert trace.get("matched_rules")
        assert trace["matched_rules"][0]["rule_id"] is not None


def test_no_duplicate_candidates_per_disease(app):
    with app.app_context():
        user = _seed_user()
        thirst = _symptom("thirst")
        fatigue = _symptom("fatigue")
        inactive = _symptom("inactive")
        family_history = _symptom("family_history")

        type2 = _disease("TYPE2_DM", "Type 2 Diabetes", severity_level="HIGH")
        _rule("R_TYPE2_A", type2, 60, [(thirst, "==", True), (fatigue, "==", True)])
        _rule("R_TYPE2_B", type2, 60, [(inactive, "==", True), (family_history, "==", True)])

        assessment = _assessment(user.id)
        _fact(assessment, thirst, True)
        _fact(assessment, fatigue, True)
        _fact(assessment, inactive, True)
        _fact(assessment, family_history, True)
        db.session.commit()

        run_diagnosis_now(assessment)
        rows = _result_rows(assessment.id)

        assert len(rows) == 1
        assert rows[0].disease.code == "TYPE2_DM"
        matched_rules = (rows[0].trace_json or {}).get("matched_rules") or []
        assert len(matched_rules) == 2


def test_invalid_labs_do_not_block_candidates(app):
    with app.app_context():
        user = _seed_user()
        thirst = _symptom("thirst")
        fatigue = _symptom("fatigue")
        fpg = _symptom("fpg", input_type="NUMBER")

        type2 = _disease("TYPE2_DM", "Type 2 Diabetes", severity_level="HIGH")
        _rule("R_TYPE2_CORE", type2, 60, [(thirst, "==", True), (fatigue, "==", True)])

        assessment = _assessment(user.id)
        _fact(assessment, thirst, True)
        _fact(assessment, fatigue, True)
        _fact(assessment, fpg, 999)
        db.session.commit()

        run = run_diagnosis_now(assessment)
        rows = _result_rows(assessment.id)

        assert run.disease.code == "TYPE2_DM"
        assert len(rows) == 1
        trace = rows[0].trace_json or {}
        assert trace.get("labs", {}).get("labs_invalid") is True
        assert trace.get("lab_points") == []


def test_evidence_thresholds_and_candidate_sorting(app):
    with app.app_context():
        user = _seed_user()

        thirst = _symptom("thirst")
        fatigue = _symptom("fatigue")
        inactive = _symptom("inactive")
        family_history = _symptom("family_history")
        pregnant = _symptom("pregnant")

        high_dx = _disease("TYPE2_DM", "Type 2 Diabetes", severity_level="HIGH")
        moderate_dx = _disease("PREDM", "Prediabetes", severity_level="MEDIUM")
        low_dx = _disease("GDM", "Gestational Diabetes", severity_level="LOW")

        _rule("R_HIGH_A", high_dx, 60, [(thirst, "==", True), (fatigue, "==", True)])
        _rule("R_HIGH_B", high_dx, 60, [(inactive, "==", True), (family_history, "==", True)])
        _rule(
            "R_MOD",
            moderate_dx,
            60,
            [
                (thirst, "==", True),
                (fatigue, "==", True),
                (inactive, "==", True),
                (family_history, "==", True),
            ],
        )
        _rule("R_LOW", low_dx, 40, [(pregnant, "==", True)])

        assessment = _assessment(user.id)
        _fact(assessment, thirst, True)
        _fact(assessment, fatigue, True)
        _fact(assessment, inactive, True)
        _fact(assessment, family_history, True)
        _fact(assessment, pregnant, True)
        db.session.commit()

        run_diagnosis_now(assessment)
        rows = _result_rows(assessment.id)

        assert [row.disease.code for row in rows] == ["TYPE2_DM", "PREDM", "GDM"]
        assert [row.evidence_level for row in rows] == ["HIGH", "MODERATE", "LOW"]
        assert rows[0].score > rows[1].score > rows[2].score
