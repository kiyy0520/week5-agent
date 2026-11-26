# app/main.py
from fastapi import FastAPI, HTTPException
from app.schemas import RunRequest, ApprovalRequest, PendingAction
from app.idempotency import make_idempotency_key, build_fingerprint, check_idempotency
from tools.executors.weather import get_weather
from tools.executors.write_action import submit_write_action, send_email

app = FastAPI()

PENDING: dict[str, PendingAction] = {}
# IDEMPOTENCY_LOG 结构: {key: {"fingerprint": dict, "result": dict}}
IDEMPOTENCY_LOG: dict[str, dict] = {}

READONLY_TOOLS = {
    "get_weather": {"executor": get_weather},
}
WRITE_TOOLS = {
    "submit_write_action": {"executor": submit_write_action, "requires_approval": True},
    "send_email": {"executor": send_email, "requires_approval": True},
}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/run")
def run(req: RunRequest):
    # 1. 只读：直接执行，不拦截、不要键
    if req.tool_name in READONLY_TOOLS:
        executor = READONLY_TOOLS[req.tool_name]["executor"]
        result = executor(**req.params)
        return {"status": "executed", "result": result}

    # 2. 写：系统生成键 -> 100% 拦截 -> 存 pending
    if req.tool_name in WRITE_TOOLS:
        key = make_idempotency_key(req.tenant_id, req.task_id, req.tool_name, req.params)
        approval_id = f"appr-{key[:12]}"
        record = PendingAction(
            approval_id=approval_id,
            tenant_id=req.tenant_id,
            user_id=req.user_id,
            task_id=req.task_id,
            tool_name=req.tool_name,
            params=req.params,
            idempotency_key=key,
            status="pending",
        )
        PENDING[approval_id] = record
        return {"status": "pending_approval", "approval_id": approval_id, "idempotency_key": key}

    raise HTTPException(404, "未知工具")

@app.post("/approve")
def approve(req: ApprovalRequest):
    record = PENDING.get(req.approval_id)
    if record is None:
        raise HTTPException(404, "审批记录不存在")

    if req.decision == "reject":
        record.status = "rejected"
        return {"status": "rejected"}

    # 状态机：只有 pending 能执行
    if record.status != "pending":
        raise HTTPException(409, f"状态不允许执行: {record.status}")

    # 构建指纹并调用 check_idempotency
    # 注意：必须使用 record 里的字段，不能用外部请求新传的
    fingerprint = build_fingerprint(
        record.tenant_id, record.task_id, record.tool_name, record.params
    )
    verdict, prev = check_idempotency(IDEMPOTENCY_LOG, record.idempotency_key, fingerprint)

    if verdict == "missing_key":
        raise HTTPException(400, "缺少幂等键，拒绝执行")
    if verdict == "cross_tenant":
        raise HTTPException(403, "跨租户复用幂等键，拒绝执行并告警")
    if verdict == "conflict":
        raise HTTPException(409, "幂等键冲突：同键不同指纹，拒绝执行并告警")
    if verdict == "replay":
        record.status = "executed"
        return {"status": "replayed", "result": prev}

    # verdict == "new" 才真正执行
    executor = WRITE_TOOLS[record.tool_name]["executor"]
    result = executor(**record.params, idempotency_key=record.idempotency_key)
    
    # 执行成功后，连同指纹一起存入幂等记录
    IDEMPOTENCY_LOG[record.idempotency_key] = {
        "fingerprint": fingerprint,
        "result": result,
    }
    record.status = "executed"
    record.result = result
    return {"status": "executed", "result": result}