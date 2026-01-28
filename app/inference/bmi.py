def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    h = height_cm / 100.0
    return round(weight_kg / (h * h), 2)

def bmi_to_overweight(bmi: float) -> bool:
    return bmi >= 25.0
