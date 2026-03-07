import os
from typing import Any, Dict, List, Optional

if __name__ == "__main__":
    from dotenv import load_dotenv

    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    load_dotenv(env_path, override=True)

from app.extensions import db
from app.models import Disease, Rule, RuleAction, RuleCondition, RuleSet, Symptom

VALID_OPERATORS = {
    "PRESENT",
    "ABSENT",
    "==",
    "!=",
    ">=",
    "<=",
    ">",
    "<",
    "EQ",
    "NEQ",
    "GTE",
    "GT",
    "LTE",
    "LT",
    "BETWEEN",
    "IN",
}

KB_BLUEPRINT_V2: Dict[str, List[Dict[str, Any]]] = {
    "symptoms": [
        {
            "code": "has_labs",
            "name": "Recent lab results",
            "question_text": "Do you have recent blood test results? (Yes/No)",
            "input_type": "BOOLEAN",
            "ui_section": "Labs",
            "category": "HAB_LAB",
            "priority_order": 1,
        },
        {
            "code": "fpg",
            "name": "Fasting Plasma Glucose",
            "question_text": "Fasting plasma glucose (mg/dL)",
            "input_type": "NUMBER",
            "unit": "mg/dL",
            "allow_unknown": True,
            "ui_section": "Labs",
            "category": "HAB_LAB",
            "parent_code": "has_labs",
            "show_if_operator": "==",
            "show_if_value": "1",
            "priority_order": 10,
        },
        {
            "code": "FBS",
            "name": "Fasting Blood Sugar",
            "question_text": "FBS / fasting blood glucose (mg/dL)",
            "input_type": "NUMBER",
            "unit": "mg/dL",
            "allow_unknown": True,
            "ui_section": "Labs",
            "category": "HAB_LAB",
            "parent_code": "has_labs",
            "show_if_operator": "==",
            "show_if_value": "1",
            "priority_order": 11,
        },
        {
            "code": "hba1c",
            "name": "HbA1c",
            "question_text": "HbA1c (%)",
            "input_type": "NUMBER",
            "unit": "%",
            "allow_unknown": True,
            "ui_section": "Labs",
            "category": "HAB_LAB",
            "parent_code": "has_labs",
            "show_if_operator": "==",
            "show_if_value": "1",
            "priority_order": 20,
        },
        {
            "code": "HBA1C",
            "name": "HbA1c (standard code)",
            "question_text": "HbA1c (%)",
            "input_type": "NUMBER",
            "unit": "%",
            "allow_unknown": True,
            "ui_section": "Labs",
            "category": "HAB_LAB",
            "parent_code": "has_labs",
            "show_if_operator": "==",
            "show_if_value": "1",
            "priority_order": 21,
        },
        {
            "code": "random_glucose",
            "name": "Random glucose",
            "question_text": "Random glucose (mg/dL)",
            "input_type": "NUMBER",
            "unit": "mg/dL",
            "allow_unknown": True,
            "ui_section": "Labs",
            "category": "HAB_LAB",
            "parent_code": "has_labs",
            "show_if_operator": "==",
            "show_if_value": "1",
            "priority_order": 30,
        },
        {
            "code": "RANDOM_GLUCOSE",
            "name": "Random glucose (standard code)",
            "question_text": "Random glucose (mg/dL)",
            "input_type": "NUMBER",
            "unit": "mg/dL",
            "allow_unknown": True,
            "ui_section": "Labs",
            "category": "HAB_LAB",
            "parent_code": "has_labs",
            "show_if_operator": "==",
            "show_if_value": "1",
            "priority_order": 31,
        },
        {
            "code": "OGTT75_FAST",
            "name": "OGTT 75 g fasting",
            "question_text": "75 g OGTT fasting glucose (mg/dL)",
            "input_type": "NUMBER",
            "unit": "mg/dL",
            "allow_unknown": True,
            "ui_section": "Labs",
            "category": "HAB_LAB",
            "parent_code": "has_labs",
            "show_if_operator": "==",
            "show_if_value": "1",
            "priority_order": 32,
        },
        {
            "code": "OGTT75_1H",
            "name": "OGTT 75 g 1-hour",
            "question_text": "75 g OGTT 1-hour glucose (mg/dL)",
            "input_type": "NUMBER",
            "unit": "mg/dL",
            "allow_unknown": True,
            "ui_section": "Labs",
            "category": "HAB_LAB",
            "parent_code": "has_labs",
            "show_if_operator": "==",
            "show_if_value": "1",
            "priority_order": 33,
        },
        {
            "code": "OGTT75_2H",
            "name": "OGTT 75 g 2-hour",
            "question_text": "75 g OGTT 2-hour glucose (mg/dL)",
            "input_type": "NUMBER",
            "unit": "mg/dL",
            "allow_unknown": True,
            "ui_section": "Labs",
            "category": "HAB_LAB",
            "parent_code": "has_labs",
            "show_if_operator": "==",
            "show_if_value": "1",
            "priority_order": 34,
        },
        {
            "code": "polyuria",
            "name": "Frequent urination",
            "question_text": "Frequent urination? (Yes/No)",
            "input_type": "BOOLEAN",
            "ui_section": "Symptoms",
            "category": "Classic",
            "priority_order": 100,
        },
        {
            "code": "polyuria_pattern",
            "name": "Urination pattern",
            "question_text": "How would you describe the urination pattern?",
            "input_type": "SINGLE",
            "options_json": ["DAYTIME", "NIGHT_ONLY", "DAY_AND_NIGHT", "NOT_SURE"],
            "ui_section": "Symptoms",
            "category": "Detail",
            "parent_code": "polyuria",
            "show_if_operator": "==",
            "show_if_value": "1",
            "priority_order": 105,
        },
        {
            "code": "polydipsia",
            "name": "Very thirsty",
            "question_text": "Very thirsty? (Yes/No)",
            "input_type": "BOOLEAN",
            "ui_section": "Symptoms",
            "category": "Classic",
            "priority_order": 110,
        },
        {
            "code": "polydipsia_severity",
            "name": "Thirst severity",
            "question_text": "How would you describe the thirst severity?",
            "input_type": "SINGLE",
            "options_json": ["MILD", "MODERATE", "SEVERE", "NOT_SURE"],
            "ui_section": "Symptoms",
            "category": "Detail",
            "parent_code": "polydipsia",
            "show_if_operator": "==",
            "show_if_value": "1",
            "priority_order": 115,
        },
        {
            "code": "weight_loss",
            "name": "Unexplained weight loss",
            "question_text": "Unexplained weight loss? (Yes/No)",
            "input_type": "BOOLEAN",
            "ui_section": "Symptoms",
            "category": "Classic",
            "priority_order": 120,
        },
        {
            "code": "fatigue",
            "name": "Fatigue or weakness",
            "question_text": "Fatigue or unusual weakness? (Yes/No)",
            "input_type": "BOOLEAN",
            "ui_section": "Symptoms",
            "category": "General",
            "priority_order": 130,
        },
        {
            "code": "blurred_vision",
            "name": "Blurred vision",
            "question_text": "Blurred vision? (Yes/No)",
            "input_type": "BOOLEAN",
            "ui_section": "Symptoms",
            "category": "General",
            "priority_order": 140,
        },
        {
            "code": "overweight",
            "name": "Overweight",
            "question_text": "Are you overweight for your height? (Yes/No)",
            "input_type": "BOOLEAN",
            "ui_section": "Risk",
            "category": "Risk",
            "priority_order": 200,
        },
        {
            "code": "inactive",
            "name": "Physically inactive",
            "question_text": "Less than 150 minutes exercise per week? (Yes/No)",
            "input_type": "BOOLEAN",
            "ui_section": "Risk",
            "category": "Risk",
            "priority_order": 210,
        },
        {
            "code": "family_history",
            "name": "Family history of diabetes",
            "question_text": "Family history of diabetes? (Yes/No)",
            "input_type": "BOOLEAN",
            "ui_section": "Risk",
            "category": "Risk",
            "priority_order": 220,
        },
        {
            "code": "high_bp",
            "name": "High blood pressure",
            "question_text": "Have you been told you have high blood pressure? (Yes/No)",
            "input_type": "BOOLEAN",
            "ui_section": "Risk",
            "category": "Risk",
            "priority_order": 225,
        },
        {
            "code": "gestational_diabetes_history",
            "name": "Gestational diabetes history",
            "question_text": "History of gestational diabetes during pregnancy? (Yes/No)",
            "input_type": "BOOLEAN",
            "ui_section": "Risk",
            "category": "Risk",
            "priority_order": 230,
        },
        {
            "code": "PREGNANT",
            "name": "Currently pregnant",
            "question_text": "Are you currently pregnant? (Yes/No)",
            "input_type": "BOOLEAN",
            "allow_unknown": True,
            "ui_section": "Risk",
            "category": "Pregnancy",
            "priority_order": 231,
        },
        {
            "code": "age_years",
            "name": "Age",
            "question_text": "Age (years)",
            "input_type": "NUMBER",
            "unit": "years",
            "ui_section": "Risk",
            "category": "Risk",
            "priority_order": 240,
        },
    ],
    "diseases": [
        {
            "code": "TYPE2_DM",
            "name": "Type 2 Diabetes",
            "description": "Lab-confirmed pattern suggests diabetes. Please consult a clinician for confirmation and treatment planning.",
            "category": "diabetes",
            "severity_level": "HIGH",
            "patient_label_screening": "Possible Type 2 Diabetes (needs labs to confirm)",
            "patient_label_confirmed": "Type 2 Diabetes - likely/confirmed",
            "default_next_steps": "Book clinician follow-up.\nAsk for HbA1c + fasting plasma glucose.\nMonitor blood glucose as advised.",
            "red_flag_message": "If severe dehydration, persistent vomiting, confusion, or drowsiness develops, seek urgent care.",
        },
        {
            "code": "PREDIABETES",
            "name": "Prediabetes Risk",
            "description": "Risk factors indicate prediabetes risk. Lifestyle changes and follow-up testing are recommended.",
            "category": "diabetes",
            "severity_level": "MEDIUM",
            "patient_label_screening": "Possible Prediabetes (screening result)",
            "patient_label_confirmed": "Prediabetes - likely",
            "default_next_steps": "Improve nutrition quality.\nExercise at least 150 minutes per week.\nRepeat lab tests in 3-6 months.",
        },
        {
            "code": "GDM_RISK",
            "name": "Gestational Diabetes Risk",
            "description": "History suggests gestational diabetes risk. Discuss pregnancy-safe screening with your clinician.",
            "category": "pregnancy",
            "severity_level": "MEDIUM",
            "patient_label_screening": "Possible Gestational Diabetes Risk (screening)",
            "patient_label_confirmed": "Gestational Diabetes Risk - likely",
            "default_next_steps": "Schedule obstetric review.\nAsk about pregnancy-safe glucose screening such as OGTT/FPG/HbA1c.",
        },
        {
            "code": "GDM",
            "name": "Gestational Diabetes Mellitus",
            "description": "Pregnancy glucose thresholds are in the diagnostic range for gestational diabetes.",
            "category": "gestational",
            "severity_level": "MEDIUM",
            "patient_label_screening": "Possible Gestational Diabetes (needs clinical confirmation)",
            "patient_label_confirmed": "Gestational Diabetes Mellitus",
            "default_next_steps": "Confirm with obstetric team and begin pregnancy-safe glucose management.",
        },
        {
            "code": "NEED_LABS",
            "name": "Needs Lab Confirmation",
            "description": "Symptoms indicate risk. Add lab values to improve confidence and confirm diagnosis.",
            "category": "screening",
            "severity_level": "MEDIUM",
            "patient_label_screening": "Possible Diabetes Risk (needs labs to confirm)",
            "patient_label_confirmed": "Pending Lab Confirmation",
            "default_next_steps": "Add HbA1c, fasting plasma glucose, or random glucose values to confirm the result.",
        },
        {
            "code": "LOW_RISK",
            "name": "Low Risk (Screening)",
            "description": "Current symptom and risk pattern suggests low screening risk.",
            "category": "screening",
            "severity_level": "LOW",
            "patient_label_screening": "Low Diabetes Risk (screening)",
            "patient_label_confirmed": "Low Diabetes Risk",
            "default_next_steps": "Maintain healthy lifestyle habits.\nRepeat screening if symptoms change.",
        },
    ],
    "rules": [
        {
            "rule_code": "R_DGN_001",
            "title": "Diabetes by FBS",
            "rule_type": "diagnostic",
            "disease_code": "TYPE2_DM",
            "base_confidence": 0.92,
            "max_conf_without_labs": 0.70,
            "risk_level": "HIGH",
            "priority": 140,
            "is_active": True,
            "explanation_text": "FBS >= 126 mg/dL meets a diabetes diagnostic threshold.",
            "conditions": [
                {"symptom_code": "FBS", "operator": "GTE", "values": [126], "weight": 1.0, "is_required": True},
            ],
        },
        {
            "rule_code": "R_DGN_002",
            "title": "Diabetes by HbA1c",
            "rule_type": "diagnostic",
            "disease_code": "TYPE2_DM",
            "base_confidence": 0.92,
            "max_conf_without_labs": 0.70,
            "risk_level": "HIGH",
            "priority": 139,
            "is_active": True,
            "explanation_text": "HbA1c >= 6.5% meets a diabetes diagnostic threshold.",
            "conditions": [
                {"symptom_code": "HBA1C", "operator": "GTE", "values": [6.5], "weight": 1.0, "is_required": True},
            ],
        },
        {
            "rule_code": "R_DGN_003",
            "title": "Prediabetes by FBS",
            "rule_type": "diagnostic",
            "disease_code": "PREDIABETES",
            "base_confidence": 0.88,
            "max_conf_without_labs": 0.75,
            "risk_level": "MEDIUM",
            "priority": 132,
            "is_active": True,
            "explanation_text": "FBS between 100 and 125 mg/dL supports prediabetes diagnosis.",
            "conditions": [
                {"symptom_code": "FBS", "operator": "BETWEEN", "values": [100, 125], "weight": 1.0, "is_required": True},
            ],
        },
        {
            "rule_code": "R_DGN_004",
            "title": "Prediabetes by HbA1c",
            "rule_type": "diagnostic",
            "disease_code": "PREDIABETES",
            "base_confidence": 0.88,
            "max_conf_without_labs": 0.75,
            "risk_level": "MEDIUM",
            "priority": 131,
            "is_active": True,
            "explanation_text": "HbA1c between 5.7% and 6.4% supports prediabetes diagnosis.",
            "conditions": [
                {"symptom_code": "HBA1C", "operator": "BETWEEN", "values": [5.7, 6.4], "weight": 1.0, "is_required": True},
            ],
        },
        {
            "rule_code": "R_DGN_005",
            "title": "GDM one-step 75g OGTT",
            "rule_type": "diagnostic",
            "disease_code": "GDM",
            "base_confidence": 0.94,
            "max_conf_without_labs": 0.70,
            "risk_level": "HIGH",
            "priority": 145,
            "is_active": True,
            "min_required_matches": 1,
            "explanation_text": "Pregnancy plus any abnormal 75g OGTT value (fasting/1h/2h) confirms GDM threshold.",
            "conditions": [
                {"symptom_code": "PREGNANT", "operator": "EQ", "value": "1", "weight": 1.0, "is_required": True},
                {"symptom_code": "OGTT75_FAST", "operator": "GTE", "values": [92], "weight": 1.0, "is_required": False},
                {"symptom_code": "OGTT75_1H", "operator": "GTE", "values": [180], "weight": 1.0, "is_required": False},
                {"symptom_code": "OGTT75_2H", "operator": "GTE", "values": [153], "weight": 1.0, "is_required": False},
            ],
        },
        {
            "rule_code": "R_SCR_001",
            "title": "High Risk Symptoms Pattern",
            "rule_type": "screening",
            "disease_code": "NEED_LABS",
            "base_confidence": 0.76,
            "confidence_cap_if_unconfirmed": 0.60,
            "confidence_bonus_max": 0.20,
            "risk_level": "MEDIUM",
            "priority": 70,
            "is_active": True,
            "explanation_text": "Classic symptom pattern indicates elevated risk; labs recommended for confirmation.",
            "conditions": [
                {"symptom_code": "polyuria", "operator": "==", "value": "1", "weight": 1.0, "is_required": True},
                {"symptom_code": "polydipsia", "operator": "==", "value": "1", "weight": 1.0, "is_required": True},
                {"symptom_code": "weight_loss", "operator": "==", "value": "1", "weight": 0.8, "is_required": False},
                {"symptom_code": "has_labs", "operator": "==", "value": "0", "weight": 0.4, "is_required": False},
            ],
        },
        {
            "rule_code": "R_SCR_004",
            "title": "Moderate Symptoms Pattern",
            "rule_type": "screening",
            "disease_code": "NEED_LABS",
            "base_confidence": 0.68,
            "confidence_cap_if_unconfirmed": 0.58,
            "confidence_bonus_max": 0.18,
            "risk_level": "MEDIUM",
            "priority": 66,
            "is_active": True,
            "explanation_text": "Two classic symptoms indicate moderate diabetes risk and need for lab confirmation.",
            "conditions": [
                {"symptom_code": "polyuria", "operator": "==", "value": "1", "weight": 1.0, "is_required": True},
                {"symptom_code": "polydipsia", "operator": "==", "value": "1", "weight": 1.0, "is_required": True},
                {"symptom_code": "has_labs", "operator": "==", "value": "0", "weight": 0.4, "is_required": False},
            ],
        },
        {
            "rule_code": "R_SCR_002",
            "title": "Prediabetes Risk Factors",
            "rule_type": "screening",
            "disease_code": "PREDIABETES",
            "base_confidence": 0.64,
            "confidence_cap_if_unconfirmed": 0.60,
            "confidence_bonus_max": 0.20,
            "risk_level": "MEDIUM",
            "priority": 60,
            "is_active": True,
            "explanation_text": "Multiple risk factors suggest prediabetes risk.",
            "conditions": [
                {"symptom_code": "overweight", "operator": "==", "value": "1", "weight": 1.0, "is_required": True},
                {"symptom_code": "inactive", "operator": "==", "value": "1", "weight": 1.0, "is_required": True},
                {"symptom_code": "family_history", "operator": "==", "value": "1", "weight": 0.7, "is_required": False},
            ],
        },
        {
            "rule_code": "R_SCR_005",
            "title": "Metabolic Syndrome Screening Pattern",
            "rule_type": "screening",
            "disease_code": "PREDIABETES",
            "base_confidence": 0.66,
            "confidence_cap_if_unconfirmed": 0.62,
            "confidence_bonus_max": 0.20,
            "risk_level": "MEDIUM",
            "priority": 62,
            "is_active": True,
            "explanation_text": "Metabolic risk cluster (weight, inactivity, blood pressure) suggests elevated prediabetes risk.",
            "conditions": [
                {"symptom_code": "overweight", "operator": "==", "value": "1", "weight": 1.0, "is_required": True},
                {"symptom_code": "inactive", "operator": "==", "value": "1", "weight": 1.0, "is_required": True},
                {"symptom_code": "high_bp", "operator": "==", "value": "1", "weight": 0.8, "is_required": False},
                {"symptom_code": "family_history", "operator": "==", "value": "1", "weight": 0.6, "is_required": False},
            ],
        },
        {
            "rule_code": "R_SCR_003",
            "title": "Gestational Diabetes Risk Screen",
            "rule_type": "screening",
            "disease_code": "GDM_RISK",
            "base_confidence": 0.70,
            "confidence_cap_if_unconfirmed": 0.60,
            "confidence_bonus_max": 0.20,
            "risk_level": "MEDIUM",
            "priority": 65,
            "is_active": True,
            "explanation_text": "Gestational diabetes history is a strong risk indicator and should trigger pregnancy-focused screening.",
            "conditions": [
                {"symptom_code": "gestational_diabetes_history", "operator": "==", "value": "1", "weight": 1.0, "is_required": True},
            ],
        },
        {
            "rule_code": "R_SCR_006",
            "title": "Age-Based Prediabetes Risk",
            "rule_type": "screening",
            "disease_code": "PREDIABETES",
            "base_confidence": 0.60,
            "confidence_cap_if_unconfirmed": 0.55,
            "confidence_bonus_max": 0.18,
            "risk_level": "MEDIUM",
            "priority": 58,
            "is_active": True,
            "explanation_text": "Age >= 45 years with added risk factors increases prediabetes risk.",
            "conditions": [
                {"symptom_code": "age_years", "operator": ">=", "value": "45", "weight": 1.0, "is_required": True},
                {"symptom_code": "overweight", "operator": "==", "value": "1", "weight": 0.8, "is_required": False},
                {"symptom_code": "high_bp", "operator": "==", "value": "1", "weight": 0.6, "is_required": False},
            ],
        },
        {
            "rule_code": "R_SCR_007",
            "title": "Low Risk Screening Baseline",
            "rule_type": "screening",
            "disease_code": "LOW_RISK",
            "base_confidence": 0.56,
            "confidence_cap_if_unconfirmed": 0.56,
            "confidence_bonus_max": 0.12,
            "risk_level": "LOW",
            "priority": 20,
            "is_active": True,
            "explanation_text": "No major classic symptoms or key lifestyle risk factors were identified.",
            "conditions": [
                {"symptom_code": "polyuria", "operator": "==", "value": "0", "weight": 1.0, "is_required": True},
                {"symptom_code": "polydipsia", "operator": "==", "value": "0", "weight": 1.0, "is_required": True},
                {"symptom_code": "weight_loss", "operator": "==", "value": "0", "weight": 0.9, "is_required": True},
                {"symptom_code": "overweight", "operator": "==", "value": "0", "weight": 0.8, "is_required": False},
                {"symptom_code": "inactive", "operator": "==", "value": "0", "weight": 0.8, "is_required": False},
            ],
        },
    ],
}


