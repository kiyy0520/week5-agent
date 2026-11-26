# app/idempotency.py
import hashlib
import json

def canonical_params(params: dict) -> str:
    return json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def make_idempotency_key(tenant_id: str, task_id: str, tool_name: str, params: dict) -> str:
    canonical = canonical_params(params)
    params_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    raw = f"{tenant_id}|{task_id}|{tool_name}|{params_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

# app/idempotency.py 追加
def build_fingerprint(tenant_id: str, task_id: str, tool_name: str, params: dict) -> dict:
    return {
        "tenant_id": tenant_id,
        "task_id": task_id,
        "tool_name": tool_name,
        "params_hash": hashlib.sha256(
            canonical_params(params).encode("utf-8")
        ).hexdigest(),
    }

def check_idempotency(log: dict, key: str, fingerprint: dict) -> tuple[str, dict | None]:
    if not key:
        return "missing_key", None
    if key not in log:
        return "new", None
    record = log[key]
    if record["fingerprint"] != fingerprint:
        if record["fingerprint"]["tenant_id"] != fingerprint["tenant_id"]:
            return "cross_tenant", record
        return "conflict", record
    return "replay", record["result"]