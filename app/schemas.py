# app/schemas.py
from dataclasses import dataclass, field
from typing import Any, Literal

@dataclass
class RunRequest:
    tenant_id: str
    user_id: str
    task_id: str
    tool_name: str
    params: dict[str, Any]

@dataclass
class ApprovalRequest:
    approval_id: str
    decision: Literal["approve", "reject"]

@dataclass
class PendingAction:
    approval_id: str
    tenant_id: str
    user_id: str
    task_id: str
    tool_name: str
    params: dict[str, Any]
    idempotency_key: str
    status: Literal["pending", "approved", "rejected", "executed"] = "pending"
    result: dict[str, Any] | None = None