def _norm_confidence(raw: Any) -> float:
    value = float(raw if raw is not None else 0.5)
    if value > 1.0:
        value = value / 100.0
    return max(0.0, min(1.0, value))


def _norm_optional_confidence(raw: Any) -> Optional[float]:
    if raw is None or raw == "":
        return None
    return _norm_confidence(raw)


def _upsert_symptom(row: Dict[str, Any]) -> Symptom:
    code = str(row["code"]).strip()
    symptom = Symptom.query.filter_by(code=code).first()
    if not symptom:
        symptom = Symptom(code=code)
        db.session.add(symptom)

    symptom.name = row["name"]
    symptom.question_text = row["question_text"]
    symptom.input_type = row["input_type"]
    symptom.unit = row.get("unit")
    symptom.options_json = row.get("options_json")
    symptom.category = row.get("category")
    symptom.ui_section = row.get("ui_section")
    symptom.allow_unknown = bool(row.get("allow_unknown", False))
    symptom.min_value = row.get("min_value")
    symptom.max_value = row.get("max_value")
    symptom.reference_ranges_json = row.get("reference_ranges_json")
    symptom.priority_order = int(row.get("priority_order", 0) or 0)
    symptom.is_active = bool(row.get("is_active", True))

    symptom.parent_symptom_id = None
    symptom.show_if_operator = row.get("show_if_operator")
    symptom.show_if_value = row.get("show_if_value")
    return symptom


