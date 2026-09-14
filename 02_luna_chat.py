import csv
import os
import time
from datetime import datetime
from openai import APIError, APITimeoutError, OpenAI

QUESTION = "Cisco 스위치에 광 SFP 모듈을 연결했으나 인식되지 않는다. 확인 결과 Cisco 정품이 맞다. 어떤 명령어로 상태를 확인할 수 있으며, 이 경우 A/S는 어떤 방식으로 받을 수 있는가? 서드파티 모듈을 사용할 경우 A/S는 어떻게 진행되는가?"

assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY가 설정되지 않았습니다."
assert os.getenv("OPENAI_MODEL"), "OPENAI_MODEL이 설정되지 않았습니다."

api_key = os.environ["OPENAI_API_KEY"].strip()
model_id = os.environ["OPENAI_MODEL"].strip()

print("API key configured:", True)
print("model:", model_id)

client = OpenAI(
    api_key=api_key,
    base_url="https://api.openai.com/v1",
    timeout=60,
    max_retries=0,
)
print("Luna에 질문을 보냈습니다. 답변을 기다려 주세요.")

started = time.perf_counter()

try:
    response = client.responses.create(
        model=model_id,
        input=QUESTION,
        reasoning={"effort": "none"},
        max_output_tokens=4096,
        tools=[],
        tool_choice="none",
        store=False,
    )
except APITimeoutError:
    raise SystemExit("응답 대기 시간이 초과됐습니다. 재실행 전 사용량을 확인하세요.") from None
except APIError as error:
    status = getattr(error, "status_code", "연결 오류")
    raise SystemExit(f"API 호출 실패: {status}. 가이드의 오류 안내를 확인하세요.") from None

elapsed = time.perf_counter() - started

usage = getattr(response, "usage", None)
if usage:
    input_tokens = getattr(usage, "input_tokens", 0)
    output_tokens = getattr(usage, "output_tokens", 0)
    total_tokens = getattr(usage, "total_tokens", input_tokens + output_tokens)

    details = getattr(usage, "output_tokens_details", None)
    reasoning_tokens = getattr(details, "reasoning_tokens", 0) if details else 0

    cached = getattr(usage, "input_tokens_details", None)
    cached_tokens = getattr(cached, "cached_tokens", 0) if cached else 0

    print("\n[토큰 사용량]")
    print(f"  입력  : {input_tokens:,} (캐시 적중 {cached_tokens:,})")
    print(f"  출력  : {output_tokens:,} (추론 {reasoning_tokens:,})")
    print(f"  합계  : {total_tokens:,}")
else:
    print("\n[토큰 사용량] 응답에 usage 정보가 없습니다.")
    input_tokens = output_tokens = total_tokens = 0

print(f"\n[처리 상태] {response.status}")
print("[Luna 답변]")
print(response.output_text or "출력된 답변이 없습니다.")
if response.status != "completed":
    print("완료된 답변이 아닙니다. 출력이 중간에 끊겼을 수 있습니다.")

PRICE_IN = 0.0      # 1M 입력 토큰당 USD — 요금표 확인 후 입력
PRICE_OUT = 0.0     # 1M 출력 토큰당 USD

cost = (input_tokens * PRICE_IN + output_tokens * PRICE_OUT) / 1_000_000
speed = output_tokens / elapsed if elapsed else 0

print("\n[측정 결과]")
print(f"  응답 시간 : {elapsed:.2f}초")
print(f"  속도      : {speed:.1f} tok/s")
print(f"  추정 비용 : ${cost:.6f}")

CSV_PATH = "benchmark_log.csv"
is_new = not os.path.exists(CSV_PATH)

with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    if is_new:
        writer.writerow([
            "timestamp", "label", "model", "finish_reason",
            "input_tokens", "output_tokens", "latency_sec", "tokens_per_sec",
        ])
    writer.writerow([
        datetime.now().isoformat(timespec="seconds"),
        "luna", model_id, response.status,
        input_tokens, output_tokens, f"{elapsed:.2f}", f"{speed:.1f}",
    ])

print(f"\n[기록] {CSV_PATH}에 저장했습니다.")