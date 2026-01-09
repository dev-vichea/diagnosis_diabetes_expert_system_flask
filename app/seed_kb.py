from app.extensions import db
from app.models import Symptom, Rule, RuleCondition, Advice


def seed_demo_kb():
    print("🌱 Seeding demo Knowledge Base (symptoms, rules, advice)...")

    # ---------- Symptoms (Questions) ----------
    symptom_data = [
        ("polyuria", "Frequent urination?", 1),
        ("polydipsia", "Excessive thirst?", 2),
        ("weight_loss", "Unexplained weight loss?", 3),
        ("fatigue", "Unusual fatigue or weakness?", 4),
        ("blurred_vision", "Blurred vision?", 5),
        ("slow_healing", "Slow-healing wounds?", 6),
    ]

    symptoms = {}
    for code, q, order in symptom_data:
        s = Symptom.query.filter_by(code=code).first()
        if not s:
            s = Symptom(code=code, question_text=q, priority_order=order, is_active=True)
            db.session.add(s)
            db.session.commit()
        symptoms[code] = s

    # ---------- Rules ----------
    # Rule A: HIGH risk (3 strong symptoms)
    rule_high = Rule.query.filter_by(name="High Risk Diabetes Pattern").first()
    if not rule_high:
        rule_high = Rule(
            name="High Risk Diabetes Pattern",
            diagnosis_code="DIABETES_RISK",
            risk_level="HIGH",
            priority=10,
            is_active=True,
        )
        db.session.add(rule_high)
        db.session.commit()

    # Rule B: MODERATE risk (2 symptoms)
    rule_mod = Rule.query.filter_by(name="Moderate Risk Pattern").first()
    if not rule_mod:
        rule_mod = Rule(
            name="Moderate Risk Pattern",
            diagnosis_code="DIABETES_RISK",
            risk_level="MODERATE",
            priority=5,
            is_active=True,
        )
        db.session.add(rule_mod)
        db.session.commit()

    # ---------- Rule Conditions (IF parts) ----------
    def link_condition(rule_id: int, symptom_id: int, expected: bool = True):
        exists = RuleCondition.query.filter_by(rule_id=rule_id, symptom_id=symptom_id).first()
        if not exists:
            db.session.add(RuleCondition(rule_id=rule_id, symptom_id=symptom_id, expected_value=expected))
            db.session.commit()

    # HIGH = polyuria + polydipsia + weight_loss
    link_condition(rule_high.id, symptoms["polyuria"].id, True)
    link_condition(rule_high.id, symptoms["polydipsia"].id, True)
    link_condition(rule_high.id, symptoms["weight_loss"].id, True)

    # MODERATE = polyuria + polydipsia
    link_condition(rule_mod.id, symptoms["polyuria"].id, True)
    link_condition(rule_mod.id, symptoms["polydipsia"].id, True)

    # ---------- Advice templates ----------
    high_advice = Advice.query.filter_by(diagnosis_code="DIABETES_RISK", risk_level="HIGH").first()
    if not high_advice:
        high_advice = Advice(
            diagnosis_code="DIABETES_RISK",
            risk_level="HIGH",
            title="Urgent check-up recommended",
            content=(
                "Your answers match a high-risk diabetes symptom pattern. "
                "Please visit a doctor or clinic soon and request: FBS, RBS, HbA1c. "
                "If symptoms are severe (vomiting, confusion, dehydration), go to ER."
            ),
            severity="ALERT",
            is_active=True,
        )
        db.session.add(high_advice)
        db.session.commit()

    mod_advice = Advice.query.filter_by(diagnosis_code="DIABETES_RISK", risk_level="MODERATE").first()
    if not mod_advice:
        mod_advice = Advice(
            diagnosis_code="DIABETES_RISK",
            risk_level="MODERATE",
            title="Screening and lifestyle advice",
            content=(
                "Your answers match a moderate-risk pattern. "
                "Consider screening tests (FBS or HbA1c) and improve lifestyle: reduce sugary drinks, "
                "exercise regularly, and monitor symptoms."
            ),
            severity="INFO",
            is_active=True,
        )
        db.session.add(mod_advice)
        db.session.commit()

    print("✅ Demo KB seeded successfully.")