def _apply_parent_links(symptom_rows: List[Dict[str, Any]]) -> None:
    by_code = {symptom.code: symptom for symptom in Symptom.query.all()}
    for row in symptom_rows:
        parent_code = row.get("parent_code")
        if not parent_code:
            continue
        child = by_code.get(row["code"])
        parent = by_code.get(parent_code)
        if not child or not parent:
            raise ValueError(f"Invalid parent link: {row['code']} -> {parent_code}")
        child.parent_symptom_id = parent.id
        child.show_if_operator = row.get("show_if_operator") or "=="
        child.show_if_value = row.get("show_if_value") or "1"


def _upsert_disease(row: Dict[str, Any]) -> Disease:
    def _normalize_category(raw: Any) -> str:
        value = str(raw or "").strip().lower()
        if value in {"type1", "t1dm", "type_1", "type-1"}:
            return "type1"
        if value in {"type2", "t2dm", "type_2", "type-2", "diabetes"}:
            return "type2"
        if value in {"prediabetes", "predm", "pre_dm", "pre-diabetes"}:
            return "prediabetes"
        if value in {"gestational", "gdm", "pregnancy"}:
            return "gestational"
        return "other"

    def _normalize_severity(raw: Any) -> str:
        value = str(raw or "low").strip().lower()
        if value == "high":
            return "high"
        if value == "medium":
            return "medium"
        if value == "urgent":
            return "high"
        return "low"

    code = str(row["code"]).strip().upper()
    disease = Disease.query.filter_by(code=code).first()
    if not disease:
        disease = Disease(code=code)
        db.session.add(disease)

    disease.name = row["name"]
    disease.description = row.get("description")
    disease.category = _normalize_category(row.get("category"))
    disease.severity_level = _normalize_severity(row.get("severity_level"))
    disease.default_recommendation = row.get("default_recommendation") or row.get("default_next_steps")
    disease.active = bool(row.get("active", row.get("is_active", True)))
    return disease


