"""로컬 모델 벤치마크 수집 (Ollama 네이티브 API)

실행 전:  uv add ollama
예시:
  python 04.ollama_test.py --models llama3.1:8b --questions q08 q09 --runs 3 --reload question --tag A
"""

import argparse
import csv
import os
import re
import time
import json
from datetime import datetime

from ollama import Client, ResponseError

SYSTEM_PROMPT = (
    "당신은 네트워크 엔지니어입니다. "
    "질문에 대해 3000자 이내로 답변하세요. "
    "확인할 항목과 점검 순서를 중심으로 서술하고, "
    "확실하지 않은 명령어나 설정값은 추측하지 말고 모른다고 하세요."
)

# -----------------------------
# 1) 가이드라인 자동 판정 함수
# -----------------------------

def detect_guessing(text):
    patterns = [
        r"추측", r"아마", r"일 것", r"정확.*모름",
        r"정확.*알 수", r"확실.*않", r"잘 모르",
    ]
    for p in patterns:
        if re.search(p, text):
            return "Y"
    return ""

with open("verified_commands.json", "r", encoding="utf-8") as f:
    VERIFIED = set(json.load(f))

def detect_unverified_commands(text):
    cmds = re.findall(r"\b[\w\-]+\s[\w\-]+", text)
    for c in cmds:
        if c not in VERIFIED:
            return "Y"
    return ""

# -----------------------------
# 질문 목록
# -----------------------------
QUESTIONS = {
    "q01": "FortiGate 간 IPsec VPN이 연결되고 라우팅도 정상인데, Phase 1과 Phase 2 사이에서 down 로그가 남고 3초에 한 번씩 끊긴다. 어떤 원인을 의심해야 하며, 어떤 설정값을 조정해야 하는가?",
    "q02": "FortiGate의 Virtual IP로 제공하던 웹 서비스가 갑자기 중단됐다. VIP 설정과 정책은 정상이고 서버에도 이상이 없으며, 방화벽과 서버 간 통신도 정상이다(방화벽에서 웹서버로 임시 SSH 접속 시 정상 연결). 웹서버에서 외부로 나가는 통신도 되는데 웹 서비스만 되지 않는다. 무엇이 문제이며 어디부터 확인해야 하는가?",
    "q03": "FortiGate에서 로그가 쌓이지 않고 로그 서버로도 전송되지 않는다. 로그 서버는 정상 동작 중이고 설정과 정책에도 문제가 없으며 ping도 정상이다. 원인은 무엇이며 어떤 순서로 점검하는 것이 좋은가?",
    "q04": "Top-down 방식으로 운영하던 FortiGate 정책이 적용되지 않는다. 포트 번호를 다시 확인해 정확히 입력했고 정책을 맨 위로 올렸는데도 해당 정책은 동작하지 않고 그다음 정책부터 적용된다. 어떤 문제를 의심해야 하며 어디부터 확인해야 하는가?",
    "q05": "HA로 구성된 Cisco 스위치에서 STP 루프가 발생했고, 이 상태에서 HA가 정상적으로 넘어가지 않는다. 로그에는 문제로 볼 만한 내용이 없고 show spanning-tree summary 결과에도 이상이 없다. 무엇을 확인해야 하며 어떤 조치를 먼저 취해야 하는가?",
    "q06": "Cisco 스위치에 NTP를 정상적으로 설정했는데, 다음 유지보수 때 확인해 보니 시간이 어긋나 있다. NTP 서버는 정상이고 유독 한 대만 틀어져 있다. 스위치에서 어느 부분을 확인해야 하며, 이때 NTP 서버를 변경하는 것이 맞는 접근인가?",
    "q07": "HA로 구성된 Cisco 스위치와 Juniper 스위치가 서로 연결돼 있다. Juniper는 HA가 정상적으로 넘어가는데, Cisco는 넘어가지 않고 Active 스위치만 off 되는 현상이 발생한다. 로그에도 Active 스위치가 꺼졌다는 기록만 남아 있다. 어느 쪽 스위치를 먼저 확인해야 하며 어떤 설정을 변경해야 하는가?",
    "q08": "NetScreen 방화벽과 FortiGate 간 IPsec VPN에서 터널 구간 통신은 되지만, 전체 VPN 연결 상태는 disable로 표시된다. 어디부터 확인해야 하며, 어느 쪽 방화벽 설정을 먼저 변경해야 연결이 정상화되는가?",
    "q09": "Cisco 스위치에 광 SFP 모듈을 연결했으나 인식되지 않는다. 확인 결과 Cisco 정품이 맞다. 어떤 명령어로 상태를 확인할 수 있으며, 이 경우 A/S는 어떤 방식으로 받을 수 있는가? 서드파티 모듈을 사용할 경우 A/S는 어떻게 진행되는가?",
    "q10": "기존 Cisco 스위치에서 Juniper 스위치로 장비를 이전하는 중이다. 전환 기간이라 두 장비가 동시에 물려 있고, 트렁크 구간은 802.1Q로 양쪽 모두 설정했으며 VLAN ID도 동일하게 맞췄다. 링크는 up 되고 LLDP로 서로 인식된다. 그런데 일부 VLAN만 통신이 되지 않고, 포트를 올린 뒤부터 간헐적으로 루프성 트래픽이 관측된다. 각 스위치 내부에서는 단말 간 통신에 문제가 없다. 어디부터 확인해야 하며, 이전 작업은 어떤 순서로 진행하는 것이 안전한가?",
}

