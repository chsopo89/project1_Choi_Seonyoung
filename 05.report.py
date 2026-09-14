import csv
from collections import defaultdict

CSV_PATH = "benchmark_log.csv"

rows = []
with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        rows.append(row)

grouped = defaultdict(list)
for r in rows:
    grouped[r["label"]].append(r)

print(f"\n{'모델':<14}{'회수':>5}{'평균초':>9}{'평균tok/s':>11}{'평균출력':>10}")
print("-" * 50)

for label, items in grouped.items():
    n = len(items)
    avg_sec = sum(float(i["latency_sec"]) for i in items) / n
    avg_tps = sum(float(i["tokens_per_sec"]) for i in items) / n
    avg_out = sum(int(i["output_tokens"]) for i in items) / n
    print(f"{label:<14}{n:>5}{avg_sec:>9.1f}{avg_tps:>11.1f}{avg_out:>10.0f}")

print(f"\n{'=' * 50}\n전체 기록\n{'=' * 50}")
print(f"{'시각':<10}{'모델':<14}{'초':>8}{'tok/s':>9}{'출력':>8}")
for r in rows:
    t = r["timestamp"][11:16]
    print(f"{t:<10}{r['label']:<14}{r['latency_sec']:>8}{r['tokens_per_sec']:>9}{r['output_tokens']:>8}")