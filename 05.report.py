import csv
import statistics
import sys
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass


def out(msg=""):
    print(msg, flush=True)


CSV_PATH = "benchmark_local_v2.csv"
W = 15


def load(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def num(rows, key, cast=float):
    vals = []
    for r in rows or []:
        v = r.get(key, "")
        if v not in ("", None):
            try:
                vals.append(cast(v))
            except (ValueError, TypeError):
                pass
    return vals


def row_line(name, cells, width=W, pad=16):
    return f"{name:<{pad}}" + "".join(f"{c:>{width}}" for c in cells)


def fmt(vals, spec="{:.0f}"):
    return spec.format(statistics.mean(vals)) if vals else "-"


out("오픈소스 모델 리포트")

try:
    rows = load(CSV_PATH)
except FileNotFoundError:
    out(f"{CSV_PATH} 파일이 없습니다.")
    raise SystemExit(1)

if not rows:
    out(f"{CSV_PATH}에 기록이 없습니다.")
    raise SystemExit(1)

# ── 세션 선택 ───────────────────────────────────────────
# 사용법:
#   python 05.report.py            → 가장 마지막 세션만
#   python 05.report.py all        → 전체 세션
#   python 05.report.py 0915-1423  → 특정 세션
sessions = []
for r in rows:
    s = (r.get("세션") or "").strip()
    if s and s not in sessions:
        sessions.append(s)

arg = sys.argv[1].strip() if len(sys.argv) > 1 else ""

if arg.lower() == "all":
    target = None
elif arg:
    if arg not in sessions:
        out(f"세션 '{arg}'을(를) 찾을 수 없습니다.")
        out(f"기록된 세션: {', '.join(sessions) or '없음'}")
        raise SystemExit(1)
    target = arg
else:
    target = sessions[-1] if sessions else None

if target:
    rows = [r for r in rows if (r.get("세션") or "").strip() == target]
    out(f"세션 {target} (전체 {len(sessions)}개 중 1개)")
    if len(sessions) > 1:
        out(f"제외한 세션: {', '.join(s for s in sessions if s != target)}")
else:
    out(f"전체 세션 {len(sessions)}개 합산")

# ── 정상/제외 분류 ──────────────────────────────────────
ok, bad = [], []
for r in rows:
    tok_val = str(r.get("출력토큰", ""))
    if r.get("상태") == "정상" and tok_val.isdigit() and int(tok_val) > 0:
        ok.append(r)
    else:
        bad.append(r)

out(f"정상 {len(ok)}건 / 제외 {len(bad)}건")

if not ok:
    out("집계할 정상 기록이 없습니다.")
    raise SystemExit(1)

labels = sorted({r.get("모델", "") for r in ok})
qids = sorted({r.get("문제", "") for r in ok})

by_model = {l: [r for r in ok if r.get("모델", "") == l] for l in labels}
cell = defaultdict(list)
for r in ok:
    cell[(r.get("문제", ""), r.get("모델", ""))].append(r)

bar = "-" * (16 + W * len(labels))

# ── 지표 비교 ────────────────────────────────────────────
out("")
out(f"{'':16}" + "".join(f"{l:>{W}}" for l in labels))
out(bar)

metrics = [
    ("측정 건수",     lambda rs: f"{len(rs)}"),
    ("평균 출력토큰",  lambda rs: fmt(num(rs, "출력토큰", int))),
    ("최소-최대",     lambda rs: (f"{min(num(rs, '출력토큰', int))}-"
                               f"{max(num(rs, '출력토큰', int))}")
                               if num(rs, "출력토큰", int) else "-"),
    ("출력 편차",     lambda rs: (f"{statistics.stdev(num(rs, '출력토큰', int)):.0f}"
                               if len(num(rs, "출력토큰", int)) > 1 else "-")),
    ("평균 글자수",   lambda rs: fmt(num(rs, "응답글자수", int))),
    ("제약 초과",     lambda rs: f"{sum(1 for r in rs if r.get('제약초과') == 'Y')}/{len(rs)}"),
    ("평균 응답초",   lambda rs: fmt(num(rs, "응답초"), "{:.1f}")),
    ("최장 응답초",   lambda rs: (f"{max(num(rs, '응답초')):.1f}"
                              if num(rs, "응답초") else "-")),
    ("평균 tok/s",   lambda rs: fmt(num(rs, "초당토큰"), "{:.1f}")),
    ("잘림 건수",     lambda rs: f"{sum(1 for r in rs if r.get('종료사유') == '토큰한도')}"),
    ("총 출력토큰",   lambda rs: (f"{sum(num(rs, '출력토큰', int)):,}"
                              if num(rs, "출력토큰", int) else "-")),
]

for name, fn in metrics:
    out(row_line(name, [fn(by_model[l]) for l in labels]))

# ── 문제별 표 ───────────────────────────────────────────
views = [
    ("문제별 출력토큰", "출력토큰",   int,   "{:.0f}"),
    ("문제별 글자수",  "응답글자수", int,   "{:.0f}"),
    ("문제별 응답초",  "응답초",    float, "{:.1f}"),
]

for title, key, cast, spec in views:
    out("")
    out(f"{title:16}" + "".join(f"{l:>{W}}" for l in labels))
    out(bar)
    for qid in qids:
        cells = []
        for l in labels:
            rs = cell.get((qid, l))
            cells.append(fmt(num(rs, key, cast), spec) if rs else "-")
        out(row_line(qid, cells))

# ── 회차 수 (셀별 집계 건수) ────────────────────────────
counts = {(q, l): len(cell.get((q, l), [])) for q in qids for l in labels}
if len(set(counts.values())) > 1:
    out("")
    out(f"{'문제별 회차수':16}" + "".join(f"{l:>{W}}" for l in labels))
    out(bar)
    for qid in qids:
        out(row_line(qid, [str(counts[(qid, l)]) for l in labels]))
    out("  주의: 회차 수가 셀마다 다릅니다. 평균 비교 시 감안하세요.")

# ── 회차 편차 ───────────────────────────────────────────
if any(len(cell.get((q, l), [])) > 1 for q in qids for l in labels):
    out("")
    out(f"{'문제별 회차편차':16}" + "".join(f"{l:>{W}}" for l in labels))
    out(bar)
    for qid in qids:
        cells = []
        for l in labels:
            vals = num(cell.get((qid, l), []), "출력토큰", int)
            cells.append(f"+-{statistics.stdev(vals):.0f}" if len(vals) > 1 else "-")
        out(row_line(qid, cells))

# ── 이상 행 ─────────────────────────────────────────────
if bad:
    out("")
    out("확인 필요")
    out(bar)
    for r in bad:
        why = (r.get("오류") or r.get("상태") or "")[:40]
        out(f"  {r.get('문제') or '-':<5}{r.get('모델', ''):<14}"
            f"run{r.get('회차') or '-':<4}{why}")

cut_rows = [r for r in ok if r.get("종료사유") == "토큰한도"]
if cut_rows:
    out("")
    out("잘린 응답")
    out(bar)
    for r in cut_rows:
        out(f"  {r['문제']:<5}{r['모델']:<14}run{r['회차']:<4}{r.get('원문경로', '')}")

over_rows = [r for r in ok if r.get("제약초과") == "Y"]
if over_rows:
    out("")
    out("글자수 초과")
    out(bar)
    for r in over_rows:
        out(f"  {r['문제']:<5}{r['모델']:<14}run{r['회차']:<4}"
            f"{r['응답글자수']}자")

out("")
out(f"집계 {len(ok)}건 / 모델 {len(labels)}종")
out("")