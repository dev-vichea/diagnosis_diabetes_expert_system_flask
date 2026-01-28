from typing import Dict

def build_facts(raw_facts: Dict[str, any]) -> Dict[str, any]:
    """
    Convert raw user input into medical facts.
    """
    facts = {}

    # Direct symptoms
    facts["frequent_urination"] = raw_facts.get("frequent_urination")
    facts["excessive_thirst"] = raw_facts.get("excessive_thirst")

    # BMI (derived fact)
    weight = raw_facts.get("weight")
    height_cm = raw_facts.get("height_cm")

    if weight and height_cm:
        height_m = height_cm / 100
        bmi = weight / (height_m * height_m)
        facts["bmi"] = round(bmi, 2)
        facts["overweight"] = bmi >= 25

    # Age group
    age = raw_facts.get("age")
    if age:
        facts["age_over_45"] = age >= 45

    return facts