def _risk_from_disease(disease: Disease) -> str:
    level = (disease.severity_level or "LOW").upper()
    if level == "HIGH":
        return "HIGH"
    if level == "MEDIUM":
        return "MEDIUM"
    return "LOW"


def _active_rule_set(version: int = 2) -> RuleSet:
    row = RuleSet.query.filter_by(version=version).first()
    if not row:
        row = RuleSet(version=version, active=True)
        db.session.add(row)
        db.session.flush()
    elif not row.active:
        row.active = True
    return row


def _replace_rule_conditions(rule: Rule, conditions: List[Dict[str, Any]], symptom_by_code: Dict[str, Symptom]) -> None:
    RuleCondition.query.filter_by(rule_id=rule.id).delete()

    seen_codes = set()
    for row in conditions:
        symptom_code = str(row["symptom_code"]).strip()
        if symptom_code in seen_codes:
            raise ValueError(f"Duplicate symptom in rule {rule.rule_code}: {symptom_code}")
        seen_codes.add(symptom_code)

        symptom = symptom_by_code.get(symptom_code)
        if not symptom:
            raise ValueError(f"Unknown symptom code in rule {rule.rule_code}: {symptom_code}")

        operator = str(row.get("operator") or "==").upper()
        if operator == "EQ":
            operator = "EQ"
        elif operator == "NEQ":
            operator = "!="
        elif operator == "GT":
            operator = ">"
        elif operator == "LT":
            operator = "<"
        elif operator == "GTE":
            operator = "GTE"
        elif operator == "LTE":
            operator = "<="
        if operator not in VALID_OPERATORS:
            raise ValueError(f"Invalid operator for {rule.rule_code}: {operator}")

        raw_value = row.get("value")
        raw_values = row.get("values")
        values_json = None
        if raw_values is not None:
            if isinstance(raw_values, list):
                values_json = raw_values
            else:
                values_json = [raw_values]

        if operator in {"PRESENT", "ABSENT"}:
            value = None
        elif values_json is not None:
            value = None if not values_json else str(values_json[0])
        elif raw_value is None:
            value = None
        else:
            value = str(raw_value)

        is_required = bool(row.get("is_required", True))
        if (rule.rule_type or "screening").lower() == "screening" and symptom.code.lower() == "has_labs":
            is_required = False

        condition = RuleCondition(
            rule_id=rule.id,
            symptom_id=symptom.id,
            finding_code=symptom.code,
            operator=operator,
            value=value,
            values_json=values_json,
            score_points=int(row.get("score_points", 0) or 0),
            weight=float(row.get("weight", 1.0) or 0),
            is_required=is_required,
            negate=bool(row.get("negate", False)),
        )
        db.session.add(condition)


