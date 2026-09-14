from time import perf_counter

from ollama import Client

MODEL = "qwen3:4b-instruct-2507-q4_K_M"
QUESTION = "Forgitage 간의 IPsec VPN 연결이 되었고 Routing 또한 정상적으로 확인이 되었으나 phase 1과 2사에서 down 로그가 확인이 되었고 3초마다 한번씩 끊기는 현상이 발견이 되고 있다. 이때 어떤 문제를 생각해야 하며 설정에서 어떤 값을 변경해야 할까?."
client = Client(host="http://127.0.0.1:11434", timeout=180)

print("Ollama의 답변을 끝까지 받는 데 걸린 시간을 측정합니다.")
start = perf_counter()
response = client.chat(
    model=MODEL,
    messages=[{"role": "user", "content": QUESTION}],
    stream=False,
    options={"temperature": 0, "num_predict": 256},
)
elapsed = perf_counter() - start

print("\n[Ollama 답변]")
print(response.message.content)
print(f"\n전체 응답 시간: {elapsed:.2f}초")
# 첫 토큰 시간(TTFT)이 아닙니다. 필요하면 모델 로딩 시간도 포함됩니다.
