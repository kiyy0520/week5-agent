import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Callable

from agent.policy import can_continue, decide_retry, is_repeated_state, is_repeated_tool_call
from agent.state import AgentState


class ToolTimeout(Exception):
    pass


def execute_with_timeout(fn: Callable[[], Any], timeout_seconds: float) -> Any:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError:
        raise ToolTimeout(f"工具执行超过 {timeout_seconds}s")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def run_agent(
    state: AgentState,
    model_propose: Callable[[AgentState], dict[str, Any] | None],
    tools: dict[str, dict[str, Any]],
    audit: list[dict[str, Any]],
) -> dict[str, Any]:
    while True:
        check = can_continue(state)
        if not check.allowed:
            audit.append({"event": "stop", "reason": check.reason, "step": state.step})
            return {"status": "stopped", "reason": check.reason, "state": state}

        if is_repeated_state(state):
            audit.append({"event": "loop_detected", "type": "repeat_state", "step": state.step})
            return {"status": "stopped", "reason": "状态哈希重复，判定循环", "state": state}
        state.state_hashes.append(state.snapshot_hash())

        proposal = model_propose(state)
        if proposal is None:
            audit.append({"event": "finish", "step": state.step})
            return {"status": "finished", "state": state}

        tool_name = proposal["tool"]
        args = proposal.get("args", {})
        tool_kind = tools[tool_name]["kind"]

        if is_repeated_tool_call(state, tool_name, args):
            audit.append({"event": "loop_detected", "type": "repeat_tool_args", "step": state.step})
            return {"status": "stopped", "reason": "重复工具+参数，判定循环", "state": state}

        retry_count = 0
        while True:
            try:
                result = execute_with_timeout(
                    lambda: tools[tool_name]["fn"](**args),
                    tools[tool_name].get("timeout", 10),
                )
                state.record_tool_call(tool_name, args)
                audit.append({"event": "tool_ok", "tool": tool_name, "step": state.step})
                break
            except ToolTimeout:
                decision = decide_retry(tool_kind, retry_count, state.budget_remaining)
                audit.append({
                    "event": "tool_timeout",
                    "tool": tool_name,
                    "retry_count": retry_count,
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                    "step": state.step,
                })
                if not decision.allowed:
                    return {"status": "stopped", "reason": decision.reason, "state": state}
                state.budget_remaining -= 1
                retry_count += 1
                time.sleep(decision.retry_delay or 0)