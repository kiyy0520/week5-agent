from dataclasses import dataclass, field
from typing import Dict, List, Callable, Any, Optional
from tools.errors import ToolError

@dataclass
class ToolMeta:
    """工具元数据：记录一个工具的所有关键属性"""
    name: str
    version: str
    permissions: List[str]      # 需要什么权限才能调用，如 ["admin"]
    has_side_effects: bool      # 是否有副作用（如写数据库）
    timeout: float              # 超时时间（秒）
    retry_policy: Dict[str, Any]# 重试策略，如 {"max_retries": 3}
    schema: dict                # JSON Schema 定义
    executor: Callable          # 真正的执行函数
    description: str = ""  # <--- 新增这行，一定要放最后

class ToolRegistry:
    def __init__(self):
        # 存储结构：_tools[工具名][版本] = ToolMeta
        self._tools: Dict[str, Dict[str, ToolMeta]] = {}

    def register(self, meta: ToolMeta) -> None:
        """注册工具，并检测同名同版本冲突"""
        if meta.name not in self._tools:
            self._tools[meta.name] = {}
            
        if meta.version in self._tools[meta.name]:
            # 冲突检测：抛出我们之前定义的 ToolError
            raise ToolError(
                error_type="ToolConflictError",
                retryable=False,
                message=f"工具 '{meta.name}' 版本 '{meta.version}' 已存在，不能重复注册！",
                tool_name=meta.name,
                trace_id="system_registration"
            )
            
        self._tools[meta.name][meta.version] = meta

    def get_allowed_tools(self, user_permissions: List[str]) -> List[dict]:
        """运行时投影：只返回当前身份允许使用的 Schema 列表"""
        allowed_schemas = []
        for name, versions in self._tools.items():
            # 为了演示，我们默认取最新版本（实际中需更严谨的版本控制）
            meta = list(versions.values())[-1]
            
            # 检查权限：如果工具不需要权限，或者用户拥有所需权限
            if not meta.permissions or any(p in user_permissions for p in meta.permissions):
                allowed_schemas.append({
                    "name": meta.name,
                    "description": f"Tool {meta.name} version {meta.version}",
                    "parameters": meta.schema
                })
        return allowed_schemas