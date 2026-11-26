import json
import time
import uuid
import os


class TraceLogger:
    def __init__(self, task_id, log_path="experiments/day5_trace.jsonl"):
        self.task_id = task_id
        self.trace_id = "trace_" + uuid.uuid4().hex[:8]
        self.log_path = log_path
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def log_step(self, step, tool, params, result,
                 elapsed_ms=0, error_type="None",
                 is_retry=False, is_approval=False):
        record = {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "step": step,
            "tool": tool,
            "params": params,
            "result": result,
            "elapsed_ms": elapsed_ms,
            "error_type": error_type,
            "is_retry": is_retry,
            "is_approval": is_approval,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record


def call_tool_with_log(logger, step, tool_name, tool_func, params,
                       max_retry=1, need_approval=False):
    if need_approval:
        logger.log_step(step=step, tool=tool_name, params=params,
                        result={"status": "pending_approval"},
                        elapsed_ms=0, error_type="None",
                        is_retry=False, is_approval=True)
        return {"status": "pending_approval"}

    last_error = "None"
    for attempt in range(max_retry + 1):
        start = time.time()
        try:
            result = tool_func(**params)
            elapsed = int((time.time() - start) * 1000)
            logger.log_step(step=step, tool=tool_name, params=params,
                            result=result, elapsed_ms=elapsed,
                            error_type="None", is_retry=(attempt > 0),
                            is_approval=False)
            return result
        except TimeoutError:
            last_error = "timeout"
        except (ValueError, TypeError):
            last_error = "schema_error"
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg:
                last_error = "429"
            elif "5xx" in msg or "500" in msg or "503" in msg:
                last_error = "5xx"
            else:
                last_error = "unknown_error"

        elapsed = int((time.time() - start) * 1000)
        logger.log_step(step=step, tool=tool_name, params=params,
                        result={"error": last_error}, elapsed_ms=elapsed,
                        error_type=last_error, is_retry=(attempt > 0),
                        is_approval=False)

    return {"error": last_error, "retried": max_retry}