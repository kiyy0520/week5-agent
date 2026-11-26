import pytest
from tools.registry import ToolRegistry, ToolMeta
from tools.schema import validate_arguments
from tools.errors import ToolError
from tools.executors.math_tool import calculate_bmi

# 准备通用的测试数据（Fixture）
@pytest.fixture
def registry():
    reg = ToolRegistry()
    weather_schema = {"type": "object", "properties": {"city": {"type": "string"}, "unit": {"type": "string", "enum": ["C", "F"]}}, "required": ["city", "unit"]}
    delete_schema = {"type": "object", "properties": {"user_id": {"type": "integer", "minimum": 1}}, "required": ["user_id"]}
    search_schema = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

    reg.register(ToolMeta("get_weather", "v1", [], False, 5.0, {}, weather_schema, lambda: "sunny"))
    reg.register(ToolMeta("delete_user", "v1", ["admin"], True, 10.0, {}, delete_schema, lambda: "deleted"))
    reg.register(ToolMeta("search_knowledge", "v1", [], False, 15.0, {}, search_schema, lambda: "result"))
    return reg

def test_tool_conflict_detection(registry):
    """测试工具名冲突检测"""
    schema = {"type": "object"}
    with pytest.raises(ToolError) as exc_info:
        registry.register(ToolMeta("get_weather", "v1", [], False, 5.0, {}, schema, lambda: "sunny"))
    
    assert exc_info.value.error_type == "ToolConflictError"
    assert exc_info.value.retryable is False
    assert "已存在" in exc_info.value.message

def test_runtime_tool_projection(registry):
    """测试运行时工具投影（权限过滤）"""
    guest_tools = registry.get_allowed_tools(["guest"])
    admin_tools = registry.get_allowed_tools(["admin"])
    
    assert len(guest_tools) == 2
    assert len(admin_tools) == 3
    
    guest_tool_names = [t["name"] for t in guest_tools]
    assert "delete_user" not in guest_tool_names

def test_schema_enum_validation():
    """测试 Schema 枚举越界拦截"""
    schema = {"type": "object", "properties": {"unit": {"type": "string", "enum": ["C", "F"]}}, "required": ["unit"]}
    with pytest.raises(ToolError) as exc_info:
        validate_arguments("get_weather", {"unit": "K"}, schema, "trace_123")
    
    assert exc_info.value.error_type == "ValidationError"
    assert exc_info.value.retryable is False
    assert exc_info.value.trace_id == "trace_123"

def test_schema_missing_param_validation():
    """测试 Schema 必填缺失拦截"""
    schema = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    with pytest.raises(ToolError) as exc_info:
        validate_arguments("search_knowledge", {}, schema, "trace_456")
    
    assert exc_info.value.error_type == "ValidationError"
    assert "required property" in exc_info.value.message

def test_bmi_tool():
    """【独立挑战】测试 BMI 工具的注册与范围越界拦截"""
    registry = ToolRegistry()
    
    bmi_schema = {
        "type": "object",
        "properties": {
            "height": {"type": "number", "minimum": 0.1},
            "weight": {"type": "number", "minimum": 0.1}
        },
        "required": ["height", "weight"]
    }
    
    registry.register(ToolMeta(
        name="calculate_bmi",
        version="v1",
        permissions=[],
        has_side_effects=False,
        timeout=5.0,
        retry_policy={},
        schema=bmi_schema,
        executor=calculate_bmi
    ))
    
    # 测试范围越界拦截 (height = -1)
    with pytest.raises(ToolError) as exc_info:
        validate_arguments("calculate_bmi", {"height": -1, "weight": 70}, bmi_schema, "trace_bmi")
    
    assert exc_info.value.error_type == "ValidationError"
    assert exc_info.value.retryable is False
    assert exc_info.value.tool_name == "calculate_bmi"

def test_user_info_tool_type_validation():
    """【变式练习】测试类型错误拦截与正常调用"""
    user_schema = {
        "type": "object",
        "properties": {"age": {"type": "integer"}},
        "required": ["age"]
    }
    
    # 1. 可选挑战：正常情况不报错（传整数）
    try:
        validate_arguments("get_user_info", {"age": 25}, user_schema, "trace_ok")
    except ToolError:
        pytest.fail("正常情况不应该抛出异常！")
        
    # 2. 异常情况拦截（传字符串 "twenty"）
    with pytest.raises(ToolError) as exc_info:
        validate_arguments("get_user_info", {"age": "twenty"}, user_schema, "trace_err")
        
    assert exc_info.value.error_type == "ValidationError"
    assert exc_info.value.retryable is False