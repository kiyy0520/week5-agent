# agent/state.py
from dataclasses import dataclass, field
from typing import Any
import hashlib
import json
import time


@dataclass
class AgentState:
    trace_id: str
    max_steps: int
    budget_remaining: int
    run_deadline: float
    step: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    state_hashes: list[str] = field(default_factory=list)

    def budget_left(self) -> bool:
        return self.budget_remaining > 0

    def deadline_left(self) -> bool:
        return time.time() < self.run_deadline

    def can_continue(self) -> bool:
        return self.step < self.max_steps and self.budget_left() and self.deadline_left()

    def record_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
        args_summary = json.dumps(args, sort_keys=True, ensure_ascii=False)[:200]
        self.tool_calls.append({"tool": tool_name, "args": args_summary})
        self.step += 1

    def snapshot_hash(self, extra: str = "") -> str:
        raw = json.dumps(
            {"step": self.step, "tool_calls": self.tool_calls, "extra": extra},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()