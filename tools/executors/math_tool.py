def calculate_bmi(height: float, weight: float) -> str:
    """真实的计算 BMI 的函数，简单返回用于测试"""
    return f"BMI tool called with {height} and {weight}"

bmi_schema = {
    "type": "object",
    "properties": {
        "height": {"type": "number", "minimum": 0.1},
        "weight": {"type": "number", "minimum": 0.1}
    },
    "required": ["height", "weight"]
}