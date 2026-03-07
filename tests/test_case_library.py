import json
import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    User,
    Symptom,
    Rule,
    RuleCondition,
    Assessment,
    CaseFact,
    Disease,
    RuleAction,
)
from app.services.inference_engine import infer_if_complete
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


def _seed_symptoms():
    symptoms = [
        ("polyuria", "BOOLEAN"),
        ("polydipsia", "BOOLEAN"),
        ("weight_loss", "BOOLEAN"),
        ("overweight", "BOOLEAN"),
        ("inactive", "BOOLEAN"),
        ("high_bp", "BOOLEAN"),
        ("blurred_vision", "BOOLEAN"),
        ("age_years", "NUMBER"),
        ("bmi", "NUMBER"),
    ]
    created = []
    for code, input_type in symptoms:
        created.append(Symptom(
            code=code,
            name=code.replace("_", " ").title(),
            question_text=f"{code}?",
            input_type=input_type,
            is_active=True,
        ))
    db.session.add_all(created)
    db.session.commit()
    return {s.code: s.id for s in created}


def _add_rule(rule_code, diagnosis_code, risk_level, priority, confidence, conditions):
    confidence_frac = confidence / 100.0
    rule = Rule(
        rule_code=rule_code,
        title=rule_code,
        risk_level=risk_level,
        base_confidence=confidence_frac,
        priority=priority,
        is_active=True,
    )
    db.session.add(rule)
    db.session.commit()

    for cond in conditions:
        value = cond.get("value")
        if isinstance(value, bool):
            value = "true" if value else "false"
        rc = RuleCondition(
            rule_id=rule.id,
            symptom_id=cond["symptom_id"],
            operator=cond.get("operator", "=="),
            value=value,
        )
        db.session.add(rc)

    db.session.commit()

    disease = Disease.query.filter_by(code=diagnosis_code).first()
    if not disease:
        severity_level = "HIGH" if risk_level == "HIGH" else ("MEDIUM" if risk_level == "MEDIUM" else "LOW")
        disease = Disease(
            code=diagnosis_code,
            name=diagnosis_code,
            severity_level=severity_level,
            patient_label_screening=f"Possible {diagnosis_code} (screening)",
            patient_label_confirmed=diagnosis_code,
        )
        db.session.add(disease)
        db.session.commit()
    rule.disease_id = disease.id
    db.session.add(RuleAction(rule_id=rule.id, disease_id=disease.id, confidence=confidence_frac))
    db.session.commit()


def _seed_rules(code_map):
    _add_rule(
        "R_HIGH_CLASSIC",
        "HIGH_RISK_TYPE_2_DIABETES",
        "HIGH",
        priority=100,
        confidence=90,
        conditions=[
            {"symptom_id": code_map["polyuria"], "operator": "==", "value": True, "expected_value": True},
            {"symptom_id": code_map["polydipsia"], "operator": "==", "value": True, "expected_value": True},
            {"symptom_id": code_map["weight_loss"], "operator": "==", "value": True, "expected_value": True},
        ],
    )
    _add_rule(
        "R_METABOLIC",
        "MODERATE_RISK",
        "MEDIUM",
        priority=70,
        confidence=80,
        conditions=[
            {"symptom_id": code_map["overweight"], "operator": "==", "value": True, "expected_value": True},
            {"symptom_id": code_map["inactive"], "operator": "==", "value": True, "expected_value": True},
            {"symptom_id": code_map["high_bp"], "operator": "==", "value": True, "expected_value": True},
        ],
    )
    _add_rule(
        "R_LOW",
        "LOW_RISK",
        "LOW",
        priority=10,
        confidence=60,
        conditions=[
            {"symptom_id": code_map["overweight"], "operator": "==", "value": False, "expected_value": False},
            {"symptom_id": code_map["inactive"], "operator": "==", "value": False, "expected_value": False},
        ],
    )
    _add_rule(
        "R_AGE_45",
        "AGE_OR_BMI_RISK",
        "MEDIUM",
        priority=80,
        confidence=85,
        conditions=[
            {"symptom_id": code_map["age_years"], "operator": ">=", "value": "45"},
        ],
    )
    _add_rule(
        "R_BMI_30",
        "AGE_OR_BMI_RISK",
        "MEDIUM",
        priority=80,
        confidence=85,
        conditions=[
            {"symptom_id": code_map["bmi"], "operator": ">=", "value": "30"},
        ],
    )
    _add_rule(
        "R_SYMPTOM_ALERT_A",
        "SYMPTOM_ALERT",
        "HIGH",
        priority=90,
        confidence=88,
        conditions=[
            {"symptom_id": code_map["polyuria"], "operator": "==", "value": True, "expected_value": True},
            {"symptom_id": code_map["polydipsia"], "operator": "==", "value": True, "expected_value": True},
        ],
    )
    _add_rule(
        "R_SYMPTOM_ALERT_B",
        "SYMPTOM_ALERT",
        "HIGH",
        priority=90,
        confidence=88,
        conditions=[
            {"symptom_id": code_map["weight_loss"], "operator": "==", "value": True, "expected_value": True},
            {"symptom_id": code_map["blurred_vision"], "operator": "==", "value": True, "expected_value": True},
        ],
    )


