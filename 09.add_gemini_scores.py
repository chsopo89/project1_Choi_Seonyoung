"""
Gemini 확정 점수를 scores_v2_t1.csv에 추가한다.

사용법 (프로젝트 폴더에서)
    python .\\09.add_gemini_scores.py            # 미리보기만 (파일 변경 없음)
    python .\\09.add_gemini_scores.py --apply    # 백업 후 실제로 추가

- 기존 CSV의 헤더를 읽어서 열 이름을 자동으로 맞춘다.
  (가로형: A~E 열이 따로 있음 / 세로형: axis, score 열이 있음 둘 다 지원)
- 필요한 열을 못 찾으면 아무것도 쓰지 않고 헤더를 보여준 뒤 멈춘다.
  그때는 아래 COLUMN_OVERRIDE에 실제 열 이름을 적어주면 된다.
- 이미 Gemini 행이 있으면 멈춘다. (--force로 무시 가능)
- --apply 시 scores_v2_t1.csv.bak_날짜시각 으로 백업을 먼저 만든다.
"""
import argparse
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCORES = BASE / "scores_v2_t1.csv"
BENCH = BASE / "benchmark_gemini.csv"
RESP_DIR = BASE / "responses_gemini"
DEFAULT_MODEL = "gemini-3.6-flash"
RUN = 1
SCORER = "human (AI 초안 검토·수정)"

# q10 A축: Junos EX 기본 STP 모드 서술을 미확인으로 두면 2, 틀림으로 정하면 1
Q10_A = 2

# 자동 매칭이 안 될 때만 채운다. 예: {"qid": "question_id", "reason": "note"}
COLUMN_OVERRIDE = {}

KEEP = "초안 판정 유지 (채점자 원문 대조 검토)"
E_OK = "3000자 이내, 형식 준수"
E_OVER = "3000자 초과"

SCORES_DATA = {
    "q03": {
        "A": (3, "제시 명령(get system performance status, diagnose sys process pidof miglogd, "
                 "fnsysctl killall miglogd, get log syslogd setting, sniffer) 모두 공식 문서 확인, 틀린 것 0"),
        "B": (3, KEEP),
        "C": (3, KEEP),
        "D": (1, "4단계 syslog 설정 확인이 질문의 '설정 정상' 단서와 겹치는 배제 조치 "
                 "(source-ip 확인만 떼어 보면 3점 가능)"),
        "E": (3, E_OK),
        "flags": "R",
        "flag_note": "R: '장비 재부팅을 고려', 운영 중 로그 데몬 강제 종료(fnsysctl killall miglogd)",
    },
    "q06": {
        "A": (1, "NTP-5-PEERUNSYNC가 Cisco 공식 문서·웹 검색 모두에서 확인되지 않음 → 틀린 것 1"),
        "B": (3, "원인을 단정하지 않고 점검 항목과 확인 명령으로 제시, 'reach 0이라면', "
                 "'인증 사용 시', '통신이 안 된다면/시간만 다르다면' 등 조건부 분기"),
        "C": (3, "CPU 부하·상단 방화벽 점검도 NTP 동기화 실패와 연결해 제시, 상황 특화"),
        "D": (3, "첫 문단에서 NTP 서버 변경(배제 조치)을 부정하고 '다른 장비 정상' 단서로 장비 단독 문제로 좁힌 뒤 "
                 "가설(ntp source, ACL, 인증키, 타임존, calendar)과 검증 명령 제시"),
        "E": (3, E_OK),
        "flags": "",
        "flag_note": "",
    },
    "q07": {
        "A": (1, "show virtual switch는 없는 형태(VSS는 show switch virtual), "
                 "Bundled를 'LACP 대기 상태'로 설명 → 틀린 것 2"),
        "B": (2, KEEP),
        "C": (3, KEEP),
        "D": (3, "Cisco와 Juniper를 한 HA 그룹으로 전제하지 않고 'Cisco 먼저'를 정확히 지목"),
        "E": (1, E_OVER),
        "flags": "L",
        "flag_note": "L: 3000자 초과",
    },
    "q09": {
        "A": (1, "errdisable detect cause unsupported-transceiver가 Cisco 공식 문서·웹 검색 모두에서 "
                 "확인되지 않음 → 틀린 것 1"),
        "B": (3, KEEP),
        "C": (3, "A/S 구조(SMARTnet·TAC·구매처, 서드파티는 판매처, 정품 교체 후 재현 요구)가 reference와 일치"),
        "D": (3, "A/S 경로를 구매 형태별로 나눠 reference와 같은 흐름으로 제시"),
        "E": (1, E_OVER),
        "flags": "R, L",
        "flag_note": "R: service unsupported-transceiver 제시 / L: 3000자 초과",
    },
    "q10": {
        "A": (Q10_A, "Junos EX 기본 STP 모드가 RSTP라는 서술이 공식 문서에서 확인되지 않음 → "
                     + ("미확인 1, 틀린 것 0" if Q10_A == 2 else "틀린 것 1")),
        "B": (3, KEEP),
        "C": (3, "reference 가설(native VLAN 불일치, 허용 VLAN 목록, PVST+/RSTP 불일치 → MSTP/VSTP)과 거의 일치"),
        "D": (3, "reference 가설과 같은 순서로 단서 기반 가설과 검증 제시"),
        "E": (1, E_OVER),
        "flags": "L",
        "flag_note": "L: 3000자 초과",
    },
}
AXES = ["A", "B", "C", "D", "E"]

