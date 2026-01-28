from app.extensions import db
from app.models import Symptom, Rule, RuleCondition, Advice


PRIORITY_SCORE = {
    1: 100,  # Critical
    2: 80,   # High
    3: 60,   # Moderate
    4: 40,   # Low
    5: 20,   # Informational
}


def seed_demo_kb():
    print("🌱 Seeding demo Knowledge Base (symptoms, rules, advice)...")

    # ---------- Symptoms (Questions) ----------
    symptom_data = [
        {
            "code": "polyuria",
            "name": "Frequent urination",
            "question_text": "Do you urinate more often than usual?",
            "priority_order": 1,
            "category": "classic",
        },
        {
            "code": "polydipsia",
            "name": "Excessive thirst",
            "question_text": "Do you feel unusually thirsty most days?",
            "priority_order": 2,
            "category": "classic",
        },
        {
            "code": "polyphagia",
            "name": "Increased hunger",
            "question_text": "Have you felt unusually hungry or eaten more than usual?",
            "priority_order": 3,
            "category": "classic",
        },
        {
            "code": "weight_loss",
            "name": "Unexplained weight loss",
            "question_text": "Have you lost weight without trying?",
            "priority_order": 4,
            "category": "classic",
        },
        {
            "code": "fatigue",
            "name": "Fatigue or weakness",
            "question_text": "Do you often feel unusually tired or weak?",
            "priority_order": 5,
            "category": "classic",
        },
        {
            "code": "blurred_vision",
            "name": "Blurred vision",
            "question_text": "Do you experience blurred vision?",
            "priority_order": 6,
            "category": "classic",
        },
        {
            "code": "slow_healing",
            "name": "Slow-healing wounds",
            "question_text": "Do cuts or wounds heal more slowly than usual?",
            "priority_order": 7,
            "category": "classic",
        },
        {
            "code": "tingling",
            "name": "Tingling or numbness",
            "question_text": "Do you have tingling or numbness in your hands or feet?",
            "priority_order": 8,
            "category": "classic",
        },
        {
            "code": "recurrent_infections",
            "name": "Frequent infections",
            "question_text": "Do you get frequent skin, gum, or urinary infections?",
            "priority_order": 9,
            "category": "classic",
        },
        {
            "code": "darkened_skin",
            "name": "Darkened skin patches",
            "question_text": "Do you have darkened skin patches on the neck or armpits?",
            "priority_order": 10,
            "category": "risk_factor",
        },
        {
            "code": "family_history",
            "name": "Family history of diabetes",
            "question_text": "Do you have a close family member with diabetes?",
            "priority_order": 11,
            "category": "risk_factor",
        },
        {
            "code": "high_bp",
            "name": "High blood pressure",
            "question_text": "Have you been told you have high blood pressure?",
            "priority_order": 12,
            "category": "risk_factor",
        },
        {
            "code": "overweight",
            "name": "Overweight",
            "question_text": "Are you overweight for your height?",
            "priority_order": 13,
            "category": "risk_factor",
        },
        {
            "code": "inactive",
            "name": "Physical inactivity",
            "question_text": "Are you physically inactive (less than 150 minutes of exercise per week)?",
            "priority_order": 14,
            "category": "risk_factor",
        },
        {
            "code": "gestational_diabetes",
            "name": "Gestational diabetes history",
            "question_text": "Have you ever had gestational diabetes during pregnancy?",
            "priority_order": 15,
            "category": "risk_factor",
        },
        {
            "code": "prediabetes_history",
            "name": "Prediabetes history",
            "question_text": "Have you been told you have prediabetes or high blood sugar before?",
            "priority_order": 16,
            "category": "risk_factor",
        },
    ]

    derived_symptom_data = [
        {
            "code": "classic_diabetes_symptoms",
            "name": "Classic diabetes symptom pattern",
            "question_text": "Derived: classic diabetes symptom pattern",
            "priority_order": 901,
        },
        {
            "code": "severe_symptoms",
            "name": "Severe symptom pattern",
            "question_text": "Derived: severe symptom pattern",
            "priority_order": 902,
        },
        {
            "code": "metabolic_risk",
            "name": "Metabolic risk cluster",
            "question_text": "Derived: metabolic risk cluster",
            "priority_order": 903,
        },
        {
            "code": "lifestyle_risk",
            "name": "Lifestyle risk cluster",
            "question_text": "Derived: lifestyle risk cluster",
            "priority_order": 904,
        },
        {
            "code": "multiple_symptoms",
            "name": "Multiple symptoms",
            "question_text": "Derived: multiple symptoms",
            "priority_order": 905,
        },
        {
            "code": "age_over_45",
            "name": "Age over 45",
            "question_text": "Derived: age is 45 or above",
            "priority_order": 906,
        },
        {
            "code": "age_over_35",
            "name": "Age over 35",
            "question_text": "Derived: age is 35 or above",
            "priority_order": 907,
        },
        {
            "code": "has_fatigue",
            "name": "Has fatigue",
            "question_text": "Derived: fatigue reported",
            "priority_order": 908,
        },
        {
            "code": "has_thirst",
            "name": "Has thirst",
            "question_text": "Derived: thirst reported",
            "priority_order": 909,
        },
        {
            "code": "obese",
            "name": "Obese",
            "question_text": "Derived: obesity indicator",
            "priority_order": 910,
        },
    ]

    symptoms = {}
    for item in symptom_data:
        code = item["code"]
        s = Symptom.query.filter_by(code=code).first()
        if not s:
            s = Symptom(
                code=code,
                name=item["name"],
                question_text=item["question_text"],
                input_type="BOOLEAN",
                priority_order=item["priority_order"],
                category=item["category"],
                is_active=True,
                is_derived=False,
            )
            db.session.add(s)
            db.session.commit()
        symptoms[code] = s

    for item in derived_symptom_data:
        code = item["code"]
        s = Symptom.query.filter_by(code=code).first()
        if not s:
            s = Symptom(
                code=code,
                name=item["name"],
                question_text=item["question_text"],
                input_type="BOOLEAN",
                priority_order=item["priority_order"],
                category="derived",
                is_active=True,
                is_derived=True,
            )
            db.session.add(s)
            db.session.commit()
        symptoms[code] = s

    # ---------- Rules ----------
    rules_data = [
        {
            "rule_code": "R1A",
            "title": "Strong diabetes indication (obesity)",
            "name": "Very High Risk: Classic + Obese",
            "diagnosis": "Type 2 Diabetes Risk",
            "diagnosis_code": "HIGH_RISK_TYPE_2_DIABETES",
            "risk_level": "VERY_HIGH",
            "priority": PRIORITY_SCORE[1],
            "confidence": 90,
            "explanation_text": "Classic diabetes symptoms with obesity indicate a very high Type 2 diabetes risk.",
            "conditions": ["classic_diabetes_symptoms", "obese"],
        },
        {
            "rule_code": "R1B",
            "title": "Strong diabetes indication (age)",
            "name": "Very High Risk: Classic + Age",
            "diagnosis": "Type 2 Diabetes Risk",
            "diagnosis_code": "HIGH_RISK_TYPE_2_DIABETES",
            "risk_level": "VERY_HIGH",
            "priority": PRIORITY_SCORE[1],
            "confidence": 90,
            "explanation_text": "Classic diabetes symptoms with age over 45 indicate a very high Type 2 diabetes risk.",
            "conditions": ["classic_diabetes_symptoms", "age_over_45"],
        },
        {
            "rule_code": "R2",
            "title": "Severe symptom rule",
            "name": "Very High Risk: Severe Symptoms",
            "diagnosis": "Type 2 Diabetes Risk",
            "diagnosis_code": "HIGH_RISK_TYPE_2_DIABETES",
            "risk_level": "VERY_HIGH",
            "priority": PRIORITY_SCORE[1],
            "confidence": 95,
            "explanation_text": "Severe symptom patterns strongly indicate a very high Type 2 diabetes risk.",
            "conditions": ["severe_symptoms"],
        },
        {
            "rule_code": "R3",
            "title": "Metabolic syndrome risk",
            "name": "High Risk: Metabolic + Age",
            "diagnosis": "Type 2 Diabetes Risk",
            "diagnosis_code": "HIGH_RISK_TYPE_2_DIABETES",
            "risk_level": "HIGH",
            "priority": PRIORITY_SCORE[2],
            "confidence": 85,
            "explanation_text": "Metabolic risk combined with age over 45 increases Type 2 diabetes risk.",
            "conditions": ["metabolic_risk", "age_over_45"],
        },
        {
            "rule_code": "R4",
            "title": "Family history + lifestyle",
            "name": "High Risk: Family + Inactive",
            "diagnosis": "Type 2 Diabetes Risk",
            "diagnosis_code": "HIGH_RISK_TYPE_2_DIABETES",
            "risk_level": "HIGH",
            "priority": PRIORITY_SCORE[2],
            "confidence": 80,
            "explanation_text": "Family history and inactivity raise Type 2 diabetes risk.",
            "conditions": ["family_history", "inactive"],
        },
        {
            "rule_code": "R5",
            "title": "Age + weight risk",
            "name": "Moderate Risk: Age + Weight",
            "diagnosis": "Prediabetes",
            "diagnosis_code": "MODERATE_RISK",
            "risk_level": "MODERATE",
            "priority": PRIORITY_SCORE[3],
            "confidence": 65,
            "explanation_text": "Being over 35 with excess weight increases the chance of prediabetes.",
            "conditions": ["age_over_35", "overweight"],
        },
        {
            "rule_code": "R6",
            "title": "Lifestyle risk alone",
            "name": "Moderate Risk: Lifestyle",
            "diagnosis": "Prediabetes",
            "diagnosis_code": "MODERATE_RISK",
            "risk_level": "MODERATE",
            "priority": PRIORITY_SCORE[3],
            "confidence": 60,
            "explanation_text": "Lifestyle risk factors alone indicate a moderate risk of prediabetes.",
            "conditions": ["lifestyle_risk"],
        },
        {
            "rule_code": "R7",
            "title": "Healthy profile",
            "name": "Low Risk: Healthy Profile",
            "diagnosis": "Normal",
            "diagnosis_code": "LOW_RISK",
            "risk_level": "LOW",
            "priority": PRIORITY_SCORE[4],
            "confidence": 90,
            "explanation_text": "You are under 35, not overweight, and do not show multiple symptoms.",
            "conditions": [
                {"code": "age_over_35", "expected": False},
                {"code": "overweight", "expected": False},
                {"code": "multiple_symptoms", "expected": False},
            ],
        },
        {
            "rule_code": "R8A",
            "title": "Single symptom monitoring (fatigue)",
            "name": "Monitor: Fatigue",
            "diagnosis": "Monitor",
            "diagnosis_code": "MONITOR",
            "risk_level": "LOW",
            "priority": PRIORITY_SCORE[5],
            "confidence": 50,
            "explanation_text": "Single mild symptom noted; monitor and recheck if symptoms change.",
            "conditions": [
                {"code": "multiple_symptoms", "expected": False},
                {"code": "has_fatigue", "expected": True},
            ],
        },
        {
            "rule_code": "R8B",
            "title": "Single symptom monitoring (thirst)",
            "name": "Monitor: Thirst",
            "diagnosis": "Monitor",
            "diagnosis_code": "MONITOR",
            "risk_level": "LOW",
            "priority": PRIORITY_SCORE[5],
            "confidence": 50,
            "explanation_text": "Single mild symptom noted; monitor and recheck if symptoms change.",
            "conditions": [
                {"code": "multiple_symptoms", "expected": False},
                {"code": "has_thirst", "expected": True},
            ],
        },
    ]

    def get_or_create_rule(rule_def):
        rule = Rule.query.filter_by(rule_code=rule_def["rule_code"]).first()
        created = False
        if not rule:
            rule = Rule(
                rule_code=rule_def["rule_code"],
                title=rule_def["title"],
                name=rule_def["name"],
                diagnosis=rule_def["diagnosis"],
                diagnosis_code=rule_def["diagnosis_code"],
                risk_level=rule_def["risk_level"],
                priority=rule_def["priority"],
                confidence=rule_def["confidence"],
                is_active=True,
                explanation_text=rule_def.get("explanation_text"),
            )
            db.session.add(rule)
            db.session.commit()
            created = True
        return rule, created

    def link_condition(rule_id: int, symptom_id: int, expected: bool = True):
        exists = RuleCondition.query.filter_by(rule_id=rule_id, symptom_id=symptom_id).first()
        if not exists:
            db.session.add(RuleCondition(rule_id=rule_id, symptom_id=symptom_id, expected_value=expected))
            db.session.commit()

    for rule_def in rules_data:
        rule, created = get_or_create_rule(rule_def)
        if created:
            for cond in rule_def["conditions"]:
                if isinstance(cond, dict):
                    code = cond["code"]
                    expected = bool(cond.get("expected", True))
                else:
                    code = cond
                    expected = True
                link_condition(rule.id, symptoms[code].id, expected)

    # ---------- Advice templates ----------
    def ensure_advice(
        diagnosis_code: str,
        risk_level: str,
        title: str,
        content: str,
        severity: str,
        recommendations: dict,
    ):
        existing = Advice.query.filter_by(diagnosis_code=diagnosis_code, risk_level=risk_level).first()
        if existing:
            if not existing.recommendations_json:
                existing.recommendations_json = recommendations
                db.session.commit()
            return
        advice = Advice(
            diagnosis_code=diagnosis_code,
            risk_level=risk_level,
            title=title,
            content=content,
            severity=severity,
            is_active=True,
            recommendations_json=recommendations,
        )
        db.session.add(advice)
        db.session.commit()

    ensure_advice(
        "HIGH_RISK_TYPE_2_DIABETES",
        "VERY_HIGH",
        "Urgent medical evaluation",
        "Your answers suggest a very high risk of Type 2 diabetes. Please seek medical evaluation soon and request blood glucose testing (FBS, RBS, HbA1c).",
        "ALERT",
        {
            "screening_tests": [
                "Fasting Blood Sugar (FBS)",
                "HbA1c test",
                "Random Blood Glucose (RBG) if symptoms worsen",
            ],
            "lifestyle": [
                "Reduce sugary drinks and refined carbs",
                "Increase vegetables, lean protein, and whole grains",
                "Aim for 30 minutes of activity at least 5 days a week",
                "Work toward a healthy body weight",
            ],
            "monitoring": [
                "Watch for worsening thirst, urination, fatigue, or weight loss",
                "Repeat this assessment if symptoms change",
                "Seek care promptly if symptoms are severe",
            ],
            "good_news": [
                "Early action can lower long‑term risk.",
                "Many people regain control with consistent habits.",
            ],
            "notice": [
                "This result is informational only and not a medical diagnosis.",
                "Always consult a qualified healthcare professional.",
            ],
        },
    )
    ensure_advice(
        "HIGH_RISK_TYPE_2_DIABETES",
        "HIGH",
        "High-risk screening recommended",
        "Your answers indicate a high risk of Type 2 diabetes. Schedule screening tests and discuss risk reduction with a clinician.",
        "WARNING",
        {
            "screening_tests": [
                "Fasting Blood Sugar (FBS)",
                "HbA1c test",
            ],
            "lifestyle": [
                "Choose balanced meals with fewer refined carbs",
                "Stay active most days of the week",
                "Maintain or reduce weight if overweight",
            ],
            "monitoring": [
                "Track any new symptoms",
                "Repeat this assessment in 3–6 months",
            ],
            "good_news": [
                "Risk can often drop with consistent lifestyle changes.",
                "Awareness helps you take control early.",
            ],
            "notice": [
                "Informational only — not a diagnosis.",
                "Consult a healthcare professional for testing.",
            ],
        },
    )
    ensure_advice(
        "MODERATE_RISK",
        "MODERATE",
        "Moderate-risk screening",
        "Consider screening tests (FBS or HbA1c) and improve lifestyle habits: healthy diet, regular activity, and weight management.",
        "INFO",
        {
            "screening_tests": [
                "Fasting Blood Sugar (FBS)",
                "HbA1c test",
            ],
            "lifestyle": [
                "Reduce added sugar and processed foods",
                "Add brisk walking or light exercise",
                "Prioritize sleep and stress management",
            ],
            "monitoring": [
                "Repeat this assessment if symptoms appear",
                "Monitor for fatigue, thirst, or frequent urination",
            ],
            "good_news": [
                "Most people can return to low risk with healthy habits.",
            ],
            "notice": [
                "This result is informational only.",
            ],
        },
    )
    ensure_advice(
        "LOW_RISK",
        "LOW",
        "Low risk right now",
        "Your answers do not match higher-risk patterns. Maintain healthy habits and repeat screening if symptoms appear.",
        "INFO",
        {
            "screening_tests": [
                "Routine check-ups as advised by your clinician",
            ],
            "lifestyle": [
                "Keep a balanced diet",
                "Stay active weekly",
                "Maintain a healthy weight",
            ],
            "monitoring": [
                "Repeat this assessment if symptoms develop",
            ],
            "good_news": [
                "Your current pattern suggests low risk.",
                "Keep up the healthy habits.",
            ],
            "notice": [
                "This result is informational only.",
            ],
        },
    )
    ensure_advice(
        "MONITOR",
        "LOW",
        "Monitor symptoms",
        "You reported a single mild symptom. Monitor for changes and seek advice if additional symptoms appear.",
        "INFO",
        {
            "screening_tests": [
                "Discuss testing if symptoms persist",
            ],
            "lifestyle": [
                "Stay hydrated and prioritize sleep",
                "Maintain a balanced diet",
            ],
            "monitoring": [
                "Track symptoms for the next 2–4 weeks",
                "Repeat this assessment if symptoms increase",
            ],
            "good_news": [
                "Early awareness helps prevent escalation.",
            ],
            "notice": [
                "Informational only — consult a professional if concerned.",
            ],
        },
    )

    print("✅ Demo KB seeded successfully.")