TARGETS = [
    ("llama3.1:8b", "llama3.1:8b"),
    ("qwen3:8b",    "qwen3:8b"),
    ("gemma3:4b",   "gemma3:4b"),
]

NO_THINK = {"qwen3:8b"}

RUNS = 1
CSV_PATH = "benchmark_local_v2.csv"   # [수정1] 이전 결과와 분리
RESP_DIR = "responses"
CHAR_LIMIT = 3000
PREVIEW_LEN = 60

NUM_CTX = 8192
NUM_PREDICT = 8192
TEMPERATURE = 1.0
SEED = 42   # 기준값. 실제 사용 seed = SEED + 회차 (43, 44, 45...)

OPTIONS = {
    "num_ctx": NUM_CTX,
    "num_predict": NUM_PREDICT,
    "temperature": TEMPERATURE,
    "seed": SEED,
}

# -----------------------------
# 명령행 옵션
# -----------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--models", nargs="+")
parser.add_argument("--questions", nargs="+")
parser.add_argument("--runs", type=int, default=RUNS)
parser.add_argument("--reload", choices=["none", "question", "run"], default="none")
parser.add_argument("--tag", default="")
args = parser.parse_args()

if args.models:
    TARGETS = [t for t in TARGETS if t[0] in args.models]
if args.questions:
    missing = [q for q in args.questions if q not in QUESTIONS]
    if missing:
        raise SystemExit(f"없는 문항: {missing}")
    QUESTIONS = {q: QUESTIONS[q] for q in args.questions}
RUNS = args.runs

# -----------------------------
# FIELDS 확장 (가이드라인 자동 판정 포함)
# -----------------------------
FIELDS = [
    "세션", "순번", "날짜", "시각",
    "문제", "모델", "모델태그", "digest", "양자화", "컨텍스트설정",
    "회차", "상태", "종료사유",
    "입력토큰", "출력토큰", "응답글자수", "제약초과",
    "추측여부", "위험명령어",
    "응답초", "로딩초", "프롬프트평가초", "생성초", "초당토큰",
    "VRAM_MiB", "적재상태", "미측정사유",
    "미리보기", "원문경로", "오류",
    "조건", "재적재", "seed", "사고글자수",   # [수정2] seed 열 추가
]

STATUS_KO = {"ok": "정상", "error": "실패", "skipped": "건너뜀"}
FINISH_KO = {"stop": "정상종료", "length": "토큰한도", "load": "로드만", "": "없음"}

SESSION = datetime.now().strftime("%m%d-%H%M")
NS = 1_000_000_000
MIB = 1024 * 1024

client = Client(host="http://localhost:11434", timeout=900)

