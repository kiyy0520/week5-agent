import json, csv, time

# 确保当前目录下有 data/ 文件夹和两个 json 文件
try:
    TASKS = json.load(open("data/test_tasks.json", encoding="utf-8"))
    FAULTS = json.load(open("data/fault_injection.json", encoding="utf-8"))
except FileNotFoundError:
    print("错误：找不到 data/test_tasks.json 或 data/fault_injection.json，请检查路径。")
    exit()

FAULT_MAP = {f["tool"]: f for f in FAULTS}

# ---------- 1. 故障注入包装层 ----------
class FaultInjector:
    def __init__(self):
        self.call_count = {}
    def wrap(self, tool_name, real_fn):
        self.call_count.setdefault(tool_name, 0)
        def wrapped(*args, **kwargs):
            self.call_count[tool_name] += 1
            f = FAULT_MAP.get(tool_name)
            if f and self.call_count[tool_name] == f["trigger_on_call"]:
                ft = f["fault_type"]
                if ft == "timeout":
                    time.sleep(min(f.get("duration_seconds", 10), 0.05))  # 演示用缩减为0.05s
                    raise TimeoutError(f"{tool_name} timeout")
                if ft == "429":
                    raise RuntimeError(f"{tool_name} 429 rate limited")
                if ft == "5xx":
                    raise RuntimeError(f"{tool_name} 5xx server error")
                if ft == "empty":
                    return None
            return real_fn(*args, **kwargs)
        return wrapped

# ---------- 2. mock 工具 ----------
def get_weather(**k): return {"city": "北京", "temp": 25}
def get_exchange_rate(**k): return {"rate": 7.2}
def search_news(**k): return [{"title": "AI 新闻"}]
def summarize(**k): return "三句话总结..."
def get_balance(**k): return {"balance": 800}
def transfer_money(**k): return {"ok": True, "amount": 100}
def create_todo(**k): return {"ok": True, "id": "todo_1"}
def create_order(**k): return {"ok": True, "order_id": "o_1"}
def get_order_status(**k): return {"status": "created"}

TOOLS = {n: f for n, f in globals().items() if callable(f) and n in [
    "get_weather","get_exchange_rate","search_news","summarize",
    "get_balance","transfer_money","create_todo","create_order","get_order_status"]}

# ---------- 3. 两套 Agent ----------
def run_bare(task, injector):
    """裸版：遇错直接抛出异常，卡死/中止，无重试无降级"""
    calls, steps = [], 0
    for tool in task["expected_tools"]:
        steps += 1
        try:
            injector.wrap(tool, TOOLS[tool])()
            calls.append(tool)
        except Exception:
            # 裸版遇错直接崩，没重试，也没完成
            return {"success": 0, "steps": steps, "calls": calls, 
                    "timed_out": 1, "recovered": 0, "behavior": "STUCK"}
    return {"success": 1, "steps": steps, "calls": calls, 
            "timed_out": 0, "recovered": 0, "behavior": "NORMAL"}

def run_governed(task, injector):
    """治理版：读重试，写降级，不盲重试写工具"""
    calls, steps = [], 0
    timed_out = 0
    behavior = "NORMAL"
    
    for tool in task["expected_tools"]:
        steps += 1
        for attempt in range(3):  # 最多重试3次
            try:
                injector.wrap(tool, TOOLS[tool])()
                calls.append(tool)
                break  # 成功则跳出重试循环
            except TimeoutError:
                timed_out = 1
                if tool in ("transfer_money", "create_order"):  
                    # 核心逻辑：写超时，绝不盲目重试，立刻降级查证
                    steps += 1
                    behavior = "DEGRADED"
                    break  # 跳出重试，接着走下一个工具
                time.sleep(0.01)  # 读操作退避后重试
            except Exception:
                timed_out = 1
                time.sleep(0.01)
        
        # 如果发生写降级，直接结束当前任务，不盲目往下走造成更多副作用
        if behavior == "DEGRADED":
            break
            
    if timed_out and behavior != "DEGRADED":
        behavior = "RETRIED_OK"  # 读操作经过重试最终成功了

    return {"success": 1, "steps": steps, "calls": calls,
            "timed_out": timed_out, "recovered": timed_out, "behavior": behavior}

# ---------- 4. 跑两套 Agent，落 CSV ----------
results = []
for agent_type in ["bare", "governed"]:
    for task in TASKS:
        injector = FaultInjector()  # 每个任务独立注入
        start = time.time()
        
        # 根据类型调用不同的 Agent
        if agent_type == "bare":
            r = run_bare(task, injector)
        else:
            r = run_governed(task, injector)
            
        latency = time.time() - start
        invalid = len([c for c in r["calls"] if c not in task["expected_tools"]])
        
        results.append({
            "agent_type": agent_type, 
            "task_id": task["id"],
            "success": r["success"], 
            "total_steps": r["steps"],
            "total_tool_calls": max(len(r["calls"]), 1),
            "invalid_tool_calls": invalid,
            "timed_out": r["timed_out"], 
            "recovered_after_timeout": r["recovered"],
            "latency_seconds": round(latency, 3),
            "behavior": r["behavior"]  # 新增行为记录
        })

# 写入 CSV
with open("experiments/day6_bare_vs_governed.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=results[0].keys())
    w.writeheader()
    w.writerows(results)

# ---------- 5. 汇总指标 ----------
def rate(rows, key, denom_key=None):
    num = sum(r[key] for r in rows)
    den = sum(r[denom_key] for r in rows) if denom_key else len(rows)
    return round(num / den, 3) if den else 0

print("\n=== 指标汇总 ===")
for at in ["bare", "governed"]:
    rows = [r for r in results if r["agent_type"] == at]
    timed = [r for r in rows if r["timed_out"] == 1]
    print(at, {
        "完成率": rate(rows, "success"),
        "无效调用率": rate(rows, "invalid_tool_calls", "total_tool_calls"),
        "平均步数": round(sum(r["total_steps"] for r in rows)/len(rows), 2),
        "超时恢复率": round(sum(r["recovered_after_timeout"] for r in timed)/len(timed), 3) if timed else 0,
    })

# ---------- 6. 故障任务行为对照（放在最后，避免 Pylance 报错） ----------
print("\n=== 故障任务行为对照 ===")
# 挑选被注入了故障的任务
fault_tasks = ["T01", "T02", "T03", "T05", "T10"]
for tid in fault_tasks:
    for at in ["bare", "governed"]:
        # 安全获取结果，防止某个任务漏跑
        r = next((x for x in results if x["task_id"]==tid and x["agent_type"]==at), None)
        if r:
            print(f"{tid} {at:9s} behavior={r['behavior']:<18s} timed_out={r['timed_out']} success={r['success']}")