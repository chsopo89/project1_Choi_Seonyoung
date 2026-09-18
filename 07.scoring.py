"""
07.scoring.py — 모델 응답 채점 보조 (LLM 미사용)

스크립트는 표시만 하고, 점수는 사람이 입력한다.
  - 자동 표시: 글자수, 명령어 추출·판정, 배제 조치/위험 조치 키워드, 반복·언어 혼입
  - 사람 입력: 축별 점수(0~3)와 근거

[변경] 2026-09-16 오후 (temperature 1.0 + seed 43~45, 3회 반복 대응)
  - --csv    : 이 CSV의 '원문경로'에 있는 응답만 채점 (기본 benchmark_local_v2.csv, none=필터 해제)
  - --scores : 점수 저장 파일 (기본 scores_v2_t1.csv, 아침 temperature 0 점수와 분리)
  - --summary: 회차별 총점의 평균(최소~최대)과 회차 수를 표시
  - A축 명령어 등록 질문은 기본으로 끔 (필요하면 --ask-commands)

[변경] 2026-09-17 (장비별 명령어 판정)
  - verified_commands.json 항목에 vendor 추가 (fortigate / screenos / junos / cisco / any)
    vendor가 없는 항목은 any(장비 무관)로 취급
    같은 패턴을 여러 장비에 등록할 때는 값을 항목 목록으로 저장
  - 문항의 vendors(answer_keys.py)에 해당하는 항목만 판정에 사용
    다른 장비 항목에만 걸리면 ⇄(다른 장비 명령)로 표시
    여러 장비 문항에서 판정이 갈리면 ±로 표시
  - --ask-commands 등록 시 장비도 입력 (문항 장비가 하나면 자동)
  - 외국 문자 검사: 키릴·한자만 보던 것을 한글·라틴 이외의 모든 문자로 확대
    (벵골·그리스·일본 가나 등). 문자 계열별 개수와 예시를 표시

사용 예
  python .\\07.scoring.py --list
  python .\\07.scoring.py --axis A --questions q01
  python .\\07.scoring.py --axis D --questions q01 --models qwen3:8b
  python .\\07.scoring.py --axis C --questions q01 --redo
  python .\\07.scoring.py --check --questions q01      # 자동 표시만 보기 (입력 없음)
  python .\\07.scoring.py --summary
"""
import argparse
import csv
import json
import random
import re
import sys
import unicodedata
import zlib
from collections import Counter
from datetime import datetime
from pathlib import Path

from answer_keys import (ANSWER_KEYS, RUBRIC, RUBRIC_VERSION, A_CAP_NO_COMMANDS, CHAR_LIMIT,
                         VENDOR_NAMES)

BASE = Path(__file__).resolve().parent
RESP_DIRS = {
    BASE / "responses": None,
    BASE / "responses_luna": "luna",
    BASE / "responses_gemini": "gemini",
}
VERIFIED = BASE / "verified_commands.json"
SCORES = BASE / "scores_v2_t1.csv"   # main()에서 --scores 값으로 바뀜
AXES = ["A", "B", "C", "D", "E"]
ASK_COMMANDS = False   # True면 A축 채점 중 미등록 명령어 판정을 물어봄 (--ask-commands)

MODELS = ["llama3.1:8b", "qwen3:8b", "gemma3:12b", "gemma3:4b", "gemini"]

VERDICT_MARK = {"ok": "✔", "wrong": "✘", "partial": "△",
                "othervendor": "⇄", "mixed": "±", "unknown": "?"}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------- 응답 찾기
def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def parse_name(path, default_model=None):
    name = path.stem
    qid = re.search(r"q\d{2}", name)
    session = re.search(r"\d{4}-\d{4}", name)
    run = re.search(r"run[_-]?(\d+)", name)
    model = None
    for m in sorted(MODELS, key=len, reverse=True):
        if norm(m) in norm(name):
            model = m
            break
    model = model or default_model
    if not (qid and model):
        return None
    return {
        "path": path,
        "qid": qid.group(0),
        "model": model,
        "session": session.group(0) if session else "-",
        "run": run.group(1) if run else "1",
    }


# 벤치마크 CSV에 기록된 응답만 허용
def load_allowed(csv_arg):
    if csv_arg.lower() == "none":
        return None
    path = Path(csv_arg)
    if not path.is_absolute():
        path = BASE / path
    if not path.exists():
        sys.exit(f"CSV를 찾지 못함: {path}\n필터 없이 보려면 --csv none")
    allowed = set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rel = (row.get("원문경로") or "").strip()
            if rel and row.get("상태", "정상") == "정상":
                allowed.add((BASE / rel).resolve())
    print(f"[필터] {path.name} 기준 응답 {len(allowed)}건")
    return allowed