# -----------------------------
# 유틸 함수
# -----------------------------
def field(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        value = obj.get(name, default)
    else:
        value = getattr(obj, name, default)
    return default if value is None else value

def model_meta(model_id):
    meta = {"digest": "", "양자화": "", "최대컨텍스트": ""}
    try:
        listing = client.list()
        for item in field(listing, "models", []) or []:
            name = field(item, "model", "") or field(item, "name", "")
            if name == model_id:
                meta["digest"] = (field(item, "digest", "") or "")[:19]
                break
    except ResponseError:
        pass

    try:
        shown = client.show(model_id)
        details = field(shown, "details")
        meta["양자화"] = field(details, "quantization_level", "") or ""

        info = field(shown, "modelinfo", {}) or field(shown, "model_info", {}) or {}
        if isinstance(info, dict):
            for key, value in info.items():
                if key.endswith(".context_length"):
                    meta["최대컨텍스트"] = value
                    break
    except ResponseError:
        pass

    return meta

def vram_state(model_id):
    try:
        procs = client.ps()
    except ResponseError:
        return "", ""

    for item in field(procs, "models", []) or []:
        name = field(item, "model", "") or field(item, "name", "")
        if name != model_id:
            continue

        size = field(item, "size", 0) or 0
        size_vram = field(item, "size_vram", 0) or 0

        if size_vram == 0:
            state = "CPU"
        elif size and size_vram >= size:
            state = "GPU"
        else:
            state = f"혼합({size_vram / size * 100:.0f}% GPU)" if size else "혼합"

        return round(size_vram / MIB), state

    return "", "미적재"

def warmup(model_id):
    try:
        client.chat(
            model=model_id,
            messages=[{"role": "user", "content": "hi"}],
            options={**OPTIONS, "num_predict": 1},
        )
        return True
    except ResponseError:
        return False

def reload_model(model_id):
    try:
        client.generate(model=model_id, keep_alive=0)
    except ResponseError:
        pass
    time.sleep(2)
    warmup(model_id)

def save_response(qid, label, run, text):
    os.makedirs(RESP_DIR, exist_ok=True)
    safe = label.replace(":", "_")
    tag = f"_{args.tag}" if args.tag else ""
    path = os.path.join(RESP_DIR, f"{SESSION}{tag}_{qid}_{safe}_run{run}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path.replace("\\", "/")

def preview(text, length=PREVIEW_LEN):
    flat = re.sub(r"[\s*#`>\-]+", " ", text).strip()
    return flat[:length] + ("…" if len(flat) > length else "")

def make_row(seq, now, qid, label, run, status, meta=None, **extra):
    meta = meta or {}
    row = {f: "" for f in FIELDS}
    row.update({
        "세션": SESSION, "순번": seq,
        "날짜": now.strftime("%Y-%m-%d"), "시각": now.strftime("%H:%M:%S"),
        "문제": qid, "모델": label, "회차": run,
        "모델태그": meta.get("태그", ""),
        "digest": meta.get("digest", ""),
        "양자화": meta.get("양자화", ""),
        "컨텍스트설정": NUM_CTX,
        "상태": STATUS_KO.get(status, status),
        "조건": args.tag,
        "재적재": args.reload,
        "seed": SEED + run if run else "",   # [수정3] 회차별 seed 기록
    })
    row.update(extra)
    return row

# -----------------------------
# 실행
# -----------------------------
total = len(TARGETS) * len(QUESTIONS) * RUNS
print(f"대상 {len(TARGETS)}종 / 문제 {len(QUESTIONS)}개 x {RUNS}회 = 총 {total}건")
print(f"순서: {' -> '.join(QUESTIONS)} / 재적재: {args.reload} / 조건: {args.tag or '-'}")
print(f"생성 설정: num_ctx={NUM_CTX} num_predict={NUM_PREDICT} temperature={TEMPERATURE} seed={SEED}+회차\n")

results = []
skipped = []
seq = 0

for label, model_id in TARGETS:
    print(f"\n{'#' * 60}\n[{label}] 워밍업 ({model_id})\n{'#' * 60}")

    meta = model_meta(model_id)
    meta["태그"] = model_id
    print(f"  digest {meta['digest'] or '-'} / 양자화 {meta['양자화'] or '-'} / 모델카드 최대 context {meta['최대컨텍스트'] or '-'}")

    if not warmup(model_id):
        print(f"  [{label}] 건너뜁니다.")
        skipped.append(label)
        seq += 1
        results.append(make_row(
            seq, datetime.now(), "", label, "", "skipped", meta,
            오류="모델을 찾을 수 없음",
        ))
        continue

    mib, state = vram_state(model_id)
    print(f"  적재: {state} / VRAM {mib or '-'} MiB")

    for run in range(1, RUNS + 1):
        if args.reload == "run":
            reload_model(model_id)
        for qid, question in QUESTIONS.items():
            if args.reload == "question":
                reload_model(model_id)
            seq += 1
            print(f"\n{'=' * 60}\n[{label}] {qid} / run {run} / seed {SEED + run}\n{'=' * 60}")

            now = datetime.now()
            started = time.perf_counter()

            try:
                response = client.chat(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": question},
                    ],
                    options={**OPTIONS, "seed": SEED + run},   # [수정4] 회차마다 다른 seed
                    think=False if model_id in NO_THINK else None,   # [수정5] qwen thinking 끄기
                )
            except ResponseError as error:
                elapsed = time.perf_counter() - started
                print(f"  실패: {error}")
                results.append(make_row(
                    seq, now, qid, label, run, "error", meta,
                    응답초=round(elapsed, 2), 오류=str(error)[:300],
                ))
                continue

            elapsed = time.perf_counter() - started

            message = field(response, "message")
            content = (field(message, "content", "") or "").strip()
            chars = len(content)
            thinking = field(message, "thinking", "") or ""

            done_reason = field(response, "done_reason", "") or ""
            in_tok = field(response, "prompt_eval_count", "")
            out_tok = field(response, "eval_count", "")

            load_ns = field(response, "load_duration", 0) or 0
            prompt_ns = field(response, "prompt_eval_duration", 0) or 0
            eval_ns = field(response, "eval_duration", 0) or 0

            speed, reason = "", ""
            if not isinstance(out_tok, int):
                reason = "eval_count 없음"
            elif eval_ns <= 0:
                reason = "eval_duration <= 0"
            else:
                speed = round(out_tok / (eval_ns / NS), 1)

            mib, state = vram_state(model_id)
            path = save_response(qid, label, run, content) if content else ""
            status = "ok" if content else "error"

            guessing = detect_guessing(content)
            danger = detect_unverified_commands(content)

            print(content[:300] + ("..." if len(content) > 300 else ""))
            print(f"\n  전체 {elapsed:.2f}초 / 로딩 {load_ns / NS:.2f}초 / 생성 {eval_ns / NS:.2f}초")
            print(f"  {speed if speed != '' else '-'} tok/s / 입력 {in_tok} / 출력 {out_tok} / {chars:,}자 / {FINISH_KO.get(done_reason, done_reason)}")
            print(f"  VRAM {mib or '-'} MiB ({state})")

            results.append(make_row(
                seq, now, qid, label, run, status, meta,
                종료사유=FINISH_KO.get(done_reason, done_reason),
                입력토큰=in_tok,
                출력토큰=out_tok,
                응답글자수=chars,
                제약초과="Y" if chars > CHAR_LIMIT else "",
                추측여부=guessing,
                위험명령어=danger,
                응답초=round(elapsed, 2),
                로딩초=round(load_ns / NS, 3),
                프롬프트평가초=round(prompt_ns / NS, 3),
                생성초=round(eval_ns / NS, 3),
                초당토큰=speed,
                VRAM_MiB=mib,
                적재상태=state,
                미측정사유=reason,
                미리보기=preview(content),
                원문경로=path,
                사고글자수=len(thinking),
                오류="" if content else "빈 응답",
            ))

out_csv = CSV_PATH
is_new = not os.path.exists(out_csv)

with open(out_csv, "a", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS)
    if is_new:
        writer.writeheader()
    writer.writerows(results)

ok = [r for r in results if r["상태"] == "정상"]
err = sum(1 for r in results if r["상태"] == "실패")
cut = sum(1 for r in ok if r["종료사유"] == "토큰한도")
over = sum(1 for r in ok if r["제약초과"] == "Y")
nospeed = sum(1 for r in ok if r["미측정사유"])

print(f"\n{'=' * 60}")
print(f"[요약] 세션 {SESSION} / 조건 {args.tag or '-'}")
print(f"{'=' * 60}")
print(f"  성공 {len(ok)} / 실패 {err} / 잘림 {cut} / 글자수 초과 {over}")
if nospeed:
    print(f"  생성속도 미산출 {nospeed}건")
if skipped:
    print(f"  건너뛴 모델: {', '.join(skipped)}")
print(f"  응답 원문: {RESP_DIR}/")
print(f"  기록: {out_csv}")

print("\n모든 작업이 완료되었습니다.")