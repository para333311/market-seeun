# market-seeun — 세은 시황자동화

시장 브리핑 자동화 시스템. 산출물은 두 가지입니다.

1. **일간 텔레그램 브리핑** — 매일 06:30, `telegram_market_report.py`가 시세를 수집하고
   증권사 텔레그램 채널 7곳의 본문을 분석해 텔레그램 봇으로 2건(시황 데이터 / 마켓 코멘트)을
   나눠 발송합니다.
2. **주간 시황브리핑 docx** — 매주 화요일 15:00 이후, 주간 백데이터를
   `weekly-market-briefing` 스킬로 처리해 수요일 아침 회의 발표용 문서를 만듭니다.

> 상세한 배경·규칙·미해결 이슈는 [`CLAUDE.md`](CLAUDE.md)에 정리돼 있습니다.
> Claude Code가 매 세션 자동으로 읽습니다.

## ⚠️ 이 레포는 공개(public) 상태입니다

- 봇 토큰·채팅방 번호를 **코드나 문서에 적지 마세요.** `.env` 파일로만 관리합니다.
- 채널 원문이 담긴 백데이터·아카이브는 **사내 전용(대외 배포·인용 금지)** 이므로
  커밋하지 않습니다. `.gitignore`에 등록돼 있습니다.

## 최초 설정 (1회)

스크립트와 같은 폴더에 `.env` 파일을 만들고 값을 채웁니다.

```bash
cp .env.example .env
```

`.env` 내용:

```
TELEGRAM_BOT_TOKEN=봇_토큰
TELEGRAM_CHAT_ID_PERSONAL=개인_채팅방_번호
TELEGRAM_CHAT_ID_GROUP=그룹_채팅방_번호
```

값이 없으면 스크립트가 `[설정 오류]`를 남기고 바로 종료합니다.

## 실행

```bash
python telegram_market_report.py            # 일간 브리핑 발송
python telegram_market_report.py --force    # 시각·요일 조건 무시하고 강제 발송
python telegram_market_report.py --stats    # 누적 절감시간 리포트만 출력
python rebuild_weekly.py                    # 주간 백데이터 재생성 (현재 집계 창)
python rebuild_weekly.py 0804 0811          # 기간 지정 재생성
```

사용자 PC에서는 Windows 작업 스케줄러(`DailyMarketBrief`)가 매일 06:30에 자동 실행합니다.

## 주간 시황브리핑 만들기

집계 기준은 **지난주 화요일 15:00 ~ 이번주 화요일 15:00** 입니다.

1. 주간 백데이터 파일을 `backdata/` 폴더에 넣습니다.
2. Claude Code에 브리핑 생성을 요청합니다 (예: "이번 주 백데이터로 시황브리핑 만들어줘").
   `.claude/skills/weekly-market-briefing/` 스킬이 자동으로 적용됩니다.
3. 결과물은 `briefings/`에 저장됩니다. (커밋되지 않습니다)

스킬 빌더를 직접 쓰려면:

```bash
cd .claude/skills/weekly-market-briefing
npm install                                          # 최초 1회 (docx 패키지)
node scripts/build_briefing.js content.json out.docx
```

## 폴더 구조

```
market-seeun/
├── CLAUDE.md                  # 프로젝트 인수인계서 (매 세션 자동 로드)
├── telegram_market_report.py  # 일간 브리핑 메인 스크립트
├── rebuild_weekly.py          # 주간 백데이터 재생성 도구
├── .env.example               # 설정 예시 (.env는 커밋 안 됨)
├── .claude/skills/weekly-market-briefing/
│   ├── SKILL.md
│   ├── scripts/build_briefing.js
│   └── references/example_content.json
├── backdata/                  # 주간 백데이터 원본 (커밋 안 됨)
└── briefings/                 # 생성된 브리핑 결과물 (커밋 안 됨)
```

## 컴플라이언스

모든 리서치 콘텐츠는 **사내 참고용이며 대외 배포·인용을 금지**합니다.
애널리스트 개인 판단·전망·투자의견은 출처를 밝혀도 어떤 브리핑에도 넣지 않습니다.
자세한 내용은 `CLAUDE.md` 7절을 참조하세요.