def _load_cases():
    path = Path(__file__).resolve().parent / "cases.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)["cases"]


def test_case_library(app):
    with app.app_context():
        user = User(name="Test User", email="test@example.com", password_hash="x")
        db.session.add(user)
        db.session.commit()

        code_map = _seed_symptoms()
        _seed_rules(code_map)

        for case in _load_cases():
            assessment = Assessment(user_id=user.id, status="IN_PROGRESS")
            db.session.add(assessment)
            db.session.commit()

            for code, value in (case.get("inputs", {}).get("symptoms", {}) or {}).items():
                symptom_id = code_map[code]
                db.session.add(CaseFact(
                    assessment_id=assessment.id,
                    symptom_id=symptom_id,
                    value_bool=bool(value),
                ))

            metrics = case.get("inputs", {}).get("metrics") or {}
            if metrics:
                if "height_cm" in metrics:
                    pass
                if "weight_kg" in metrics:
                    pass
                if "age_years" in metrics:
                    if "age_years" in code_map:
                        db.session.add(CaseFact(
                            assessment_id=assessment.id,
                            symptom_id=code_map["age_years"],
                            value_number=float(metrics["age_years"]),
                        ))
                if "bmi" in metrics and "bmi" in code_map:
                    db.session.add(CaseFact(
                        assessment_id=assessment.id,
                        symptom_id=code_map["bmi"],
                        value_number=float(metrics["bmi"]),
                    ))
                elif "bmi" in code_map and "height_cm" in metrics and "weight_kg" in metrics:
                    height_m = float(metrics["height_cm"]) / 100.0
                    if height_m > 0:
                        bmi = float(metrics["weight_kg"]) / (height_m * height_m)
                        db.session.add(CaseFact(
                            assessment_id=assessment.id,
                            symptom_id=code_map["bmi"],
                            value_number=float(bmi),
                        ))

            db.session.commit()

            result = infer_if_complete(assessment)
            if result is None:
                result = run_diagnosis_now(assessment)
            assert result is not None, f"No result for case: {case['name']}"

            expected = case["expected"]
            disease = result.disease
            assert disease and disease.code == expected["diagnosis_code"], (
                f"{case['name']}: expected diagnosis_code {expected['diagnosis_code']}, "
                f"got {disease.code if disease else None}"
            )
            assert result.risk_level == expected["risk_level"], (
                f"{case['name']}: expected risk_level {expected['risk_level']}, got {result.risk_level}"
            )

            exp = result.trace_json or {}
            if isinstance(exp, str):
                exp = json.loads(exp)
            assert "rules_evaluated" in exp, f"Missing rules_evaluated in explanation for {case['name']}"
            assert "ranked_candidates_top3" in exp, f"Missing ranked_candidates_top3 in explanation for {case['name']}"