def find_responses(questions, sessions, models, allowed=None):
    items = []
    paths = []
    for d, default_model in RESP_DIRS.items():
        if d.exists():
            paths += [(p, default_model) for p in sorted(d.rglob("*"))]
    for p, default_model in paths:
        if not p.is_file() or p.suffix.lower() not in (".txt", ".md"):
            continue
        if allowed is not None and p.resolve() not in allowed:
            continue
        info = parse_name(p, default_model)
        if not info:
            continue
        if questions and info["qid"] not in questions:
            continue
        if sessions and info["session"] not in sessions:
            continue
        if models and info["model"] not in models:
            continue
        info["text"] = p.read_text(encoding="utf-8", errors="replace")
        items.append(info)
    return items


# ---------------------------------------------------------------- 자동 표시
CMD_PREFIX = r"(?:show|diagnose|diag|get|execute|config|set|debug|clear)\b"
CMD_RE = re.compile(r"`([^`\n]{2,120})`|^\s*(?:[-*]|\d+\.)?\s*(" + CMD_PREFIX + r"[^\n]{0,120})$", re.M)


def extract_commands(text):
    found = set()
    for a, b in CMD_RE.findall(text):
        c = (a or b).strip().rstrip(".,")
        if a and not re.match(CMD_PREFIX, c):
            if not c[:1].islower():
                continue
            if " " not in c and not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+", c):
                continue
        found.add(c)
    return sorted(found)


def entries_of(value):
    """등록 값은 항목 하나(dict) 또는 여러 장비 항목 목록(list)"""
    return value if isinstance(value, list) else [value]


def entry_vendor(entry):
    return entry.get("vendor") or "any"


def load_verified():
    if not VERIFIED.exists():
        return {}
    data = json.loads(VERIFIED.read_text(encoding="utf-8"))
    for pat, value in data.items():
        for e in entries_of(value):
            v = entry_vendor(e)
            if v not in VENDOR_NAMES:
                print(f"  ⚠ verified_commands.json '{pat}': 알 수 없는 vendor '{v}'")
    return data


def save_verified(data):
    VERIFIED.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_entry(verified, pattern, entry):
    """같은 장비 항목은 교체, 다른 장비 항목은 유지"""
    cur = verified.get(pattern)
    if cur is None:
        verified[pattern] = entry
        return
    ents = [e for e in entries_of(cur) if entry_vendor(e) != entry_vendor(entry)]
    ents.append(entry)
    verified[pattern] = ents[0] if len(ents) == 1 else ents


def in_scope(entry, vendors):
    v = entry_vendor(entry)
    return v == "any" or not vendors or v in vendors


def classify(cmd, verified, vendors=None):
    """반환: (판정, 걸린 패턴, 장비 표기)"""
    other = None
    for pat in sorted(verified, key=len, reverse=True):
        if pat not in cmd:
            continue
        ents = entries_of(verified[pat])
        scoped = [e for e in ents if in_scope(e, vendors)]
        if scoped:
            verdicts = {e["verdict"] for e in scoped}
            verdict = verdicts.pop() if len(verdicts) == 1 else "mixed"
            label = "/".join(sorted({entry_vendor(e) for e in scoped}))
            return verdict, pat, label
        if other is None:
            other = (pat, "/".join(sorted({entry_vendor(e) for e in ents})))
    if other:
        return "othervendor", other[0], other[1]
    return "unknown", None, ""


def foreign_letters(text):
    """한글·라틴 이외의 글자를 문자 계열별로 센다. 반환: {계열: (개수, 예시)}"""
    counts, samples = Counter(), {}
    for ch in text:
        if not ch.isalpha() or ch.isascii():
            continue
        name = unicodedata.name(ch, "")
        if name.startswith(("HANGUL", "LATIN")):
            continue
        script = "한자" if name.startswith("CJK") else (name.split()[0] if name else "알 수 없음")
        counts[script] += 1
        if len(samples.get(script, "")) < 8 and ch not in samples.get(script, ""):
            samples[script] = samples.get(script, "") + ch
    return {k: (n, samples[k]) for k, n in counts.most_common()}


def keyword_lines(text, groups):
    hits = []
    lines = text.splitlines()
    for g in groups:
        for i, line in enumerate(lines, 1):
            if any(k in line for k in g["keywords"]):
                hits.append((g["id"], i, line.strip()[:120]))
    return hits


