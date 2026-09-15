import csv
import statistics
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass


def out(msg=""):
    print(msg, flush=True)


CSV_PATH = "benchmark_luna.csv"

# gpt-5.6-luna 단가 (USD / 1M 토큰)
# 캐시된 입력은 $0.02이나, 매 호출이 독립적이라 적용되지 않음
PRICE_IN = 0.20 / 1_000_000
PRICE_OUT = 1.20 / 1_000_000


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


def stdev(vals):
    """1건이면 편차를 계산할 수 없으므로 None."""
    return statistics.stdev(vals) if len(vals) > 1 else None


out("Luna 리포트")

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
#   python 06.report.luna.py            → 가장 마지막 세션만
#   python 06.report.luna.py all        → 전체 세션
#   python 06.report.luna.py 0915-1423  → 특정 세션
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
else:
    out(f"전체 세션 {len(sessions)}개 합산")

if len(sessions) > 1 and target:
    others = [s for s in sessions if s != target]
    out(f"제외한 세션: {', '.join(others)}")

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

bar = "-" * 58

# ── 요약 ────────────────────────────────────────────────
tok = num(ok, "출력토큰", int)
chars = num(ok, "응답글자수", int)
sec = num(ok, "응답초")
tps = num(ok, "초당토큰")
over_rows = [r for r in ok if r.get("제약초과") == "Y"]

out("")
out("요약")
out(bar)
out(f"{'측정 건수':<16}{len(ok):>10}")
out(f"{'평균 출력토큰':<16}{statistics.mean(tok):>10.0f}")
out(f"{'출력 최소-최대':<16}{f'{min(tok)}-{max(tok)}':>10}")
if stdev(tok) is not None:
    out(f"{'출력 편차':<16}{stdev(tok):>10.0f}")
out(f"{'평균 글자수':<16}{statistics.mean(chars):>10.0f}")
out(f"{'글자수 최소-최대':<16}{f'{min(chars)}-{max(chars)}':>10}")
out(f"{'제약 초과':<16}{f'{len(over_rows)}/{len(ok)}':>10}")
out(f"{'평균 응답초':<16}{statistics.mean(sec):>10.1f}")
out(f"{'최장 응답초':<16}{max(sec):>10.1f}")
out(f"{'평균 tok/s':<16}{statistics.mean(tps):>10.1f}")
out(f"{'총 출력토큰':<16}{sum(tok):>10,}")
tok_in = num(ok, "입력토큰", int)
out(f"{'총 입력토큰':<16}{sum(tok_in):>10,}")

# ── 비용 ────────────────────────────────────────────────
cost_in = sum(tok_in) * PRICE_IN
cost_out = sum(tok) * PRICE_OUT
cost_total = cost_in + cost_out

out("")
out("비용 (USD)")
out(bar)
out(f"{'입력':<16}{f'${cost_in:.6f}':>14}  ({sum(tok_in):,} 토큰 x $0.20/1M)")
out(f"{'출력':<16}{f'${cost_out:.6f}':>14}  ({sum(tok):,} 토큰 x $1.20/1M)")
out(f"{'합계':<16}{f'${cost_total:.4f}':>14}")
out(f"{'호출당 평균':<16}{f'${cost_total / len(ok):.5f}':>14}")
out(f"{'출력 비중':<16}{f'{cost_out / cost_total * 100:.1f}%':>14}")
out(f"{'1,000회 환산':<16}{f'${cost_total / len(ok) * 1000:.2f}':>14}")

# ── 문제별 집계 (회차 평균) ─────────────────────────────
by_q = {}
for r in ok:
    by_q.setdefault(r.get("문제", ""), []).append(r)

out("")
out("문제별 집계 (회차 평균)")
out(bar)
out(f"{'문제':<7}{'회차':>5}{'토큰평균':>10}{'토큰편차':>9}"
    f"{'글자평균':>10}{'응답초':>9}{'초과':>6}")
out(bar)

for qid in sorted(by_q):
    qrows = by_q[qid]
    q_tok = num(qrows, "출력토큰", int)
    q_chr = num(qrows, "응답글자수", int)
    q_sec = num(qrows, "응답초")
    q_over = sum(1 for r in qrows if r.get("제약초과") == "Y")
    sd = stdev(q_tok)
    sd_txt = f"{sd:.0f}" if sd is not None else "-"

    out(f"{qid:<7}{len(qrows):>5}{statistics.mean(q_tok):>10.0f}{sd_txt:>9}"
        f"{statistics.mean(q_chr):>10.0f}{statistics.mean(q_sec):>9.1f}"
        f"{f'{q_over}/{len(qrows)}':>6}")

# ── 회차별 원자료 ───────────────────────────────────────
out("")
out("회차별 원자료")
out(bar)
out(f"{'문제':<8}{'회차':>5}{'출력토큰':>10}{'글자수':>10}{'응답초':>10}{'tok/s':>10}")
out(bar)


def run_key(r):
    v = str(r.get("회차", ""))
    return int(v) if v.isdigit() else 0


for r in sorted(ok, key=lambda x: (x.get("문제", ""), run_key(x))):
    out(f"{r['문제']:<8}{r.get('회차', ''):>5}{r['출력토큰']:>10}"
        f"{r['응답글자수']:>10}{r['응답초']:>10}{r['초당토큰']:>10}")

# ── 이상 행 ─────────────────────────────────────────────
if bad:
    out("")
    out("확인 필요")
    out(bar)
    for r in bad:
        why = (r.get("오류") or r.get("상태") or "")[:40]
        out(f"  {r.get('문제') or '-':<6}run{r.get('회차') or '-':<4}{why}")

if over_rows:
    out("")
    out(f"글자수 초과 ({len(over_rows)}건)")
    out(bar)
    for r in sorted(over_rows, key=lambda x: (x.get("문제", ""), run_key(x))):
        out(f"  {r['문제']:<6}run{r['회차']:<4}{r['응답글자수']}자")