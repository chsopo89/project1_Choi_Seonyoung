import csv
import os
import time
from datetime import datetime
from openai import APIError, APITimeoutError, OpenAI

QUESTION = "Cisco 스위치에 광 SFP 모듈을 연결했으나 인식되지 않는다. 확인 결과 Cisco 정품이 맞다. 어떤 명령어로 상태를 확인할 수 있으며, 이 경우 A/S는 어떤 방식으로 받을 수 있는가? 서드파티 모듈을 사용할 경우 A/S는 어떻게 진행되는가?"

TARGETS = [
    ("llama3.1:8b", "llama3.1:8b"),
    ("mistral:7b",  "mistral:7b-instruct-q4_K_M"),
    ("qwen3:4b",    "qwen3:4b-instruct-2507-q4_K_M"),
]

CSV_PATH = "benchmark_log.csv"

client = OpenAI(
    api_key="ollama",
    base_url="http://localhost:11434/v1",
    timeout=900,
    max_retries=0,
)

results = []

for label, model_id in TARGETS:
    print(f"\n{'=' * 60}\n[{label}] 호출 중...\n{'=' * 60}")

    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": QUESTION}],
            max_tokens=4096,
        )
    except (APITimeoutError, APIError) as error:
        print(f"  실패: {error}")
        continue

    elapsed = time.perf_counter() - started
    choice = response.choices[0]
    usage = response.usage
    speed = usage.completion_tokens / elapsed if elapsed else 0

    print(choice.message.content or "")
    print(f"\n  응답 시간 : {elapsed:.2f}초 / {speed:.1f} tok/s")
    print(f"  출력 토큰 : {usage.completion_tokens:,} / 종료 {choice.finish_reason}")

    results.append([
        datetime.now().isoformat(timespec="seconds"),
        label, model_id, choice.finish_reason,
        usage.prompt_tokens, usage.completion_tokens,
        f"{elapsed:.2f}", f"{speed:.1f}",
    ])

print(f"\n{'=' * 60}\n[요약]\n{'=' * 60}")
print(f"{'모델':<14}{'초':>9}{'tok/s':>10}{'출력토큰':>10}")
for row in results:
    print(f"{row[1]:<14}{row[6]:>9}{row[7]:>10}{row[5]:>10,}")

is_new = not os.path.exists(CSV_PATH)
with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    if is_new:
        writer.writerow([
            "timestamp", "label", "model", "finish_reason",
            "input_tokens", "output_tokens", "latency_sec", "tokens_per_sec",
        ])
    writer.writerows(results)

print(f"\n[기록] {CSV_PATH}에 {len(results)}건 저장했습니다.")