import time
import pytest

import agent.loop as loop_mod
from agent.loop import run_agent
from agent.state import AgentState


def make_state(max_steps=8, budget=4, deadline_seconds=60):
    return AgentState(
        trace_id="test-trace",
        max_steps=max_steps,
        budget_remaining=budget,
        run_deadline=time.time() + deadline_seconds,
    )


def test_read_timeout_triggers_limited_retry(monkeypatch):
    monkeypatch.setattr(loop_mod.time, "sleep", lambda _: None)
    calls = {"n": 0}

    def flaky_read(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise loop_mod.ToolTimeout("simulated timeout")
        return "ok"

    def propose(state):
        if state.step >= 1:
            return None
        return {"tool": "read_tool", "args": {"q": "x"}}

    tools = {"read_tool": {"kind": "read", "fn": flaky_read, "timeout": 10}}
    state = make_state(budget=4)
    audit = []

    result = run_agent(state, propose, tools, audit)

    assert result["status"] == "finished"
    assert calls["n"] == 3
    assert state.budget_remaining == 2
    assert sum(1 for e in audit if e["event"] == "tool_timeout" and e["allowed"]) == 2


def test_max_steps_truncates(monkeypatch):
    monkeypatch.setattr(loop_mod.time, "sleep", lambda _: None)
    counter = {"i": 0}

    def propose(state):
        counter["i"] += 1
        return {"tool": "read_tool", "args": {"i": counter["i"]}}

    tools = {"read_tool": {"kind": "read", "fn": lambda **kw: "ok", "timeout": 1}}
    state = make_state(max_steps=2, budget=10)
    audit = []

    result = run_agent(state, propose, tools, audit)

    assert result["status"] == "stopped"
    assert "最大步数" in result["reason"]
    assert state.step == 2


def test_repeated_tool_and_args_detected(monkeypatch):
    monkeypatch.setattr(loop_mod.time, "sleep", lambda _: None)

    tools = {"read_tool": {"kind": "read", "fn": lambda **kw: "ok", "timeout": 1}}
    state = make_state(max_steps=8, budget=10)
    audit = []
    proposal = {"tool": "read_tool", "args": {"q": "same"}}

    result = run_agent(state, lambda s: proposal, tools, audit)

    assert result["status"] == "stopped"
    assert "重复工具+参数" in result["reason"]
    assert any(e["event"] == "loop_detected" for e in audit)


def test_write_timeout_does_not_retry(monkeypatch):
    monkeypatch.setattr(loop_mod.time, "sleep", lambda _: None)

    def slow_write(**kwargs):
        raise loop_mod.ToolTimeout("simulated write timeout")

    tools = {"write_tool": {"kind": "write", "fn": slow_write, "timeout": 10}}
    state = make_state(max_steps=8, budget=10)
    initial_budget = state.budget_remaining
    audit = []

    result = run_agent(
        state,
        lambda s: {"tool": "write_tool", "args": {"id": 1}},
        tools,
        audit,
    )

    assert result["status"] == "stopped"
    assert "写操作超时禁止直接重试" in result["reason"]
    assert state.budget_remaining == initial_budget


def test_read_retry_exhausted_by_max(monkeypatch):
    """验证：READ_RETRY_MAX=1 时，只允许 1 次读重试，第 2 次被次数上限拒绝。"""
    from config import settings
    monkeypatch.setattr(settings, "READ_RETRY_MAX", 1)
    monkeypatch.setattr(loop_mod.time, "sleep", lambda _: None)

    def always_timeout(**kwargs):
        raise loop_mod.ToolTimeout("simulated timeout")

    tools = {"read_tool": {"kind": "read", "fn": always_timeout, "timeout": 10}}
    state = make_state(max_steps=8, budget=10)
    initial_budget = state.budget_remaining
    audit = []

    result = run_agent(
        state,
        lambda s: {"tool": "read_tool", "args": {"q": "x"}},
        tools,
        audit,
    )

    assert result["status"] == "stopped"
    assert "读操作重试次数已达上限" in result["reason"]
    allowed = [e for e in audit if e["event"] == "tool_timeout" and e["allowed"]]
    assert len(allowed) == 1
    assert state.budget_remaining == initial_budget - 1


def test_read_retry_blocked_when_budget_runs_out(monkeypatch):
    """验证：预算在执行中被消耗到 0 后，下一次超时被总预算拒绝重试。"""
    monkeypatch.setattr(loop_mod.time, "sleep", lambda _: None)

    def always_timeout(**kwargs):
        raise loop_mod.ToolTimeout("simulated timeout")

    tools = {"read_tool": {"kind": "read", "fn": always_timeout, "timeout": 10}}
    state = make_state(max_steps=8, budget=1)
    initial_budget = state.budget_remaining
    audit = []

    result = run_agent(
        state,
        lambda s: {"tool": "read_tool", "args": {"q": "x"}},
        tools,
        audit,
    )

    assert result["status"] == "stopped"
    assert "总预算不足" in result["reason"]
    assert state.budget_remaining == 0
    assert state.budget_remaining < initial_budget

def test_real_timeout_interrupts_slow_tool():
    """验证：真正卡住的工具会被超时打断，而不是等它执行完。"""
    def slow_write(**kwargs):
        time.sleep(0.5)
        return "done"

    tools = {"slow_write": {"kind": "write", "fn": slow_write, "timeout": 0.05}}
    state = make_state(max_steps=8, budget=10)
    initial_budget = state.budget_remaining
    audit = []

    start = time.time()
    result = run_agent(
        state,
        lambda s: {"tool": "slow_write", "args": {"id": 1}},
        tools,
        audit,
    )
    elapsed = time.time() - start

    assert result["status"] == "stopped"
    assert "写操作超时禁止直接重试" in result["reason"]
    assert elapsed < 0.3, f"应在 0.05s 左右返回，实际等了 {elapsed:.2f}s"
    assert state.budget_remaining == initial_budget