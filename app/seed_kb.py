import os
from datetime import datetime

if __name__ == "__main__":
    from dotenv import load_dotenv
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    load_dotenv(env_path, override=True)

from app.extensions import db
from app.models import Symptom, Rule, RuleCondition, RuleAction, Disease

def upsert_symptom(row):
    """
    row keys:
      code, name, question_text, input_type,
      ui_section, category, unit, options_json,
      priority_order, is_active,
      parent_code, show_if_operator, show_if_value
    """
    s = Symptom.query.filter_by(code=row["code"]).first()
    if not s:
        s = Symptom(code=row["code"])
        db.session.add(s)

    s.name = row["name"]
    s.question_text = row["question_text"]
    s.input_type = row["input_type"]
    s.ui_section = row.get("ui_section")
    s.category = row.get("category")
    s.unit = row.get("unit")
    s.options_json = row.get("options_json")
    s.priority_order = row.get("priority_order", 0)
    s.is_active = row.get("is_active", True)

    # parent linkage in second pass
    s.parent_symptom_id = None
    s.show_if_operator = row.get("show_if_operator")
    s.show_if_value = row.get("show_if_value")

    return s

def upsert_disease(code, name, urgency, advice, severity="INFO", rec=None):
    d = Disease.query.filter_by(code=code).first()
    if not d:
        d = Disease(code=code)
        db.session.add(d)
    d.name = name
    d.urgency = urgency
    d.advice = advice
    d.severity = severity
    d.recommendations_json = rec or {}
    d.is_active = True
    return d

def upsert_rule(rule_code, title, priority, explanation_text=None):
    r = Rule.query.filter_by(rule_code=rule_code).first()
    if not r:
        r = Rule(rule_code=rule_code)
        db.session.add(r)
    r.title = title
    r.priority = priority
    r.is_active = True
    r.explanation_text = explanation_text
    return r

def set_rule_conditions(rule, conditions, symptoms_by_code):
    """
    conditions: list of (symptom_code, operator, value_str, weight, is_required)
    IMPORTANT: your schema has UNIQUE(rule_id, symptom_id) so:
      - do not put two conditions on the same symptom in the same rule
    """
    # clear existing
    RuleCondition.query.filter_by(rule_id=rule.id).delete()

    for scode, op, val, weight, required in conditions:
        sym = symptoms_by_code[scode]
        rc = RuleCondition(
            rule_id=rule.id,
            symptom_id=sym.id,
            operator=op,
            value=val,
            weight=weight,
            is_required=required,
            created_at=datetime.utcnow(),
        )
        db.session.add(rc)

def set_rule_action(rule, disease, confidence):
    # clear existing actions for simplicity
    RuleAction.query.filter_by(rule_id=rule.id).delete()

    ra = RuleAction(
        rule_id=rule.id,
        disease_id=disease.id,
        confidence=confidence,
        created_at=datetime.utcnow(),
    )
    db.session.add(ra)

