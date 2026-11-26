# tools/executors/write_action.py
import uuid

TOOL_SPEC = {
    "name": "submit_write_action",
    "description": "执行一次副作用写操作。写操作，必须审批；幂等键由系统注入，禁止模型生成。",
    "side_effect": "write",
    "retryable": False,
    "retry_max": 0,
    "retry_backoff_ms": 0,
    "requires_approval": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "payload": {"type": "object"},
            "idempotency_key": {"type": "string"},
        },
        "required": ["action", "payload", "idempotency_key"],
    },
}

def submit_write_action(action: str, payload: dict, idempotency_key: str) -> dict:
    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    return {
        "action": action,
        "payload": payload,
        "idempotency_key": idempotency_key,
        "executed": True,
        "trace_id": trace_id,
    }

def register(registry):
    registry.register(TOOL_SPEC, submit_write_action)

SEND_EMAIL_SPEC = {
    "name": "send_email",
    "description": "发送邮件。写操作，必须审批；幂等键由系统注入。",
    "side_effect": "write",
    "retryable": False,
    "retry_max": 0,
    "retry_backoff_ms": 0,
    "requires_approval": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "idempotency_key": {"type": "string"},
        },
        "required": ["to", "subject", "body", "idempotency_key"],
    },
}

def send_email(to: str, subject: str, body: str, idempotency_key: str) -> dict:
    import uuid
    trace_id = f"trace-{uuid.uuid4().hex[:12]}"
    return {
        "to": to,
        "subject": subject,
        "body": body,
        "idempotency_key": idempotency_key,
        "status": "sent",
        "trace_id": trace_id,
    }