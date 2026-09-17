"""
scores_v2_t1.csv의 플래그 값을 07.scoring.py가 쓰는 형식으로 통일한다.

07.scoring.py는 플래그를 "Y"(해당) / ""(해당 없음)으로 기록하고 읽는다.
기존 행 대부분은 1/0으로 들어가 있어 --summary에 R·L·X·E·C·F 표시가 빠진다.

사용법
    python .\\10.normalize_flags.py            # 미리보기 (파일 변경 없음)
    python .\\10.normalize_flags.py --apply    # 백업 후 변환

변환 규칙: 1, true, yes → Y  /  0, false, no, n → 빈칸  /  Y와 빈칸은 그대로
그 밖의 값이 있으면 아무것도 바꾸지 않고 멈춘다.
"""
import argparse
import csv
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCORES = BASE / "scores_v2_t1.csv"
FLAG_COLS = ["risky_flag", "over_limit", "repeat_flag",
             "excluded_flag", "contradicted_flag", "facts_flag"]
TO_Y = {"1", "true", "yes", "y"}
TO_BLANK = {"0", "false", "no", "n", ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 변환")
    args = ap.parse_args()

    with SCORES.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)

    cols = [c for c in FLAG_COLS if c in header]
    if not cols:
        sys.exit("[중단] 플래그 열을 찾지 못했습니다.")

    before = {c: Counter(r[c] for r in rows) for c in cols}
    odd = {c: [v for v in before[c] if v.strip().lower() not in TO_Y | TO_BLANK] for c in cols}
    odd = {c: v for c, v in odd.items() if v}
    if odd:
        print("[중단] 알 수 없는 값이 있습니다:", odd)
        sys.exit(1)

    changed = 0
    for r in rows:
        for c in cols:
            v = r[c].strip().lower()
            new = "Y" if v in TO_Y else ""
            if r[c] != new:
                r[c] = new
                changed += 1

    print(f"대상 행 {len(rows)}개, 바뀌는 칸 {changed}개")
    for c in cols:
        after = Counter(r[c] for r in rows)
        print(f"  {c:18s} 변환 전 {dict(before[c])}  →  변환 후 {{'Y': {after.get('Y', 0)}, '': {after.get('', 0)}}}")

    # 모델별로 플래그가 붙는 응답 수 (model, qid, run 기준)
    print("\n모델별 플래그 응답 수 (변환 후)")
    for c in cols:
        hit = {(r["model"], r["qid"], r["run"]) for r in rows if r[c] == "Y"}
        print(f"  {c:18s}", dict(Counter(m for m, _, _ in hit)))

    if not args.apply:
        print("\n미리보기입니다. 문제없으면 --apply를 붙여 실행하세요.")
        return

    backup = SCORES.with_name(f"{SCORES.name}.bak_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(SCORES, backup)
    raw = SCORES.read_bytes()
    enc = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"   # 원본 BOM 유지
    eol = "\r\n" if b"\r\n" in raw[:4096] else "\n"                  # 원본 줄바꿈 유지
    with SCORES.open("w", encoding=enc, newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator=eol)
        w.writeheader()
        w.writerows(rows)
    print(f"\n변환 완료. 백업: {backup.name}")
    print("확인: python .\\07.scoring.py --summary")


if __name__ == "__main__":
    main()