def seed_full_kb():
    print("🌱 Seeding FULL KB bank (symptoms + triggers + diseases + rules)...")

    # ----------------------------
    # SYMPTOMS (root + children)
    # ----------------------------
    SYMPTOMS = [
        # Root: Labs gate
        dict(code="has_labs", name="Recent lab results",
             question_text="Do you have recent blood test results? (Yes/No)",
             input_type="BOOLEAN", ui_section="Start", category="Gate",
             priority_order=1),

        # Lab children (shown only if has_labs == YES)
        dict(code="fpg", name="Fasting Plasma Glucose",
             question_text="Fasting plasma glucose (mg/dL)", input_type="NUMBER",
             unit="mg/dL", ui_section="Labs", category="Labs",
             parent_code="has_labs", show_if_operator="==", show_if_value="1",
             priority_order=10),

        dict(code="hba1c", name="HbA1c",
             question_text="HbA1c (%)", input_type="NUMBER",
             unit="%", ui_section="Labs", category="Labs",
             parent_code="has_labs", show_if_operator="==", show_if_value="1",
             priority_order=20),

        dict(code="random_glucose", name="Random glucose",
             question_text="Random glucose (mg/dL)", input_type="NUMBER",
             unit="mg/dL", ui_section="Labs", category="Labs",
             parent_code="has_labs", show_if_operator="==", show_if_value="1",
             priority_order=30),

        # Root symptoms (classic)
        dict(code="polyuria", name="Frequent urination",
             question_text="Frequent urination? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Classic",
             priority_order=100),

        dict(code="polydipsia", name="Very thirsty",
             question_text="Very thirsty? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Classic",
             priority_order=110),

        dict(code="polyphagia", name="Increased hunger",
             question_text="Increased hunger? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Classic",
             priority_order=120),

        dict(code="weight_loss", name="Unexplained weight loss",
             question_text="Unexplained weight loss? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Classic",
             priority_order=130),

        dict(code="fatigue", name="Fatigue/weakness",
             question_text="Fatigue or weakness? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="General",
             priority_order=140),

        dict(code="blurred_vision", name="Blurred vision",
             question_text="Blurred vision? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="General",
             priority_order=150),

        dict(code="slow_healing", name="Slow healing wounds",
             question_text="Cuts/wounds heal slowly? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="General",
             priority_order=160),

        dict(code="tingling", name="Tingling/numbness",
             question_text="Tingling or numbness in hands/feet? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Complications",
             priority_order=170),

        dict(code="recurrent_infections", name="Frequent infections",
             question_text="Frequent infections (skin/gum/urinary)? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Complications",
             priority_order=180),

        dict(code="nausea_vomit", name="Nausea/vomiting",
             question_text="Nausea or vomiting? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Warning",
             priority_order=190),

        # Risk factors (root)
        dict(code="family_history", name="Family history",
             question_text="Family history of diabetes? (Yes/No)",
             input_type="BOOLEAN", ui_section="Risk", category="Risk",
             priority_order=300),

        dict(code="overweight", name="Overweight",
             question_text="Are you overweight for your height? (Yes/No)",
             input_type="BOOLEAN", ui_section="Risk", category="Risk",
             priority_order=310),

        dict(code="inactive", name="Physically inactive",
             question_text="Less than 150 minutes exercise per week? (Yes/No)",
             input_type="BOOLEAN", ui_section="Risk", category="Risk",
             priority_order=320),

        dict(code="high_bp", name="High blood pressure",
             question_text="Have you been told you have high blood pressure? (Yes/No)",
             input_type="BOOLEAN", ui_section="Risk", category="Risk",
             priority_order=330),

        dict(code="prediabetes_history", name="History of prediabetes",
             question_text="Were you told you have prediabetes/high sugar before? (Yes/No)",
             input_type="BOOLEAN", ui_section="Risk", category="Risk",
             priority_order=340),

        dict(code="gestational_diabetes", name="Gestational diabetes history",
             question_text="History of gestational diabetes during pregnancy? (Yes/No)",
             input_type="BOOLEAN", ui_section="Risk", category="Risk",
             priority_order=350),

        dict(code="darkened_skin", name="Darkened skin patches",
             question_text="Darkened skin patches on neck/armpits? (Yes/No)",
             input_type="BOOLEAN", ui_section="Risk", category="Risk",
             priority_order=360),

        # ----------------
        # Children of polyuria
        # ----------------
        dict(code="urination_onset", name="Urination onset",
             question_text="Onset (Sudden/Gradual/Not sure)",
             input_type="SINGLE", options_json=["SUDDEN", "GRADUAL", "NOT_SURE"],
             ui_section="Symptoms", category="Detail",
             parent_code="polyuria", show_if_operator="==", show_if_value="1",
             priority_order=101),

        dict(code="nocturia", name="Night urination",
             question_text="Do you wake up at night to urinate more? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Detail",
             parent_code="polyuria", show_if_operator="==", show_if_value="1",
             priority_order=102),

        # Children of polydipsia
        dict(code="dry_mouth", name="Dry mouth",
             question_text="Dry mouth frequently? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Detail",
             parent_code="polydipsia", show_if_operator="==", show_if_value="1",
             priority_order=111),

        dict(code="drinks_more_water", name="Drinks more water",
             question_text="Do you drink much more water than usual? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Detail",
             parent_code="polydipsia", show_if_operator="==", show_if_value="1",
             priority_order=112),

        # Children of weight_loss
        dict(code="weight_loss_duration", name="Weight loss duration",
             question_text="How long has the weight loss been happening?",
             input_type="SINGLE",
             options_json=["<2_WEEKS", "2_4_WEEKS", ">4_WEEKS", "NOT_SURE"],
             ui_section="Symptoms", category="Detail",
             parent_code="weight_loss", show_if_operator="==", show_if_value="1",
             priority_order=131),

        # Children of recurrent infections
        dict(code="uti_symptoms", name="Urinary infection symptoms",
             question_text="Burning/pain when urinating or UTI symptoms? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Detail",
             parent_code="recurrent_infections", show_if_operator="==", show_if_value="1",
             priority_order=181),

        dict(code="yeast_infections", name="Yeast infections",
             question_text="Frequent yeast infections? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Detail",
             parent_code="recurrent_infections", show_if_operator="==", show_if_value="1",
             priority_order=182),

        dict(code="skin_infections", name="Skin infections",
             question_text="Frequent skin infections/boils? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Detail",
             parent_code="recurrent_infections", show_if_operator="==", show_if_value="1",
             priority_order=183),

        # Children of tingling
        dict(code="tingling_feet", name="Tingling in feet",
             question_text="Tingling/numbness mainly in feet? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Detail",
             parent_code="tingling", show_if_operator="==", show_if_value="1",
             priority_order=171),

        dict(code="tingling_hands", name="Tingling in hands",
             question_text="Tingling/numbness mainly in hands? (Yes/No)",
             input_type="BOOLEAN", ui_section="Symptoms", category="Detail",
             parent_code="tingling", show_if_operator="==", show_if_value="1",
             priority_order=172),

        # Children of overweight (optional BMI flow)
        dict(code="bmi_known", name="Know BMI",
             question_text="Do you know your BMI? (Yes/No)",
             input_type="BOOLEAN", ui_section="Risk", category="Detail",
             parent_code="overweight", show_if_operator="==", show_if_value="1",
             priority_order=311),

        dict(code="bmi_value", name="BMI value",
             question_text="Enter your BMI", input_type="NUMBER",
             ui_section="Risk", category="Detail",
             parent_code="bmi_known", show_if_operator="==", show_if_value="1",
             priority_order=312),

        dict(code="height_cm", name="Height (cm)",
             question_text="Enter your height (cm)", input_type="NUMBER", unit="cm",
             ui_section="Risk", category="Detail",
             parent_code="bmi_known", show_if_operator="==", show_if_value="0",
             priority_order=313),

        dict(code="weight_kg", name="Weight (kg)",
             question_text="Enter your weight (kg)", input_type="NUMBER", unit="kg",
             ui_section="Risk", category="Detail",
             parent_code="bmi_known", show_if_operator="==", show_if_value="0",
             priority_order=314),
    ]

    # Pass 1: upsert all symptoms (no parent ids yet)
    desired_codes = {row["code"] for row in SYMPTOMS}
    symptoms_by_code = {}
    for row in SYMPTOMS:
        s = upsert_symptom(row)
        db.session.flush()
        symptoms_by_code[row["code"]] = s
    db.session.commit()

    # Deactivate any legacy symptoms not in this KB set
    legacy = Symptom.query.filter(~Symptom.code.in_(desired_codes)).all()
    for symptom in legacy:
        symptom.is_active = False
    db.session.commit()

    # Pass 2: resolve parent_code -> parent_symptom_id and set triggers
    for row in SYMPTOMS:
        pcode = row.get("parent_code")
        if pcode:
            child = Symptom.query.filter_by(code=row["code"]).first()
            parent = Symptom.query.filter_by(code=pcode).first()
            child.parent_symptom_id = parent.id
            child.show_if_operator = row.get("show_if_operator", "==")
            child.show_if_value = row.get("show_if_value", "1")
    db.session.commit()

    # ----------------------------
    # DISEASES (outcomes)
    # ----------------------------
    d_dm = upsert_disease(
        "DIABETES", "Diabetes likely", "HIGH",
        "Your results suggest diabetes. Please seek clinical confirmation and a management plan.",
        severity="DANGER",
        rec={"tests": ["Fasting plasma glucose", "HbA1c"], "actions": ["Consult clinician", "Monitor glucose"]}
    )
    d_pre = upsert_disease(
        "PREDIABETES", "Prediabetes risk", "MEDIUM",
        "Your results suggest increased risk. Lifestyle changes and follow-up testing are advised.",
        severity="WARN",
        rec={"actions": ["Diet improvements", "Exercise 150 min/week", "Repeat testing in 3-6 months"]}
    )
    d_low = upsert_disease(
        "LOW_RISK", "Low risk (screening)", "LOW",
        "Low risk based on your answers. Maintain healthy habits and recheck if symptoms change.",
        severity="INFO",
        rec={"actions": ["Balanced diet", "Stay active", "Annual screening"]}
    )
    d_need = upsert_disease(
        "NEED_LABS", "Need lab tests", "MEDIUM",
        "Symptoms suggest you should do lab tests (FPG/HbA1c) to confirm.",
        severity="WARN",
        rec={"tests": ["FPG", "HbA1c"], "note": "Screening only without labs"}
    )
    d_und = upsert_disease(
        "UNDETERMINED", "Undetermined", "LOW",
        "Not enough reliable data to decide. Answer more questions or consult a clinician.",
        severity="INFO",
        rec={"actions": ["Provide more symptoms", "Add lab data if available"]}
    )
    db.session.commit()

    # ----------------------------
    # RULES (simple & safe)
    # ----------------------------
    # Helper for boolean compare: store "1" / "0"
    # (Your facts store bool as 1/0, so conditions must match that)
    # LAB rules (highest priority)
    r = upsert_rule("R_DIAB_FPG", "Diabetes likely by FPG", 100,
                    "FPG ≥ 126 mg/dL strongly suggests diabetes.")
    db.session.commit()
    set_rule_conditions(r, [("fpg", ">=", "126", 1.0, True)], symptoms_by_code)
    set_rule_action(r, d_dm, 0.90)

    r = upsert_rule("R_DIAB_A1C", "Diabetes likely by HbA1c", 95,
                    "HbA1c ≥ 6.5% suggests diabetes.")
    db.session.commit()
    set_rule_conditions(r, [("hba1c", ">=", "6.5", 1.0, True)], symptoms_by_code)
    set_rule_action(r, d_dm, 0.85)

    # Screening rules (symptoms)
    r = upsert_rule("R_HIGH_SYMPTOMS", "High risk screening by classic symptoms", 60,
                    "Classic symptoms together suggest high risk; recommend labs.")
    db.session.commit()
    set_rule_conditions(r, [
        ("polyuria", "==", "1", 1.0, True),
        ("polydipsia", "==", "1", 1.0, True),
        ("weight_loss", "==", "1", 1.0, True),
    ], symptoms_by_code)
    set_rule_action(r, d_need, 0.75)

    r = upsert_rule("R_MODERATE_SYMPTOMS", "Moderate risk screening by symptoms", 50,
                    "Some classic symptoms suggest moderate risk; labs recommended.")
    db.session.commit()
    set_rule_conditions(r, [
        ("polyuria", "==", "1", 1.0, True),
        ("polydipsia", "==", "1", 1.0, True),
    ], symptoms_by_code)
    set_rule_action(r, d_need, 0.65)

    r = upsert_rule("R_RISK_FACTORS", "Moderate risk by risk factors", 40,
                    "Multiple risk factors suggest moderate risk; recommend screening.")
    db.session.commit()
    set_rule_conditions(r, [
        ("overweight", "==", "1", 1.0, True),
        ("inactive", "==", "1", 1.0, True),
        ("family_history", "==", "1", 1.0, True),
    ], symptoms_by_code)
    set_rule_action(r, d_pre, 0.60)

    # Low risk fallback (if explicitly no classic symptoms)
    r = upsert_rule("R_LOW_RISK", "Low risk screening", 10,
                    "No classic symptoms answered yes → low risk screening.")
    db.session.commit()
    set_rule_conditions(r, [
        ("polyuria", "==", "0", 1.0, True),
        ("polydipsia", "==", "0", 1.0, True),
        ("weight_loss", "==", "0", 1.0, True),
    ], symptoms_by_code)
    set_rule_action(r, d_low, 0.55)

    db.session.commit()
    print("✅ FULL KB seeded successfully.")

if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        seed_full_kb()
