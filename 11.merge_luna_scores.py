"""
scores_luna_v2_t1.csv(사람 채점)를 scores_v2_t1.csv에 합친다.

사용법
    python .\\11.merge_luna_scores.py            # 미리보기 (파일 변경 없음)
    python .\\11.merge_luna_scores.py --apply    # 백업 후 추가

- 플래그 값 1/0은 07.scoring.py 형식(Y/빈칸)으로 바꿔서 넣는다.
- 아래 OVERRIDES에 값을 적으면 해당 칸만 바꿔서 넣는다 (Gemini와 기준을 맞출 때 사용).
  비워 두면 원본 파일 값 그대로 들어간다.
- 이미 luna 행이 있으면 멈춘다. (--force로 무시 가능)
"""
import argparse
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "scores_luna_v2_t1.csv"
DST = BASE / "scores_v2_t1.csv"

FLAG_COLS = ["risky_flag", "over_limit", "repeat_flag",
             "excluded_flag", "contradicted_flag", "facts_flag"]
TO_Y = {"1", "true", "yes", "y"}

# 기준 맞추기용 수정. 예:
#   ("q03", "D"): {"score": "1", "reason": "..."}      # 한 축의 점수·근거 변경
#   ("q03", "*"): {"risky_flag": "Y"}                  # 응답 전체(5개 축 행)의 플래그 변경
OVERRIDES = {
    ("q03", "D"): {"score": "1", "reason": "①로 내부 문제 특정은 적절하나, 2단계 로깅·syslog 설정 재확인이 '설정 정상' 단서와 겹치는 배제 조치 (Gemini q03과 동일 기준)"},
    ("q03", "*"): {"risky_flag": "Y"},
}


def read(path):
    raw = path.read_bytes()
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames or [], list(r), raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    src_h, src_rows, _ = read(SRC)
    dst_h, dst_rows, dst_raw = read(DST)

    missing = [c for c in dst_h if c not in src_h]
    if missing:
        sys.exit(f"[중단] 원본에 없는 열: {missing}")
    if any("luna" in r["model"].lower() for r in dst_rows) and not args.force:
        sys.exit("[중단] scores_v2_t1.csv에 이미 luna 행이 있습니다. 필요하면 --force")

    new_rows = []
    for r in src_rows:
        row = {h: r.get(h, "") for h in dst_h}
        for c in FLAG_COLS:
            row[c] = "Y" if row[c].strip().lower() in TO_Y else ""
        for key in [(row["qid"], "*"), (row["qid"], row["axis"])]:
            for col, val in OVERRIDES.get(key, {}).items():
                if col not in row:
                    sys.exit(f"[중단] OVERRIDES의 열 이름 오류: {col}")
                row[col] = val
        new_rows.append(row)

    # 미리보기
    by_q = {}
    for r in new_rows:
        by_q.setdefault(r["qid"], {})[r["axis"]] = int(r["score"])
    total = 0
    for q, ax in sorted(by_q.items()):
        s = sum(ax.values())
        total += s
        flags = [m for c, m in zip(FLAG_COLS, "RLXECF")
                 if any(x[c] == "Y" for x in new_rows if x["qid"] == q)]
        print(f"  {q}: " + " ".join(f"{a}{ax[a]}" for a in "ABCDE") + f" = {s}  {''.join(flags)}")
    print(f"  평균: {total / len(by_q):.1f} / 15   (추가될 행 {len(new_rows)}개)")
    if OVERRIDES:
        print(f"  수정 적용: {list(OVERRIDES)}")

    if not args.apply:
        print("\n미리보기입니다. 문제없으면 --apply를 붙여 실행하세요.")
        return

    backup = DST.with_name(f"{DST.name}.bak_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(DST, backup)
    needs_nl = dst_raw[-1:] not in (b"\n", b"")
    eol = "\r\n" if b"\r\n" in dst_raw[:4096] else "\n"
    with DST.open("a", encoding="utf-8", newline="") as f:
        if needs_nl:
            f.write(eol)
        csv.DictWriter(f, fieldnames=dst_h, lineterminator=eol).writerows(new_rows)
    print(f"\n추가 완료. 백업: {backup.name}")
    print("확인: python .\\07.scoring.py --summary")


if __name__ == "__main__":
    main()
