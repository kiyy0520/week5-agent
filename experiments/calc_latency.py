import csv

# 读取刚才生成的 CSV
with open("experiments/day6_bare_vs_governed.csv", "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

# 提取每个任务的延迟
bare_lat = {r["task_id"]: float(r["latency_seconds"]) for r in rows if r["agent_type"] == "bare"}
gov_lat  = {r["task_id"]: float(r["latency_seconds"]) for r in rows if r["agent_type"] == "governed"}

print("任务 | 裸版延迟(s) | 治理版延迟(s) | 额外延迟(s)")
print("-" * 50)
for tid in bare_lat:
    extra = gov_lat[tid] - bare_lat[tid]
    print(f"{tid}  | {bare_lat[tid]:.3f}      | {gov_lat[tid]:.3f}        | +{extra:.3f}")