def _sync_legacy_action(rule: Rule, disease: Disease, confidence: float) -> None:
    existing = RuleAction.query.filter_by(rule_id=rule.id).all()
    target = next((item for item in existing if item.disease_id == disease.id), None)

    if target:
        target.confidence = confidence
    else:
        target = RuleAction(rule_id=rule.id, disease_id=disease.id, confidence=confidence)
        db.session.add(target)
        db.session.flush()

    for action in existing:
        if action.id != target.id:
            db.session.delete(action)


def _upsert_rule(
    row: Dict[str, Any],
    disease_by_code: Dict[str, Disease],
    symptom_by_code: Dict[str, Symptom],
    rule_set: Optional[RuleSet] = None,
) -> Rule:
    rule_code = str(row["rule_code"]).strip().upper()
    disease_code = str(row["disease_code"]).strip().upper()

    disease = disease_by_code.get(disease_code)
    if not disease:
        raise ValueError(f"Rule {rule_code} points to unknown disease code: {disease_code}")

    rule = Rule.query.filter_by(rule_code=rule_code).first()
    if not rule:
        rule = Rule(rule_code=rule_code)
        db.session.add(rule)

    confidence = _norm_confidence(row.get("base_confidence"))
    risk_level = str(row.get("risk_level") or _risk_from_disease(disease) or "LOW").upper()

    rule.title = row["title"]
    rule.rule_type = str(row.get("rule_type") or "screening").lower()
    rule.version = int(row.get("version", 1) or 1)
    rule.priority = int(row.get("priority", 0) or 0)
    rule.is_active = bool(row.get("is_active", True))
    doctor_response_template = row.get("doctor_response_template") or row.get("explanation_text")
    rule.patient_summary_template = row.get("patient_summary_template")
    rule.doctor_response_template = doctor_response_template
    rule.advice_template = row.get("advice_template")
    rule.explanation_text = doctor_response_template
    rule.disease_id = disease.id
    if rule_set:
        rule.rule_set_id = rule_set.id
    rule.base_confidence = confidence
    rule.confidence_cap_if_unconfirmed = _norm_optional_confidence(
        row.get("max_conf_without_labs", row.get("confidence_cap_if_unconfirmed"))
    )
    rule.confidence_bonus_max = _norm_optional_confidence(row.get("confidence_bonus_max"))
    rule.min_required_matches = int(row.get("min_required_matches")) if row.get("min_required_matches") not in (None, "") else None
    rule.stop_on_match = bool(row.get("stop_on_match", False))
    rule.risk_level = risk_level

    db.session.flush()

    _replace_rule_conditions(rule, row.get("conditions") or [], symptom_by_code)
    _sync_legacy_action(rule, disease, confidence)
    return rule


