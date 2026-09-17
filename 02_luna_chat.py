import csv
import os
import re
import time
from datetime import datetime
from openai import APIError, APITimeoutError, OpenAI

assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY가 설정되지 않았습니다."
MODEL = os.getenv("OPENAI_MODEL")
assert MODEL, "OPENAI_MODEL이 설정되지 않았습니다."

SYSTEM_PROMPT = (
    "당신은 네트워크 엔지니어입니다. "
    "질문에 대해 3000자 이내로 답변하세요. "
    "확인할 항목과 점검 순서를 중심으로 서술하고, "
    "확실하지 않은 명령어나 설정값은 추측하지 말고 모른다고 하세요."
)

QUESTIONS = {
    #"q01": "FortiGate 간 IPsec VPN이 연결되고 라우팅도 정상인데, Phase 1과 Phase 2 사이에서 down 로그가 남고 3초에 한 번씩 끊긴다. 어떤 원인을 의심해야 하며, 어떤 설정값을 조정해야 하는가?",
    #"q02": "FortiGate의 Virtual IP로 제공하던 웹 서비스가 갑자기 중단됐다. VIP 설정과 정책은 정상이고 서버에도 이상이 없으며, 방화벽과 서버 간 통신도 정상이다(방화벽에서 웹서버로 임시 SSH 접속 시 정상 연결). 웹서버에서 외부로 나가는 통신도 되는데 웹 서비스만 되지 않는다. 무엇이 문제이며 어디부터 확인해야 하는가?",
    "q03": "FortiGate에서 로그가 쌓이지 않고 로그 서버로도 전송되지 않는다. 로그 서버는 정상 동작 중이고 설정과 정책에도 문제가 없으며 ping도 정상이다. 원인은 무엇이며 어떤 순서로 점검하는 것이 좋은가?",
    #"q04": "Top-down 방식으로 운영하던 FortiGate 정책이 적용되지 않는다. 포트 번호를 다시 확인해 정확히 입력했고 정책을 맨 위로 올렸는데도 해당 정책은 동작하지 않고 그다음 정책부터 적용된다. 어떤 문제를 의심해야 하며 어디부터 확인해야 하는가?",
    #"q05": "HA로 구성된 Cisco 스위치에서 STP 루프가 발생했고, 이 상태에서 HA가 정상적으로 넘어가지 않는다. 로그에는 문제로 볼 만한 내용이 없고 show spanning-tree summary 결과에도 이상이 없다. 무엇을 확인해야 하며 어떤 조치를 먼저 취해야 하는가?",
    "q06": "Cisco 스위치에 NTP를 정상적으로 설정했는데, 다음 유지보수 때 확인해 보니 시간이 어긋나 있다. NTP 서버는 정상이고 유독 한 대만 틀어져 있다. 스위치에서 어느 부분을 확인해야 하며, 이때 NTP 서버를 변경하는 것이 맞는 접근인가?",
    "q07": "HA로 구성된 Cisco 스위치와 Juniper 스위치가 서로 연결돼 있다. Juniper는 HA가 정상적으로 넘어가는데, Cisco는 넘어가지 않고 Active 스위치만 off 되는 현상이 발생한다. 로그에도 Active 스위치가 꺼졌다는 기록만 남아 있다. 어느 쪽 스위치를 먼저 확인해야 하며 어떤 설정을 변경해야 하는가?",
    #"q08": "NetScreen 방화벽과 FortiGate 간 IPsec VPN에서 터널 구간 통신은 되지만, 전체 VPN 연결 상태는 disable로 표시된다. 어디부터 확인해야 하며, 어느 쪽 방화벽 설정을 먼저 변경해야 연결이 정상화되는가?",
    "q09": "Cisco 스위치에 광 SFP 모듈을 연결했으나 인식되지 않는다. 확인 결과 Cisco 정품이 맞다. 어떤 명령어로 상태를 확인할 수 있으며, 이 경우 A/S는 어떤 방식으로 받을 수 있는가? 서드파티 모듈을 사용할 경우 A/S는 어떻게 진행되는가?",
    "q10": "기존 Cisco 스위치에서 Juniper 스위치로 장비를 이전하는 중이다. 전환 기간이라 두 장비가 동시에 물려 있고, 트렁크 구간은 802.1Q로 양쪽 모두 설정했으며 VLAN ID도 동일하게 맞췄다. 링크는 up 되고 LLDP로 서로 인식된다. 그런데 일부 VLAN만 통신이 되지 않고, 포트를 올린 뒤부터 간헐적으로 루프성 트래픽이 관측된다. 각 스위치 내부에서는 단말 간 통신에 문제가 없다. 어디부터 확인해야 하며, 이전 작업은 어떤 순서로 진행하는 것이 안전한가?",
}

