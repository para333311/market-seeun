# -*- coding: utf-8 -*-
"""
주간백데이터 파일 재생성 도구

archive 폴더의 일별 파일(YYYY-MM-DD.txt)을 지정 기간만큼 합쳐서
주간백데이터 파일을 다시 만든다. 채널에서 현재 남아있는 글도 함께 회수한다.

사용법:
    python rebuild_weekly.py              → 현재 집계 창(화요일 기준)으로 재생성
    python rebuild_weekly.py 0804 0811    → 8/4 ~ 8/11 기간으로 재생성
"""

import os
import re
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import telegram_market_report as tmr


def parse_mmdd(token, year):
    return datetime.date(year, int(token[:2]), int(token[2:]))


def main():
    year = datetime.date.today().year

    if len(sys.argv) >= 3:
        start = parse_mmdd(sys.argv[1], year)
        end = parse_mmdd(sys.argv[2], year)
    else:
        start, end = tmr.weekly_window()

    out_name = f"{start.strftime('%m%d')}_{end.strftime('%m%d')}_주간백데이터.txt"
    out_path = os.path.join(tmr.ARCHIVE_DIR, out_name)

    print(f"[재생성] 기간: {start} ~ {end}")
    print(f"[대상] {out_path}")

    if not os.path.isdir(tmr.ARCHIVE_DIR):
        print("[오류] archive 폴더가 없습니다.")
        return 1

    # ── 1) 기간 내 일별 파일 수집 ──
    parts, used = [], []
    for name in sorted(os.listdir(tmr.ARCHIVE_DIR)):
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})\.txt$", name)
        if not m:
            continue
        try:
            d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if not (start <= d <= end):
            continue
        with open(os.path.join(tmr.ARCHIVE_DIR, name), encoding="utf-8") as f:
            body = f.read().strip()
        if body:
            parts.append(f"\n\n{'#'*70}\n# {d}\n{'#'*70}\n\n{body}")
            used.append(name)

    print(f"[수집] 일별 파일 {len(used)}개: {', '.join(used) if used else '없음'}")

    # ── 2) 채널에 남아있는 최신 글 회수 (누락분 보완) ──
    existing = "\n".join(parts)
    fresh = []
    for label, ch in tmr.ARCHIVE_CHANNELS:
        blocks = tmr._channel_blocks(ch)
        body = [b.strip() for b in blocks if len(b.strip()) >= 15 and b.strip() not in existing]
        if body:
            fresh.append(f"\n{'='*60}\n[{label}] @{ch}\n{'='*60}\n\n" + "\n\n---\n\n".join(body))
            print(f"[회수] {label}: {len(body)}건 추가")

    if fresh:
        today = datetime.date.today()
        parts.append(f"\n\n{'#'*70}\n# {today} (채널 회수분)\n{'#'*70}\n" + "".join(fresh))

    if not parts:
        print("[중단] 합칠 내용이 없습니다.")
        return 1

    # ── 3) 저장 ──
    header = (f"# 주간백데이터 {start.strftime('%m/%d')} ~ {end.strftime('%m/%d')}\n"
              f"# 재생성 시각: {datetime.datetime.now():%Y-%m-%d %H:%M}\n"
              f"# (내부 브리핑 작성용 참고자료 / 원문 인용 시 출처 표기)\n")

    if os.path.exists(out_path):
        backup = out_path.replace(".txt", "_backup.txt")
        os.replace(out_path, backup)
        print(f"[백업] 기존 파일 → {os.path.basename(backup)}")

    text = header + "".join(parts)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"\n[완료] {len(text):,}자 저장")
    print(f"        {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