def seed_kb_v2(deactivate_missing: bool = False) -> None:
    print("Seeding KB v2 blueprint...")

    symptom_rows = KB_BLUEPRINT_V2["symptoms"]
    disease_rows = KB_BLUEPRINT_V2["diseases"]
    rule_rows = KB_BLUEPRINT_V2["rules"]

    for row in symptom_rows:
        _upsert_symptom(row)
    db.session.flush()
    _apply_parent_links(symptom_rows)

    for row in disease_rows:
        _upsert_disease(row)
    db.session.flush()

    symptom_by_code = {symptom.code: symptom for symptom in Symptom.query.all()}
    disease_by_code = {disease.code: disease for disease in Disease.query.all()}
    active_rule_set = _active_rule_set(version=2)

    for row in rule_rows:
        _upsert_rule(
            row,
            disease_by_code=disease_by_code,
            symptom_by_code=symptom_by_code,
            rule_set=active_rule_set,
        )

    if deactivate_missing:
        symptom_codes = {row["code"] for row in symptom_rows}
        rule_codes = {str(row["rule_code"]).strip().upper() for row in rule_rows}
        disease_codes = {str(row["code"]).strip().upper() for row in disease_rows}

        for symptom in Symptom.query.filter(~Symptom.code.in_(symptom_codes)).all():
            symptom.is_active = False
        for rule in Rule.query.filter(~Rule.rule_code.in_(rule_codes)).all():
            rule.is_active = False
        for disease in Disease.query.filter(~Disease.code.in_(disease_codes)).all():
            disease.active = False

    db.session.commit()
    print(
        "KB v2 seed complete: "
        f"{len(symptom_rows)} symptoms, "
        f"{len(disease_rows)} diseases, "
        f"{len(rule_rows)} rules"
    )


def main() -> None:
    import argparse
    from app import create_app

    parser = argparse.ArgumentParser(description="Seed KB v2 blueprint")
    parser.add_argument(
        "--deactivate-missing",
        action="store_true",
        help="Mark symptoms/rules/diseases not in blueprint as inactive",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        seed_kb_v2(deactivate_missing=args.deactivate_missing)


if __name__ == "__main__":
    main()
