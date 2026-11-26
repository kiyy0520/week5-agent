# tools/executors/weather.py
import uuid

TOOL_SPEC = {
    "name": "get_weather",
    "description": "查询指定城市天气。只读操作，不改变任何数据。",
    "side_effect": "read_only",
    "retryable": True,
    "requires_approval": False,
    "timeout_ms": 2000,
    "retry_max": 2,
    "retry_backoff_ms": 150,
}

def get_weather(city: str) -> dict:
    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    return {
        "city": city,
        "weather": "sunny",
        "temperature_c": 25,
        "trace_id": trace_id,
    }

def register(registry):
    registry.register(TOOL_SPEC, get_weather)