import time

import agent.loop as loop_mod
from agent.loop import run_agent
from agent.state import AgentState

# 实验脚本里临时跳过退避等待，避免真等 1s、2s
loop_mod.time.sleep = lambda _: None


def run_case(name, max_steps, budget, deadline_seconds, proposal_fn, tools):
    state = AgentState(
        trace_id=name,
        max_steps=max_steps,
        budget_remaining=budget,
        run_deadline=time.time() + deadline_seconds,
    )
    audit = []
    result = run_agent(state, proposal_fn, tools, audit)
    timeouts = [e for e in audit if e["event"] == "tool_timeout"]
    allowed_retries = [e for e in timeouts if e["allowed"]]
    return {
        "name": name,
        "status": result["status"],
        "reason": result.get("reason", ""),
        "steps": state.step,
        "budget_left": state.budget_remaining,
        "timeout_count": len(timeouts),
        "retry_count": len(allowed_retries),
        "truncated": result["status"] == "stopped",
        "deadlocked": False,
    }


def endless_proposal():
    counter = {"n": 0}

    def propose(state):
        counter["n"] += 1
        return {"tool": "read_tool", "args": {"i": counter["n"]}}

    return propose


def always_timeout(**kwargs):
    raise loop_mod.ToolTimeout("simulated timeout")


def always_ok(**kwargs):
    return "ok"


print("## 无预算 vs 有预算")
read_tools = {"read_tool": {"kind": "read", "fn": always_ok, "timeout": 10}}
for label, max_steps, budget, deadline in [
    ("无预算", 1000, 10**9, 3600),
    ("有预算", 8, 4, 60),
]:
    r = run_case(label, max_steps, budget, deadline, endless_proposal(), read_tools)
    print(r)

print("\n## 读重试受总预算约束")
timeout_tools = {"read_tool": {"kind": "read", "fn": always_timeout, "timeout": 10}}
for label, budget in [("读重试_budget1", 1), ("读重试_budget10", 10)]:
    r = run_case(
        label, 8, budget, 60,
        lambda s: {"tool": "read_tool", "args": {"q": "x"}},
        timeout_tools,
    )
    print(r)

print("\n## 写操作超时不重试")
write_tools = {"write_tool": {"kind": "write", "fn": always_timeout, "timeout": 10}}
r = run_case(
    "写超时", 8, 10, 60,
    lambda s: {"tool": "write_tool", "args": {"id": 1}},
    write_tools,
)
print(r)