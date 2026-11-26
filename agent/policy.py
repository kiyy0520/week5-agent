# agent/policy.py
from dataclasses import dataclass
from typing import Any, Literal
import json
import time

from config import settings


@dataclass
class PolicyResult:
    allowed: bool
    reason: str = ""
    retry_delay: float | None = None


def can_continue(state) -> PolicyResult:
    if state.step >= state.max_steps:
        return PolicyResult(False, "达到最大步数，截断")
    if time.time() >= state.run_deadline:
        return PolicyResult(False, "超过 Run Deadline，截断")
    if state.budget_remaining <= 0:
        return PolicyResult(False, "总预算耗尽，停止")
    return PolicyResult(True, "允许继续")


def is_repeated_tool_call(state, tool_name: str, args: dict[str, Any], lookback: int = 3) -> bool:
    args_summary = json.dumps(args, sort_keys=True, ensure_ascii=False)[:200]
    recent = state.tool_calls[-lookback:]
    return any(
        c["tool"] == tool_name and c["args"] == args_summary
        for c in recent
    )


def is_repeated_state(state, extra: str = "", lookback: int = 3) -> bool:
    current_hash = state.snapshot_hash(extra)
    return current_hash in state.state_hashes[-lookback:]


def decide_retry(
    tool_kind: Literal["read", "write"],
    retry_count: int,
    budget_remaining: int,
) -> PolicyResult:
    if budget_remaining <= 0:
        return PolicyResult(False, "总预算不足，禁止重试")
    if tool_kind == "write":
        return PolicyResult(False, "写操作超时禁止直接重试")
    if retry_count >= settings.READ_RETRY_MAX:
        return PolicyResult(False, "读操作重试次数已达上限")
    delay = 2 ** retry_count
    return PolicyResult(True, "允许读操作重试", retry_delay=float(delay))