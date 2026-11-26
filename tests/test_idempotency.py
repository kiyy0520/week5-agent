# tests/test_idempotency.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
import tools.executors.write_action as wa

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_globals():
    from app import main
    main.PENDING.clear()
    main.IDEMPOTENCY_LOG.clear()
    yield

@pytest.fixture
def mock_executor(monkeypatch):
    """给写操作工具打桩，记录它到底被调用了几次。"""
    call_count = {"count": 0}
    def fake_executor(action, payload, idempotency_key):
        call_count["count"] += 1
        return {"action": action, "idempotency_key": idempotency_key, "mocked": True}
    
    # 将 main 里注册的执行器替换为带计数器的假执行器
    from app import main
    monkeypatch.setitem(main.WRITE_TOOLS["submit_write_action"], "executor", fake_executor)
    return call_count

def test_readonly_not_intercepted():
    """只读工具直接执行，不进审批"""
    payload = {
        "tenant_id": "t1", "user_id": "u1", "task_id": "task1",
        "tool_name": "get_weather", "params": {"city": "Beijing"}
    }
    res = client.post("/run", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "executed"

def test_write_intercepted_and_not_executed(mock_executor):
    """未审批写操作不执行，拦截率 100%"""
    payload = {
        "tenant_id": "t1", "user_id": "u1", "task_id": "task1",
        "tool_name": "submit_write_action", "params": {"action": "pay", "payload": {"amount": 100}}
    }
    res = client.post("/run", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "pending_approval"
    assert mock_executor["count"] == 0  # 关键：一次都没执行

def test_approve_resume_and_no_duplicate_side_effect(mock_executor):
    """审批后 Resume 执行一次；重复调用（同键）不再执行"""
    payload = {
        "tenant_id": "t1", "user_id": "u1", "task_id": "task1",
        "tool_name": "submit_write_action", "params": {"action": "pay", "payload": {"amount": 100}}
    }
    # 1. 拦截
    res = client.post("/run", json=payload)
    appr_id = res.json()["approval_id"]
    
    # 2. 审批通过，Resume 执行
    res = client.post("/approve", json={"approval_id": appr_id, "decision": "approve"})
    assert res.status_code == 200
    assert res.json()["status"] == "executed"
    assert mock_executor["count"] == 1  # 执行了 1 次

    # 3. 模拟同一个业务请求再次进来（参数完全一致，生成同一个键）
    res2 = client.post("/run", json=payload)
    appr_id2 = res2.json()["approval_id"]
    
    # 4. 再次审批
    res2 = client.post("/approve", json={"approval_id": appr_id2, "decision": "approve"})
    assert res2.status_code == 200
    assert res2.json()["status"] == "replayed"  # 识别为重放
    assert mock_executor["count"] == 1  # 关键：副作用次数 = 0（除首次外）

def test_conflict_rejected(mock_executor):
    """同键不同参数：被拒绝"""
    # 先执行一次建立记录
    payload1 = {
        "tenant_id": "t1", "user_id": "u1", "task_id": "task1",
        "tool_name": "submit_write_action", "params": {"action": "pay", "payload": {"amount": 100}}
    }
    res = client.post("/run", json=payload1)
    appr_id = res.json()["approval_id"]
    client.post("/approve", json={"approval_id": appr_id, "decision": "approve"})
    
    # 手动伪造一个相同 key 但不同指纹的记录进入幂等库（模拟键碰撞）
    from app import main
    from app.idempotency import make_idempotency_key
    key = make_idempotency_key("t1", "task1", "submit_write_action", payload1["params"])
    
    # 强行修改已保存的指纹，使其与请求不符
    main.IDEMPOTENCY_LOG[key]["fingerprint"]["params_hash"] = "tampered_hash"
    
    # 再次请求并审批
    res2 = client.post("/run", json=payload1)
    appr_id2 = res2.json()["approval_id"]
    res2 = client.post("/approve", json={"approval_id": appr_id2, "decision": "approve"})
    
    assert res2.status_code == 409  # 应该拒绝
    assert mock_executor["count"] == 1  # 没有执行第二次

def test_cross_tenant_rejected(monkeypatch):
    """跨租户复用幂等键：拒绝执行并返回 403"""
    from app import main
    from app.schemas import PendingAction

    # 1. t1 租户正常执行一次，建立幂等记录
    payload = {
        "tenant_id": "t1", "user_id": "u1", "task_id": "task1",
        "tool_name": "send_email", "params": {"to": "test@test.com", "subject": "Hi", "body": "Hello"}
    }
    res = client.post("/run", json=payload)
    appr_id = res.json()["approval_id"]
    client.post("/approve", json={"approval_id": appr_id, "decision": "approve"})

    # 从 PENDING 中拿到刚才的执行记录
    record_t1 = main.PENDING[appr_id]

    # 2. 伪造一个 t2 租户的 pending 记录，但强行复用 t1 的 idempotency_key
    # 为什么要直接造 PendingAction？因为正常 /run 会让系统重新算键，算出来的是 t2 的键。
    # 我们要模拟的是：底层由于某种 bug 或恶意伪造，把 t1 的键交给了 t2 的请求。
    fake_record = PendingAction(
        approval_id="fake_t2",
        tenant_id="t2",  # 跨租户
        user_id="u2",
        task_id="task1",
        tool_name="send_email",
        params={"to": "test@test.com", "subject": "Hi", "body": "Hello"},
        idempotency_key=record_t1.idempotency_key,  # 强行复用 t1 的键
        status="pending"
    )
    main.PENDING["fake_t2"] = fake_record

    # 3. 审批这个伪造记录，期望触发 403
    res = client.post("/approve", json={"approval_id": "fake_t2", "decision": "approve"})
    assert res.status_code == 403
    assert "跨租户" in res.json()["detail"]

def test_missing_key_rejected():
    """幂等键丢失：拒绝执行并返回 400"""
    from app import main

    # 1. 正常 /run 生成一条 pending 记录
    payload = {
        "tenant_id": "t1", "user_id": "u1", "task_id": "task_missing",
        "tool_name": "send_email", "params": {"to": "test@test.com", "subject": "Hi", "body": "Hello"}
    }
    res = client.post("/run", json=payload)
    appr_id = res.json()["approval_id"]

    # 2. 篡改记录：模拟系统异常导致键丢失
    main.PENDING[appr_id].idempotency_key = ""

    # 3. 审批，期望触发 400
    res = client.post("/approve", json={"approval_id": appr_id, "decision": "approve"})
    assert res.status_code == 400
    assert "缺少幂等键" in res.json()["detail"]