LABEL = "luna"                      # CSV에 남길 모델 표시명
RUNS = 1                            # Cloud는 문항당 1회 (로컬 3회와 반복 수 다름)
CSV_PATH = "benchmark_luna.csv"     # 로컬 결과와 파일 분리
RESP_DIR = "responses_luna"
CHAR_LIMIT = 3000
PREVIEW_LEN = 60

FIELDS = [
    "세션", "순번", "날짜", "시각",
    "문제", "모델", "회차", "상태",
    "종료사유", "입력토큰", "출력토큰", "응답글자수", "제약초과",
    "응답초", "초당토큰", "미리보기", "원문경로", "오류",
]

SESSION = datetime.now().strftime("%m%d-%H%M")

client = OpenAI(timeout=900, max_retries=0)


def save_response(qid, label, run, text):
    os.makedirs(RESP_DIR, exist_ok=True)
    safe = label.replace(":", "_")
    path = os.path.join(RESP_DIR, f"{SESSION}_{qid}_{safe}_run{run}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path.replace("\\", "/")


def preview(text, length=PREVIEW_LEN):
    """줄바꿈과 마크다운 기호를 걷어내고 한 줄로 만든다."""
    flat = re.sub(r"[\s*#`>\-]+", " ", text).strip()
    return flat[:length] + ("…" if len(flat) > length else "")


def make_row(seq, now, qid, run, status, **extra):
    row = {
        "세션": SESSION, "순번": seq,
        "날짜": now.strftime("%Y-%m-%d"), "시각": now.strftime("%H:%M:%S"),
        "문제": qid, "모델": LABEL, "회차": run, "상태": status,
        "종료사유": "", "입력토큰": "", "출력토큰": "", "응답글자수": "",
        "제약초과": "", "응답초": "", "초당토큰": "",
        "미리보기": "", "원문경로": "", "오류": "",
    }
    row.update(extra)
    return row


print(f"모델: {MODEL} / 문제 {len(QUESTIONS)}개 x {RUNS}회\n")

results = []
seq = 0

for qid, question in QUESTIONS.items():
    for run in range(1, RUNS + 1):
        seq += 1
        print(f"\n{'=' * 60}\n[{LABEL}] {qid} / run {run}\n{'=' * 60}")

        now = datetime.now()
        started = time.perf_counter()

        try:
            response = client.responses.create(
                model=MODEL,
                instructions=SYSTEM_PROMPT,
                input=question,
            )
        except (APITimeoutError, APIError) as error:
            elapsed = time.perf_counter() - started
            print(f"  실패: {error}")
            results.append(make_row(
                seq, now, qid, run, "실패",
                응답초=round(elapsed, 2), 오류=str(error)[:300],
            ))
            continue

        elapsed = time.perf_counter() - started
        content = (response.output_text or "").strip()
        chars = len(content)

        usage = getattr(response, "usage", None)
        in_tok = getattr(usage, "input_tokens", "") if usage else ""
        out_tok = getattr(usage, "output_tokens", "") if usage else ""
        speed = out_tok / elapsed if (out_tok and elapsed) else 0

        # reasoning 토큰이 별도로 보고되면 함께 기록
        reasoning = ""
        details = getattr(usage, "output_tokens_details", None) if usage else None
        if details is not None:
            reasoning = getattr(details, "reasoning_tokens", "") or ""

        path = save_response(qid, LABEL, run, content) if content else ""
        status = "정상" if content else "실패"

        print(content[:300] + ("..." if len(content) > 300 else ""))
        print(f"\n  {elapsed:.2f}초 / {speed:.1f} tok/s / "
              f"출력 {out_tok}토큰 / {chars:,}자"
              + (f" (추론 {reasoning})" if reasoning else ""))
        if chars > CHAR_LIMIT:
            print(f"  주의: 글자수 제약({CHAR_LIMIT}자)을 넘었습니다")

        results.append(make_row(
            seq, now, qid, run, status,
            종료사유=getattr(response, "status", "") or "",
            입력토큰=in_tok, 출력토큰=out_tok, 응답글자수=chars,
            제약초과="Y" if chars > CHAR_LIMIT else "",
            응답초=round(elapsed, 2), 초당토큰=round(speed, 1),
            미리보기=preview(content), 원문경로=path,
            오류="" if content else "빈 응답",
        ))

is_new = not os.path.exists(CSV_PATH)
with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS)
    if is_new:
        writer.writeheader()
    writer.writerows(results)

ok = [r for r in results if r["상태"] == "정상"]
err = len(results) - len(ok)
over = sum(1 for r in ok if r["제약초과"] == "Y")

print(f"\n{'=' * 60}\n[요약] 세션 {SESSION} / {MODEL}\n{'=' * 60}")
print(f"  성공 {len(ok)} / 실패 {err} / 글자수 초과 {over}")
print(f"  응답 원문: {RESP_DIR}/")
print(f"  기록: {CSV_PATH}")