def auto_report(item, verified):
    text = item["text"]
    key = ANSWER_KEYS.get(item["qid"], {})
    vendors = key.get("vendors")
    cmds = [(c, *classify(c, verified, vendors)) for c in extract_commands(text)]
    top_line, top_count = ("", 0)
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 10]
    if lines:
        top_line, top_count = Counter(lines).most_common(1)[0]
    return {
        "chars": len(text),
        "over_limit": len(text) > CHAR_LIMIT,
        "vendors": vendors or [],
        "commands": cmds,
        "excluded": keyword_lines(text, key.get("excluded", [])),
        "contradicted": keyword_lines(text, key.get("contradicted", [])),
        "risky": keyword_lines(text, key.get("risky", [])),
        "facts": keyword_lines(text, key.get("facts_wrong", [])),
        "check": keyword_lines(text, key.get("facts_check", [])),
        "foreign": foreign_letters(text),
        "repeat": (top_count, top_line[:80]) if top_count >= 5 else None,
    }


def print_report(r, axis=None):
    show = lambda ax: axis is None or axis == ax
    print(f"  글자수 {r['chars']:,}" + ("  ⚠ 3000자 초과" if r["over_limit"] else ""))
    if show("A"):
        multi = len(r["vendors"]) > 1
        print(f"  명령어 {len(r['commands'])}개  (문항 장비: {'/'.join(r['vendors']) or '미지정'})")
        for c, verdict, pat, vendor in r["commands"]:
            line = f"    {VERDICT_MARK.get(verdict, '?')} {c}"
            if pat and pat != c:
                line += f"   (← {pat})"
            if verdict == "othervendor":
                line += f"   다른 장비 명령 [{vendor}]"
            elif verdict == "mixed":
                line += f"   장비별 판정 다름 [{vendor}]"
            elif multi and vendor:
                line += f"   [{vendor}]"
            print(line)
        for gid, ln, line in r["facts"]:
            print(f"  [틀린 사실:{gid}] {ln}행: {line}")
        for gid, ln, line in r["check"]:
            print(f"  [확인 필요 사실:{gid}] {ln}행: {line}")
        if not r["commands"] and not r["facts"] and not r["check"]:
            cap = A_CAP_NO_COMMANDS
            print("    검증 대상 없음" + (f" → A 상한 {cap}" if cap is not None else " → A 상한 규칙 미결정"))
    if show("D"):
        for title, key in (("배제 조치 언급", "excluded"), ("단서와 안 맞는 원인", "contradicted")):
            for gid, ln, line in r[key]:
                note = "  (상황 설명일 수 있음)" if key == "excluded" and "정상" in line else ""
                print(f"  [{title}:{gid}] {ln}행: {line}{note}")
    for gid, ln, line in r["risky"]:
        print(f"  [위험 조치:{gid}] {ln}행: {line}")
    if show("E") or show("C"):
        for script, (n, sample) in r["foreign"].items():
            print(f"  ⚠ 외국 문자 혼입: {script} {n}자 ({sample})")
        if r["repeat"]:
            print(f"  ⚠ 같은 줄 {r['repeat'][0]}회 반복: {r['repeat'][1]}")


# ---------------------------------------------------------------- 점수 저장
FIELDS = [
    "session", "model", "qid", "run", "axis", "score", "reason",
    "risky_flag", "over_limit", "repeat_flag", "excluded_flag",
    "contradicted_flag", "facts_flag", "rubric", "scored_at",
]

FLAG_MARKS = [
    ("risky_flag", "R"), ("over_limit", "L"), ("repeat_flag", "X"),
    ("excluded_flag", "E"), ("contradicted_flag", "C"), ("facts_flag", "F"),
]


