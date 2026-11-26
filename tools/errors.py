from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class ToolError(Exception):
    """结构化工具错误：给模型看，也给人看"""
    error_type: str           # 错误类型，如 "ValidationError", "TimeoutError"
    retryable: bool           # 是否可重试，给模型提供决策依据
    message: str              # 人类可读的错误描述
    tool_name: str            # 出错的工具名
    trace_id: str             # 本次调用的追踪ID
    detail: Optional[Dict[str, Any]] = None  # 详细的上下文信息

    def __str__(self):
        # 让打印出来的时候更直观
        return f"[{self.error_type}] Tool '{self.tool_name}' failed (retryable={self.retryable}): {self.message}"