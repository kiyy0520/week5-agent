# Day 4 实验报告：副作用工具、幂等键与人工审批

## 1. 实验环境
- Python 版本：3.14.2
- 测试框架：pytest, FastAPI TestClient
- 运行目录：F:\Projects\week5-agent

## 2. 量化验证结果
- [x] **幂等重复调用副作用次数 = 0（除首次外）**：通过 mock 计数器验证，重放时底层执行次数保持为 1。
- [x] **审批拦截率 100%**：未审批写操作不执行，`/run` 只返回 pending，测试通过。
- [x] **审批后 Resume 成功继续执行**：`/approve` 触发后状态从 pending 变 executed。
- [x] **幂等键冲突/跨租户复用测试通过**：同键不同指纹返回 409，跨租户返回 403，拒绝执行。

## 3. 独立挑战：新增“发送邮件”写操作工具
- 在 `write_action.py` 中新增 `send_email` 声明，标记 `side_effect=write`、`retryable=False`、`requires_approval=True`，并在 Schema 中强制要求 `idempotency_key`。
- 在 `main.py` 的 `WRITE_TOOLS` 中注册该工具。
- 编写测试 `test_send_email_approval_and_idempotency`，用 monkeypatch 打桩，验证了：未审批不执行、审批后执行 1 次、重放时不再增加执行次数。

## 4. 变式练习：边界条件防范
- **跨租户防范**：伪造一个 t2 租户的 pending 记录，强行复用 t1 的 idempotency_key，验证 `/approve` 会拦截并返回 403，防止数据串租户。
- **幂等键丢失**：篡改 pending 记录，将 idempotency_key 置空，验证 `/approve` 会返回 400 拒绝执行，证明缺失键时保护机制生效。

## 5. 测试执行记录
```text
pytest tests/test_idempotency.py -v
tests/test_idempotency.py::test_readonly_not_intercepted PASSED
tests/test_idempotency.py::test_write_intercepted_and_not_executed PASSED
tests/test_idempotency.py::test_approve_resume_and_no_duplicate_side_effect PASSED
tests/test_idempotency.py::test_conflict_rejected PASSED
tests/test_idempotency.py::test_cross_tenant_rejected PASSED
tests/test_idempotency.py::test_missing_key_rejected PASSED
======================= 6 passed in 0.48s =======================