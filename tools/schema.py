import jsonschema
from jsonschema import ValidationError
from tools.errors import ToolError

def validate_arguments(tool_name: str, arguments: dict, schema: dict, trace_id: str) -> None:
    """
    校验模型输出的参数是否符合 Schema 规则。
    如果校验失败，抛出结构化的 ToolError。
    """
    try:
        # 核心操作：使用 jsonschema 库进行校验
        jsonschema.validate(instance=arguments, schema=schema)
    except ValidationError as e:
        # 如果校验失败，捕获异常，并转化为我们标准的结构化错误！
        raise ToolError(
            error_type="ValidationError",
            retryable=False,  # 参数错了，重试毫无意义
            message=f"参数校验失败: {e.message}",
            tool_name=tool_name,
            trace_id=trace_id,
            detail={"path": list(e.path), "invalid_value": e.instance}
        )