CANDIDATES = {
    "model": ["model", "model_name", "모델"],
    "qid": ["qid", "question_id", "question", "q", "item", "문항"],
    "run": ["run", "repeat", "trial", "iter", "회차"],
    "axis": ["axis", "축"],
    "score": ["score", "점수", "value"],
    "reason": ["reason", "rationale", "evidence", "basis", "note", "근거"],
    "flags": ["flags", "flag", "플래그"],
    "file": ["file", "path", "response", "resp", "response_file", "resp_file"],
    "scorer": ["scorer", "rater", "채점자"],
    "timestamp": ["timestamp", "scored_at", "time", "date", "datetime"],
    "total": ["total", "sum", "총점", "합계"],
}


def find_col(header, names):
    low = {h.lower().strip(): h for h in header}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def map_columns(header):
    cols = {k: find_col(header, v) for k, v in CANDIDATES.items()}
    for x in AXES:
        cols[f"score_{x}"] = find_col(header, [x, f"{x}_score", f"score_{x}", f"axis_{x}"])
        cols[f"reason_{x}"] = find_col(header, [f"{x}_reason", f"reason_{x}", f"{x}_note", f"{x}_evidence"])
    for k, v in COLUMN_OVERRIDE.items():
        if v not in header:
            sys.exit(f"[중단] COLUMN_OVERRIDE의 '{v}' 열이 CSV에 없습니다.")
        cols[k] = v
    return cols


# scores_v2_t1.csv 확인 결과: 플래그는 응답 단위로 계산되어 A~E 모든 행에 같은 값(1/0)이 들어간다.
FLAG_ON, FLAG_OFF = "1", "0"
FLAG_FROM_MARK = {"risky_flag": "R", "over_limit": "L"}   # 채점 판정에서 가져오는 플래그
ZERO_COLS = ["repeat_flag"]                               # 5건 모두 반복 붕괴 없음
# 07.scoring.py가 answer_keys.py 키워드로 자동 검출하는 플래그. 이 스크립트는 검출 로직이 없으므로 비워 둔다.
AUTO_COLS = ["excluded_flag", "contradicted_flag", "facts_flag"]
RUBRIC = "v2.1"


def learn_formats(rows, header, axis_col):
    info = {}
    if "rubric" in header:
        info["rubric"] = RUBRIC
    if "session" in header:
        info["session"] = datetime.now().strftime("%m%d-%H%M")  # 기존 형식: 0916-1635
    return info


def model_name():
    if BENCH.exists():
        with BENCH.open(encoding="utf-8-sig", newline="") as f:
            r = csv.DictReader(f)
            mcol = find_col(r.fieldnames or [], CANDIDATES["model"])
            if mcol:
                for row in r:
                    if row.get(mcol):
                        return row[mcol]
    return DEFAULT_MODEL


def qid_format(existing_rows, qcol):
    """기존 CSV의 문항 표기(q03 / Q03 / 3 / 03)에 맞춘다."""
    sample = next((r[qcol] for r in existing_rows if r.get(qcol)), "q01")

    def fmt(q):
        num = q[1:]
        if sample.isdigit():
            return num if sample.startswith("0") else str(int(num))
        return ("Q" if sample[0].isupper() else "q") + num
    return fmt


def response_file(qid):
    if not RESP_DIR.exists():
        return ""
    hits = [p for p in RESP_DIR.iterdir() if qid in p.name.lower()]
    return str(hits[0].relative_to(BASE)) if len(hits) == 1 else ""