def load_scores():
    if not SCORES.exists() or SCORES.stat().st_size == 0:
        return []
    with SCORES.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def append_score(row):
    new = not SCORES.exists() or SCORES.stat().st_size == 0
    with SCORES.open("a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def done_keys(rows):
    return {(r["session"], r["model"], r["qid"], r["run"], r["axis"]) for r in rows}


# ---------------------------------------------------------------- 입력
def safe_input(prompt):
    try:
        return input(prompt)
    except EOFError:
        return "q"


def ask_vendor(vendors):
    if vendors and len(vendors) == 1:
        return vendors[0]
    choices = list(vendors or []) + ["any"]
    while True:
        v = safe_input(f"      장비 [{' / '.join(choices)}]: ").strip().lower()
        if v in choices or (not vendors and v in VENDOR_NAMES):
            return v


def ask_unknown_commands(report, verified):
    changed = False
    for c, verdict, _, _ in report["commands"]:
        if verdict != "unknown":
            continue
        ans = safe_input(f"    미등록 명령 '{c}' 판정 [o=ok / x=wrong / p=partial / Enter=건너뜀]: ").strip().lower()
        if ans not in ("o", "x", "p"):
            continue
        pattern = safe_input("      등록할 패턴 (Enter=그대로): ").strip() or c
        vendor = ask_vendor(report["vendors"])
        source = safe_input("      출처 (문서명 > 항목): ").strip()
        add_entry(verified, pattern, {
            "verdict": {"o": "ok", "x": "wrong", "p": "partial"}[ans],
            "vendor": vendor,
            "source": source,
            "checked_at": datetime.now().strftime("%Y-%m-%d"),
        })
        changed = True
    if changed:
        save_verified(verified)
        print("    → verified_commands.json 저장됨")
    return changed


def ask_score(axis):
    while True:
        s = safe_input(f"  {axis} 점수 0~3 (s=건너뜀, q=종료): ").strip().lower()
        if s in ("s", "q"):
            return s, ""
        if s in ("0", "1", "2", "3"):
            reason = ""
            while not reason:
                reason = safe_input("  근거 한 줄: ").strip()
            return s, reason


def score_axis(items, axis, seed, redo=False):
    verified = load_verified()
    done = set() if redo else done_keys(load_scores())
    todo = [it for it in items
            if (it["session"], it["model"], it["qid"], it["run"], axis) not in done]
    random.Random(seed).shuffle(todo)
    name, guide = RUBRIC[axis]
    print(f"\n=== {axis}축 {name} / 남은 응답 {len(todo)}건 ===\n기준: {guide}\n")
    for n, it in enumerate(todo, 1):
        print("=" * 70)
        print(f"[{n}/{len(todo)}] {it['qid']} / 응답 #{zlib.crc32(it['path'].name.encode()) % 1000:03d}")
        print("-" * 70)
        print(it["text"])
        print("-" * 70)
        report = auto_report(it, verified)
        print_report(report, axis)
        # 명령어 등록 질문은 --ask-commands를 줄 때만 표시
        if axis == "A" and ASK_COMMANDS and ask_unknown_commands(report, verified):
            report = auto_report(it, verified)
            print_report(report, "A")
        s, reason = ask_score(axis)
        if s == "q":
            break
        if s == "s":
            continue

        append_score({
            "session": it["session"],
            "model": it["model"],
            "qid": it["qid"],
            "run": it["run"],
            "axis": axis,
            "score": s,
            "reason": reason,
            "risky_flag": "Y" if report["risky"] else "",
            "over_limit": "Y" if report["over_limit"] else "",
            "repeat_flag": "Y" if report["repeat"] else "",
            "excluded_flag": "Y" if report["excluded"] else "",
            "contradicted_flag": "Y" if report["contradicted"] else "",
            "facts_flag": "Y" if report["facts"] else "",
            "rubric": RUBRIC_VERSION,
            "scored_at": datetime.now().isoformat(timespec="seconds"),
        })
    print("\n저장 위치:", SCORES)


# ---------------------------------------------------------------- 요약
# 회차(run)별 총점을 따로 계산한 뒤 평균(최소~최대)으로 표시
def summary(sessions=None):
    rows = [r for r in load_scores() if r["rubric"] == RUBRIC_VERSION]
    if sessions:
        rows = [r for r in rows if r["session"] in sessions]

    latest = {}   # --redo로 다시 채점한 경우 마지막 값 적용
    for r in rows:
        latest[(r["session"], r["model"], r["qid"], r["run"], r["axis"])] = r
    if not latest:
        print(f"채점 기록 없음 ({SCORES.name})")
        return

    runs = {}    # (qid, model) -> {(session, run): {axis: score}}
    flags = {}   # (qid, model) -> 표시 기호 집합
    for (s, m, q, run, a), r in latest.items():
        runs.setdefault((q, m), {}).setdefault((s, run), {})[a] = int(r["score"])
        fs = flags.setdefault((q, m), set())
        for col, mark in FLAG_MARKS:
            if r.get(col) == "Y":
                fs.add(mark)

    qids = sorted({k[0] for k in runs})
    models = sorted({k[1] for k in runs})
    W = 22

    print(f"\n[문항별 총점] 채점표 {RUBRIC_VERSION} / {SCORES.name}")
    print("  표기: 평균(최소~최대) n=완료 회차 수 / 총점 만점 15")
    print("  * 5축 미완료 회차 있음, ! A=0 관문, R 위험 조치, L 길이, X 반복, E 배제, C 모순, F 사실오류")
    print("문항  " + "".join(f"{m:>{W}}" for m in models))

    model_totals = {m: [] for m in models}
    for q in qids:
        cells = []
        for m in models:
            rr = runs.get((q, m))
            if not rr:
                cells.append(f"{'-':>{W}}")
                continue
            totals = [sum(v.values()) for v in rr.values() if len(v) == 5]
            model_totals[m] += totals
            mark = ""
            if any(len(v) != 5 for v in rr.values()):
                mark += "*"
            if any(v.get("A") == 0 for v in rr.values()):
                mark += "!"
            mark += "".join(x for _, x in FLAG_MARKS if x in flags[(q, m)])
            if totals:
                avg = sum(totals) / len(totals)
                cell = f"{avg:.1f}({min(totals)}~{max(totals)})n{len(totals)}{mark}"
            else:
                cell = f"-{mark}"
            cells.append(f"{cell:>{W}}")
        print(f"{q:<6}" + "".join(cells))

    print("\n[모델 전체 평균 총점] (5축 완료 회차만)")
    for m in models:
        t = model_totals[m]
        print(f"  {m:<14} " + (f"{sum(t) / len(t):.2f}  (n={len(t)})" if t else "-"))

    print("\n[축별 평균] (모든 문항·회차)")
    print("축    " + "".join(f"{m:>{W}}" for m in models))
    for a in AXES:
        cells = []
        for m in models:
            vals = [v[a] for (q, mm), rr in runs.items() if mm == m
                    for v in rr.values() if a in v]
            cells.append(f"{(sum(vals) / len(vals)):>{W}.2f}" if vals else f"{'-':>{W}}")
        print(f"{a:<6}" + "".join(cells))


# ---------------------------------------------------------------- main
def main():
    global SCORES, ASK_COMMANDS
    ap = argparse.ArgumentParser()
    ap.add_argument("--axis", choices=AXES)
    ap.add_argument("--questions", nargs="*")
    ap.add_argument("--sessions", nargs="*")
    ap.add_argument("--models", nargs="*")
    ap.add_argument("--csv", default="benchmark_local_v2.csv",
                    help="이 CSV의 원문경로에 있는 응답만 대상 (none=필터 해제)")
    ap.add_argument("--scores", default="scores_v2_t1.csv", help="점수 저장 파일")
    ap.add_argument("--seed", type=int, default=7, help="응답 순서 섞기용")
    ap.add_argument("--list", action="store_true", help="찾은 응답 파일 목록")
    ap.add_argument("--check", action="store_true", help="자동 표시만 출력")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--redo", action="store_true", help="이미 채점한 항목도 다시 채점 (마지막 입력값이 적용됨)")
    ap.add_argument("--ask-commands", action="store_true", help="A축 채점 중 미등록 명령어 판정을 물어봄")
    args = ap.parse_args()
    ASK_COMMANDS = args.ask_commands

    SCORES = Path(args.scores)
    if not SCORES.is_absolute():
        SCORES = BASE / SCORES

    for q, k in ANSWER_KEYS.items():
        bad = set(k.get("vendors", [])) - VENDOR_NAMES
        if bad:
            print(f"  ⚠ answer_keys.py {q}: 알 수 없는 vendors {sorted(bad)}")

    if args.summary:
        summary(args.sessions)
        return

    allowed = load_allowed(args.csv)
    items = find_responses(args.questions, args.sessions, args.models, allowed)
    if not items:
        print(f"응답 파일을 찾지 못함: {[str(d) for d in RESP_DIRS]}\n"
              f"파일명 규칙이 다르면 parse_name()을 수정하세요.")
        return

    if args.list:
        for it in items:
            print(f"{it['session']:>10}  {it['model']:<14} {it['qid']}  run{it['run']}  {it['path'].name}")
        by_model = Counter(it["model"] for it in items)
        print(f"총 {len(items)}건  " + " / ".join(f"{m} {n}" for m, n in sorted(by_model.items())))
        return

    if args.check:
        verified = load_verified()
        for it in items:
            print("=" * 70)
            print(f"{it['session']} / {it['model']} / {it['qid']} / run{it['run']}")
            print_report(auto_report(it, verified))
        return

    if not args.axis:
        ap.error("--axis 를 지정하세요 (또는 --list / --check / --summary)")
    score_axis(items, args.axis, args.seed, args.redo)


if __name__ == "__main__":
    main()