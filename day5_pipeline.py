import json
import csv
import os

from trace_logger import TraceLogger, call_tool_with_log
from day5_mock_tools import weather_query, news_search, calculator, delete_schedule

EXPERIMENTS_DIR = "experiments"
LOG_PATH = os.path.join(EXPERIMENTS_DIR, "day5_trace.jsonl")
CSV_PATH = os.path.join(EXPERIMENTS_DIR, "day5_trace_attribution.csv")

LAYER_NAMES = ["工具选择", "参数生成", "工具返回", "忽略返回"]
CSV_FIELDS = ["trace_id", "task_id", "badcase_type", "layer", "root_cause", "evidence"]


def ensure_dirs():
    os.makedirs(EXPERIMENTS_DIR, exist_ok=True)


def clean_old_log():
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)


def build_badcases():
    results = []

    # BC01 工具选择错误：该查天气却调了新闻搜索
    logger = TraceLogger(task_id="task_001", log_path=LOG_PATH)
    call_tool_with_log(logger, step=1, tool_name="news_search",
                       tool_func=news_search,
                       params={"query": "北京明天天气"})
    results.append({
        "trace_id": logger.trace_id,
        "task_id": "task_001",
        "badcase_type": "工具选择错误",
        "layer": "工具选择",
        "root_cause": "意图识别偏差，该选 weather_query 却选 news_search",
        "evidence": "step1 tool=news_search, params={'query':'北京明天天气'}",
        "hit_layers": ["工具选择"],
    })

    # BC02 参数错误：城市名枚举越界
    logger = TraceLogger(task_id="task_002", log_path=LOG_PATH)
    call_tool_with_log(logger, step=1, tool_name="weather_query",
                       tool_func=weather_query,
                       params={"city": "上海浦东新区", "date": "2026-05-20"})
    results.append({
        "trace_id": logger.trace_id,
        "task_id": "task_002",
        "badcase_type": "参数错误",
        "layer": "参数生成",
        "root_cause": "枚举越界，schema 只允许城市名，传入 '上海浦东新区'",
        "evidence": "step1 params.city=上海浦东新区, error_type=schema_error",
        "hit_layers": ["参数生成"],
    })

    # BC03 工具返回异常：超时
    logger = TraceLogger(task_id="task_003", log_path=LOG_PATH)
    call_tool_with_log(logger, step=1, tool_name="weather_query",
                       tool_func=weather_query,
                       params={"city": "广州", "date": "2026-05-20"},
                       max_retry=2)
    results.append({
        "trace_id": logger.trace_id,
        "task_id": "task_003",
        "badcase_type": "工具返回异常",
        "layer": "工具返回",
        "root_cause": "下游天气服务超时，重试 2 次仍失败",
        "evidence": "step1 error_type=timeout, is_retry=true",
        "hit_layers": ["工具返回"],
    })

    # BC04 忽略返回：工具返回晴天，Agent 回答可能下雨
    logger = TraceLogger(task_id="task_004", log_path=LOG_PATH)
    result = call_tool_with_log(logger, step=1, tool_name="weather_query",
                                tool_func=weather_query,
                                params={"city": "深圳", "date": "2026-05-20"})
    final_answer = "深圳今天可能下雨，建议带伞。"
    results.append({
        "trace_id": logger.trace_id,
        "task_id": "task_004",
        "badcase_type": "忽略返回",
        "layer": "忽略返回",
        "root_cause": "模型未采用工具返回的晴天结果，回答可能下雨",
        "evidence": f"step1 result={result}; final_answer={final_answer}",
        "hit_layers": ["忽略返回"],
    })

    # BC05 参数错误：缺必填参数 b
    logger = TraceLogger(task_id="task_005", log_path=LOG_PATH)
    call_tool_with_log(logger, step=1, tool_name="calculator",
                       tool_func=calculator,
                       params={"a": 23, "op": "*"},
                       max_retry=0)
    results.append({
        "trace_id": logger.trace_id,
        "task_id": "task_005",
        "badcase_type": "参数错误",
        "layer": "参数生成",
        "root_cause": "缺必填参数 b，calculator 需要 a,b,op",
        "evidence": "step1 params={'a':23,'op':'*'}, 缺 b, error_type=schema_error",
        "hit_layers": ["参数生成"],
    })

    # BC06 工具选择错误：该调工具却没调
    logger = TraceLogger(task_id="task_006", log_path=LOG_PATH)
    logger.log_step(step=1, tool="None", params={},
                    result={"status": "no_tool_called"},
                    elapsed_ms=0, error_type="None",
                    is_retry=False, is_approval=False)
    results.append({
        "trace_id": logger.trace_id,
        "task_id": "task_006",
        "badcase_type": "工具选择错误",
        "layer": "工具选择",
        "root_cause": "该选未选，未调用 weather_query 直接凭记忆回答",
        "evidence": "trace 中无 weather_query 调用 step，step1 tool=None",
        "hit_layers": ["工具选择"],
    })

    # BC07 综合错误：参数枚举越界导致工具报错，且模型忽略报错
    logger = TraceLogger(task_id="task_007", log_path=LOG_PATH)
    result = call_tool_with_log(logger, step=1, tool_name="calculator",
                                tool_func=calculator,
                                params={"a": 10, "b": 0, "op": "divide"},
                                max_retry=0)
    final_answer = "结果是 0。"
    results.append({
        "trace_id": logger.trace_id,
        "task_id": "task_007",
        "badcase_type": "参数错误",
        "layer": "参数生成",
        "root_cause": "参数枚举越界（op='divide'），导致下游报错，且模型忽略报错瞎答",
        "evidence": f"step1 params.op=divide, error_type=schema_error; final_answer={final_answer}",
        "hit_layers": ["参数生成", "工具返回", "忽略返回"],
    })

    # BC08 工具返回异常 + 忽略返回：429 限流，模型强行说成功
    logger = TraceLogger(task_id="task_008", log_path=LOG_PATH)
    result = call_tool_with_log(logger, step=1, tool_name="delete_schedule",
                                tool_func=delete_schedule,
                                params={"event_id": "vip_event"},
                                max_retry=1)
    final_answer = "日程已成功删除。"
    results.append({
        "trace_id": logger.trace_id,
        "task_id": "task_008",
        "badcase_type": "工具返回异常",
        "layer": "工具返回",
        "root_cause": "下游 429 限流，重试 1 次仍失败，且模型忽略报错",
        "evidence": f"step1 error_type=429, is_retry=true; final_answer={final_answer}",
        "hit_layers": ["工具返回", "忽略返回"],
    })

    # BC09 高危操作绕过审批
    logger = TraceLogger(task_id="task_009", log_path=LOG_PATH)
    result = call_tool_with_log(logger, step=1, tool_name="delete_schedule",
                                tool_func=delete_schedule,
                                params={"event_id": "event_123"},
                                max_retry=0,
                                need_approval=False)
    results.append({
        "trace_id": logger.trace_id,
        "task_id": "task_009",
        "badcase_type": "安全越权",
        "layer": "工具选择",
        "root_cause": "高危操作绕过了审批流程，直接执行了工具",
        "evidence": "step1 need_approval=False, result={'status':'deleted'}",
        "hit_layers": ["工具选择"],
    })

    return results