def apply_extra(row, axis, data, info):
    marks = [m.strip() for m in data["flags"].split(",") if m.strip()]
    for col, mark in FLAG_FROM_MARK.items():
        if col in row:
            row[col] = FLAG_ON if mark in marks else FLAG_OFF
    for col in ZERO_COLS:
        if col in row:
            row[col] = FLAG_OFF
    for col in AUTO_COLS:
        if col in row:
            row[col] = ""
    for k in ("rubric", "session"):
        if k in info:
            row[k] = info[k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 CSV에 추가")
    ap.add_argument("--force", action="store_true", help="기존 Gemini 행이 있어도 추가")
    args = ap.parse_args()

    if not SCORES.exists():
        sys.exit(f"[중단] {SCORES.name} 파일이 없습니다.")

    with SCORES.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)

    cols = map_columns(header)
    long_form = bool(cols["axis"] and cols["score"])
    wide_form = all(cols[f"score_{x}"] for x in AXES)

    missing = []
    if not cols["model"]:
        missing.append("model")
    if not cols["qid"]:
        missing.append("qid")
    if not (long_form or wide_form):
        missing.append("axis+score 또는 A~E 점수 열")
    if missing:
        print("[중단] 필요한 열을 찾지 못했습니다:", ", ".join(missing))
        print("현재 헤더:", header)
        print("COLUMN_OVERRIDE에 실제 열 이름을 적고 다시 실행하세요. 파일은 변경하지 않았습니다.")
        sys.exit(1)

    model = model_name()
    mcol, qcol = cols["model"], cols["qid"]
    dup = [r for r in rows if "gemini" in (r.get(mcol) or "").lower()]
    if dup and not args.force:
        print(f"[중단] 이미 Gemini 행이 {len(dup)}개 있습니다. 확인 후 필요하면 --force로 실행하세요.")
        sys.exit(1)

    fmt = qid_format(rows, qcol)
    fmtinfo = learn_formats(rows, header, cols["axis"] if long_form else None)
    now = datetime.now().isoformat(timespec="seconds")
    new_rows = []

    for q, data in SCORES_DATA.items():
        base = {h: "" for h in header}
        base[mcol] = model
        base[qcol] = fmt(q)
        if cols["run"]:
            base[cols["run"]] = str(RUN)
        if cols["file"]:
            base[cols["file"]] = response_file(q)
        if cols["scorer"]:
            base[cols["scorer"]] = SCORER
        if cols["timestamp"]:
            base[cols["timestamp"]] = now

        if long_form:
            for x in AXES:
                row = dict(base)
                score, reason = data[x]
                row[cols["axis"]] = x
                row[cols["score"]] = str(score)
                if cols["reason"]:
                    row[cols["reason"]] = reason
                if cols["flags"] and x == "D":  # 플래그는 한 행에만 기록
                    row[cols["flags"]] = data["flags"]
                apply_extra(row, x, data, fmtinfo)
                new_rows.append(row)
        else:
            row = dict(base)
            reasons = []
            for x in AXES:
                score, reason = data[x]
                row[cols[f"score_{x}"]] = str(score)
                if cols[f"reason_{x}"]:
                    row[cols[f"reason_{x}"]] = reason
                else:
                    reasons.append(f"{x}{score}: {reason}")
            if cols["total"]:
                row[cols["total"]] = str(sum(data[x][0] for x in AXES))
            apply_extra(row, None, data, fmtinfo)
            if cols["flags"]:
                row[cols["flags"]] = data["flags"]
            if cols["reason"]:
                if data["flag_note"]:
                    reasons.append(data["flag_note"])
                row[cols["reason"]] = " | ".join(reasons)
            new_rows.append(row)

    # 미리보기
    print(f"형식: {'세로형(axis/score)' if long_form else '가로형(A~E 열)'}  /  모델명: {model}")
    print("열 매칭:", {k: v for k, v in cols.items() if v})
    for k, v in fmtinfo.items():
        print(f"  {k}: '{v}'")
    print(f"  risky_flag / over_limit: 판정의 R / L 기준 {FLAG_ON}·{FLAG_OFF}, A~E 모든 행에 같은 값")
    print(f"  repeat_flag: {FLAG_OFF}  /  {', '.join(AUTO_COLS)}: 빈칸 (자동 검출 미실행)")
    unfilled = [h for h in header if all(not r[h] for r in new_rows)]
    if unfilled:
        print("비워둘 열:", unfilled)
    total = 0
    for q, data in SCORES_DATA.items():
        s = [data[x][0] for x in AXES]
        total += sum(s)
        print(f"  {q}: A{s[0]} B{s[1]} C{s[2]} D{s[3]} E{s[4]} = {sum(s)}  {data['flags']}")
    print(f"  평균: {total / len(SCORES_DATA):.1f} / 15   (추가될 행 {len(new_rows)}개)")

    if not args.apply:
        print("\n미리보기입니다. 문제없으면 --apply를 붙여 실행하세요.")
        return

    backup = SCORES.with_name(f"{SCORES.name}.bak_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(SCORES, backup)
    needs_nl = SCORES.read_bytes()[-1:] not in (b"\n", b"")
    with SCORES.open("a", encoding="utf-8", newline="") as f:
        if needs_nl:
            f.write("\r\n")
        csv.DictWriter(f, fieldnames=header).writerows(new_rows)
    print(f"\n추가 완료. 백업: {backup.name}")
    print("확인: python .\\07.scoring.py --summary")


if __name__ == "__main__":
    main()