def compute_layer_rates(badcases):
    N = len(badcases)
    rates = {}
    for layer in LAYER_NAMES:
        hit = sum(1 for bc in badcases if layer in bc["hit_layers"])
        rates[layer] = {"hit": hit, "total": N, "rate": hit / N}
    return rates


def write_csv(badcases):
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for bc in badcases:
            writer.writerow({k: bc[k] for k in CSV_FIELDS})


def validate_csv_fields():
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        missing = [c for c in CSV_FIELDS if c not in header]
        assert not missing, f"CSV 缺字段: {missing}"


def validate_trace_replay(badcases):
    log_trace_ids = set()
    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            log_trace_ids.add(json.loads(line)["trace_id"])
    for bc in badcases:
        assert bc["trace_id"] in log_trace_ids, f"CSV trace_id 无法回放: {bc['trace_id']}"


def main():
    ensure_dirs()
    clean_old_log()

    badcases = build_badcases()
    rates = compute_layer_rates(badcases)

    write_csv(badcases)
    validate_csv_fields()
    validate_trace_replay(badcases)

    print("Day 5 执行完成（仅生成数据与 CSV）")
    print(f"日志: {LOG_PATH}")
    print(f"CSV: {CSV_PATH}")
    print("\n四层错误率：")
    for layer in LAYER_NAMES:
        r = rates[layer]
        print(f"  {layer}: {r['hit']}/{r['total']} = {r['rate']:.1%}")


if __name__ == "__main__":
    main()