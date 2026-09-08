# 시황 자동화 프로젝트 인수인계서 (Claude Code 이관용)

> 이 문서는 claude.ai 프로젝트에서 Claude Code 레포로 이관하기 위한 완전 인수인계서다.
> **레포 루트에 `CLAUDE.md`로 두면 Claude Code가 매 세션 자동으로 읽는다.**
> 마지막 갱신: 2026-09-08. 이 문서 하나로 지금까지의 모든 맥락·규칙·미해결 이슈를 파악할 수 있어야 한다.

---

## 0. 프로젝트가 무엇인가 (30초 요약)

SK증권 영업점 소속 사용자가 운영하는 **시장 브리핑 자동화 시스템**. 산출물은 두 가지.

1. **일간 텔레그램 브리핑** — 매일 06:30, `telegram_market_report.py`가 시세 수집 + 증권사 텔레그램 채널 7곳 본문 분석 → 텔레그램 봇으로 2건 분리 발송 (📊 데일리 시황 / 🧭 마켓 코멘트).
2. **주간 시황브리핑 docx** — 매주 화요일 15:00 이후, 주간 백데이터 txt를 `weekly-market-briefing` 스킬로 처리 → 수요일 아침 회의 **2분 내외** 구두 발표용 문서(+ 화면 투사용 PDF).

부수: 일간·주간 결과물의 개인메일 발송(예약 작업, **현재 고장**), Axtival 사내 공모전 — **2026-09-08 접수 완료**(10절).

외부 AI API 미사용(비용 0원). 모든 리서치 콘텐츠는 **사내 참고용, 대외 배포·인용 금지**.

---

## 1. 사용자 응대 규칙 (필수 — 매 응답에 적용)

- 사용자는 **파이썬 비전문가**. 코드 수정은 Claude가 직접 하고 완성된 파일을 제공한다. 폴더 접근 권한이 있으면 `C:\Telegram Desktop\`에 **직접 덮어쓴다** (덮어쓰기 전 원본을 `_backup_MMDD.py`로 백업).
- 사용자에게 코드 편집·검색·확인 작업을 시키지 않는다. Claude가 할 수 있는 일은 전부 Claude가 한다.
- 작업 시작 전 **항상 최신 상태부터 확인**한다 (파일·로그·이전 변경사항). 추측으로 진행하지 않는다.
- 안내는 **한 번에 2단계까지만**. 메뉴 경로 안내("어디 가서 뭘 누르고…")는 피한다.
- 클릭할 곳은 직접 하이퍼링크, 입력할 내용은 완성형 코드 블록(복사 버튼).
- 선택지가 여럿이면 가장 적합한 하나를 먼저 추천한다. 질문은 정말 필요할 때만, 한 번에 모아서.
- 항상 **존댓말(격식체)**.

---

## 2. 실행 환경 (사용자 PC)

| 항목 | 값 |
|---|---|
| 작업 폴더 | `C:\Telegram Desktop\` |
| 메인 스크립트 | `telegram_market_report.py` |
| 주간파일 재생성 도구 | `rebuild_weekly.py` |
| 아카이브 폴더 | `C:\Telegram Desktop\archive\` |
| 발송본 보관 | `C:\Telegram Desktop\archive\brief\YYYY-MM-DD_브리핑.txt` (`save_sent_brief()`) |
| 로그 | `C:\Telegram Desktop\log.txt` |
| Axtival 자료 | `C:\Telegram Desktop\Axtival\` |
| 파이썬 경로 | `C:\Users\jse09\AppData\Local\Programs\Python\Python313\python.exe` |
| 작업 스케줄러 | 작업명 `DailyMarketBrief`, 매일 06:30 |

**주의**: `WindowsApps\python.exe`는 스토어 껍데기라 스케줄러에서 실패한다. 반드시 `Python313` 절대경로.

스케줄 재등록 (관리자 PowerShell):

```powershell
$py = "C:\Users\jse09\AppData\Local\Programs\Python\Python313\python.exe"
$act = New-ScheduledTaskAction -Execute $py -Argument "telegram_market_report.py" -WorkingDirectory "C:\Telegram Desktop"
$trg = New-ScheduledTaskTrigger -Daily -At 6:30AM
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
Register-ScheduledTask -TaskName "DailyMarketBrief" -Action $act -Trigger $trg -Settings $set -User $env:USERNAME -Force
```

로그 확인 / 수동 실행 / 강제 실행:

```powershell
Get-Content "C:\Telegram Desktop\log.txt" -Tail 40 -Encoding UTF8
```
```powershell
python telegram_market_report.py
```
```powershell
python telegram_market_report.py --force
```

---

## 3. 텔레그램 봇 · 발송 대상

- 봇: `J_dailybriefing_Bot` (표시명: J의 일간시황브리핑).
- **⚠️ 이 레포는 공개(public) 상태다. 토큰·채팅방 번호를 코드나 문서에 적지 않는다.**
  2026-08-26 이관 시 하드코딩을 제거하고 스크립트 옆 `.env` 파일에서 읽도록 변경했다
  (`load_local_env()`, 외부 패키지 불필요). `.env`는 `.gitignore` 등록. 작성법은 `.env.example` 참조.

```
# .env (깃에 올리지 않음)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID_PERSONAL=...
TELEGRAM_CHAT_ID_GROUP=...
```

- 발송 대상은 `CHAT_TARGETS` 리스트로 관리. **대상별로 어떤 메시지를 받을지 개별 지정.**
  `chat_id`는 위 환경변수에서 읽으며, 값이 비어 있는 대상은 발송에서 자동 제외된다.

```python
CHAT_TARGETS = [
    {"name": "개인 채팅",        "chat_id": os.environ.get("TELEGRAM_CHAT_ID_PERSONAL", ""), "send_market": True, "send_comment": True},
    {"name": "그룹 J의 시황정보", "chat_id": os.environ.get("TELEGRAM_CHAT_ID_GROUP", ""),    "send_market": True, "send_comment": True},
]
```

- 실행 시 `check_credentials()`가 값 누락을 먼저 확인하고, 없으면 안내 후 종료한다(재시도 없음).

- 2026-08-19 사용자 확인: **두 방 모두 사내용, 외부 유출 위험 없음** → 그룹방 발송 재개. (그 전에는 그룹 발송 중단 상태였음)
- 그룹에서 코멘트만 빼려면 해당 줄 `send_comment`를 `False`로.

---

## 4. 일간 브리핑 (매일 06:30, 하루 2건 분리 발송)

### 4-1. 발송 조건

```python
SKIP_WEEKEND = True      # 토·일 발송 안 함
SCHEDULED_HOUR = 6
SCHEDULED_MINUTE = 30
MAX_DELAY_HOURS = 6      # 12:30 이후 실행되면 발송 생략
```

- 지연 발송 금지 장치는 "8/8(토) 시황이 8/11(화)에 도착"하던 사고 방지용.
- 06:30인 이유: 미국장 마감(05:00 KST, 서머타임)과의 여유 확보. 06:00→06:30 조정(2026-08-11).

### 4-2. 데이터 기준 시점

| 항목 | 기준 |
|---|---|
| KOSPI / KOSDAQ | 전일 15:30 종가 |
| S&P500 / 나스닥 / DOW | 전일 미국장 종가 |
| 니케이225 | 전일 종가 |
| 환율 / 유가 / 금 | 24시간 시장, 발송 시점 기준 |

해외 증시 등락률은 **채널 마감 스냅샷 값을 우선**(확정 종가). 없을 때만 yfinance 대체.

### 4-3. 1건차 — 📊 데일리 시황 (숫자만, 약 900자)

환율 → 금리·원자재 → 해외 증시 → 국내 증시 → 해외 마감 시세.

### 4-4. 2건차 — 🧭 마켓 코멘트 (약 1,500~2,500자)

2초 간격으로 별도 발송. 섹션 사이 구분선(`━━━`).

| 섹션 | 내용 | 생성 방식 |
|---|---|---|
| 📌 오늘의 핵심 | 번호 3줄: ① 국내 증시 방향 + 야간 한국물 괴리로 본 갭 출발 가능성 ② 변동 최대 자산 ③ 임박 일정 또는 최다 언급 주제 | 수집 숫자 + 선별 결과 |
| ■ 전일 시장 | 환율·국내증시·해외증시·금리/원자재 | 수집 숫자 |
| ■ 오늘 개장 체크 | NDF 환율, 필라 반도체→반도체 대형주, MSCI 한국 ETF vs KOSPI200 괴리, 금리→성장주/가치주, 유가·금 | 수집 숫자 |
| ■ 일정 · 이벤트 | 발표·공시·만기 등 3줄 | 채널 본문 |
| ■ 종목 이슈 | 완성된 문장만 4줄 | 채널 본문 |
| ■ 테마 · 매크로 | 주제 4개 × 2문장, 주제 사이 한 줄 띄움 | 채널 본문 |

### 4-5. 채널 본문 분석 엔진 — 제목이 아니라 **본문 전체**

파이프라인: `build_sentence_pool()` → `group_by_topic()` → 섹션별 선별.

1. 문장 분해(`split_sentences`), 리포트 머리 태그 `[○○증권 ○○○]` 제거(`strip_tag`).
2. **노이즈 제거**(`is_noise`) — 전부 버림:
   - 인사말·구독 안내·링크·컴플라이언스 문구·전화번호
   - 앞이 잘려 시작하는 문장(조사·닫는 괄호로 시작) → `is_broken_start`
   - 종목 시세 나열(`삼성전자(-2.2%), 마이크론(-7%)…`) → `is_price_list` (퍼센트 괄호 3개 기준)
   - 괄호 6개 이상인 표·나열
3. **중복 제거**: 앞 22자 일치 또는 글자 유사도 0.88 초과. 섹션 간에도 단어 겹침 60% 초과면 제외(`picked_all`).
4. **점수화**(`score_sentence`):
   - 퍼센트·금액 가점은 **각각 최대 3개까지만** (나열문 1등 방지, 점수 상한제)
   - 촉매 표현 종류당 +2, 인과 표현(때문·영향·여파) +2.5, 확정 사실(발표·공시·체결) +1.5
   - 온전히 끝나는 문장 +1.5, 쉼표 4개 초과부터 감점, **투자의견성 문장 −2**
5. **길이 처리**(`clean_cut`) — **`…`로 절대 자르지 않는다.** 한도 초과 시 절이 끝나는 지점까지만 쓰고, 깔끔히 못 끊으면 그 문장을 아예 버린다.
6. **선별 순서**: ① 일정 → ② 종목 → ③ 테마. 먼저 뽑힌 문장은 뒤 섹션에서 재사용 금지.
7. **종목 섹션 조건**: 촉매 표현 2종류 이상 + 종결어미로 끝나는 완성 문장만. 리포트 제목 제외.
8. 테마는 **2곳 이상 채널이 함께 다룬 주제만** 채택, 주제당 데이터가 가장 풍부한 문장 선택. 채널명·소제목은 노출하지 않는다.

조절 상수:

```python
RESEARCH_HOURS = 26          # 최근 몇 시간 이내 글만 사용
THEME_TOPIC_COUNT = 4        # 테마 주제 수
THEME_LINES_PER_TOPIC = 2    # 주제당 문장 수
STOCK_LINE_COUNT = 4         # 종목 줄 수
SCHEDULE_LINE_COUNT = 3      # 일정 줄 수
COMMON_MIN_CHANNELS = 2      # 몇 개 채널 이상 언급 시 테마 채택
STOCK_MIN_SCORE = 4.0        # 종목 문장 최소 점수
THEME_LINE_LEN = 125
STOCK_LINE_LEN = 115
SCHED_LINE_LEN = 115
```

- 주제 판별은 `TOPIC_KEYWORDS` 사전(종목·매크로·테마 40여 개) 의존 → 새 테마는 수동 추가.
- `split_message()`가 3,800자 초과 시 청크 분할(텔레그램 4,096자 제한 대응).
- 메시지 하단에 `사내 참고용. 대외 배포·인용 금지` 자동 첨부.

### 4-6. 발송본 저장

발송과 동시에 `save_sent_brief()`가 `archive\brief\YYYY-MM-DD_브리핑.txt`로 저장 (위: 시황 데이터, `====` 구분선 아래: 마켓 코멘트). 메일 발송 예약 작업이 이 파일을 읽는다.

---

## 5. 주간 시황브리핑 (매주 화요일 15:00 이후)

### 5-1. 집계 기준 — 가장 중요

> **지난주 화요일 15:00 ~ 이번주 화요일 15:00**

작성: 화요일 15:00 이후 / 발표: 수요일 아침 회의(**2분 내외**, 5-5 참조) / 캘린더 알림: 화요일 15:00 등록됨.

### 5-2. 아카이브 파일 규칙

```python
BRIEFING_WEEKDAY = 1     # 화요일
BRIEFING_HOUR = 15       # 마감 시각
ARCHIVE_KEEP_DAYS = 14   # 14일 경과분 자동 삭제
```

| 파일 | 형식 | 예시 |
|---|---|---|
| 일별 | `YYYY-MM-DD.txt` | `2026-08-11.txt` |
| 주간 | `MMDD_MMDD_주간백데이터.txt` | `0804_0811_주간백데이터.txt` |

파일명 날짜는 **수집 기간**(화→화)이며 생성일이 아니다. 8/11(화) 14:59 실행 → `0804_0811`, 15:30 실행 → `0811_0818`. **브리핑 작성 시 오늘 날짜로 끝나는 파일을 쓴다.**

주간 백데이터 구조: `===` 구분자(채널 단위) + `---` 메시지 구분자의 한국어 UTF-8 텍스트. 파싱은 `grep -n` + `sed -n 'X,Yp'` 방식이 잘 통한다. 채널 7곳이라 파일이 크다(30만 자 이상 가능).

주간 파일 재생성 (일별 누락·기간 재설정 시, 기존 파일은 `_backup.txt` 자동 백업):

```powershell
python rebuild_weekly.py
```
```powershell
python rebuild_weekly.py 0804 0811
```

### 5-3. 브리핑 문서 규칙 (매주 동일 유지)

섹션 5개 고정, 주차별로 제목 문구만 변경:

```
[MM/DD~MM/DD 시황 브리핑] {한 주를 요약하는 제목}
1. 국내 증시: {한 주 성격}
2. 이번 주 최대 이슈: {등락 원인과 트리거}
3. 통화정책·금리·환율
4. 수급 및 정책 이슈
5. 지표·섹터 및 향후 일정
```

**애널리스트 개인 판단·전망 금지 (절대 규칙):**
- "…로 판단했습니다 / 전망했습니다" 형태는 **출처를 밝혀도 제외**. (스킬 문서의 "출처 명시하면 허용" 문구보다 이 규칙이 우선한다 — 사용자가 나중에 강화한 규칙)
- 투자의견·목표주가·추천 업종·전략 제안(바벨 전략, 비중 확대 등) 제외.
- 넣는 것: 지수·금리·환율·유가 레벨, 실적 수치, 수급 숫자, 정책·규제 변경 사실, 컨센서스 수치, 예정 일정.
- 판단이 필요한 대목은 사실만 나열하고 해석은 발표자에게 맡긴다.

**구두 발표용 문장 (구어체 흐름의 문어체 산문):**
- 한 문장에 숫자 3개 이상 금지. 길면 나눈다.
- 괄호식(`6,345.53(+0.73%)`) 대신 풀어 읽기: "6,345.53으로 0.73% 올랐습니다". 수치는 문장 안에 자연스럽게 분산.
- 불릿 첫 문장은 짧게 상황 제시, 뒤에 숫자.
- 접속 표현("그런데", "다만", "반면")으로 흐름을 잇는다.
- 존댓말 격식체(~습니다). 이모지 금지.

**표기 규칙**: "전년비"→"전년 대비", "전기비"→"전분기 대비". 지수·등락률 소수점 둘째 자리. 금액 단위 조/억 원·억/조 달러 통일. 강조(`**...**`)는 섹션당 1~2개, 기록·전환점이 되는 숫자만. 총개수는 분량에 비례시킨다(5-5) — 2분 기준 5개 내외.

**모든 수치는 백데이터에서 직접 확인한 값만.** 기억·추정 금지. 종가가 없고 익일 장중 시세만 있으면 역산 검증(예: 익일 장중 `6,337.94(-257.51p)` → 전일 종가 `6,595.45`).

### 5-4. 생성 워크플로우 (weekly-market-briefing 스킬)

스킬 폴더(레포에 포함할 것 — 9절 참조): `SKILL.md` + `scripts/build_briefing.js` + `references/example_content.json`

1. 백데이터 통독 (300~500줄 단위 순차, 요약본으로 쓰지 않는다). docx면 `pandoc -t markdown`으로 변환.
2. `content.json` 작성 (형식은 `references/example_content.json` 참조):

```json
{
  "title": "[MM/DD~MM/DD 시황 브리핑] 한 주 요약 제목",
  "sections": [
    { "head": "1. 국내 증시: …", "bullets": ["…습니다. **강조는 별표**…"] }
  ]
}
```

3. 빌드:

```bash
node scripts/build_briefing.js content.json outputs/MMDD_MMDD_시황브리핑_발표용.docx
```

4. **검증 생략 금지** — ① 음영이 `**...**` 구간에만 걸렸는지 ② 줄바꿈 깨짐 ③ 분량.
   SKILL.md는 LibreOffice(`soffice.py`) + `pdftoppm`을 쓰라고 하지만
   **이 환경의 LibreOffice는 일반 txt조차 변환하지 못한다(2026-09-01 확인).**
   대신 docx의 XML을 직접 파싱해 검증한다:

```bash
python3 -c "
import zipfile
from xml.etree import ElementTree as ET
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
root=ET.fromstring(zipfile.ZipFile('<출력>.docx').read('word/document.xml').decode('utf-8'))
tot=0
for p in root.iter(W+'p'):
    t=''.join(x.text or '' for x in p.iter(W+'t')); tot+=len(t)
    k='불릿' if p.find('.//'+W+'numPr') is not None else '머리'
    for r in p.iter(W+'r'):
        s=r.find('.//'+W+'shd')
        if s is not None: print('  음영:', ''.join(x.text or '' for x in r.iter(W+'t')))
    print(f'[{k}] {len(t):3d}자 {t[:40]}')
print('총', tot, '자')
"
```

5. 파일 전달 + 발표 시 강조 포인트 3가지 불릿.

### 5-5. 분량 기준 — 실측값 (2026-09-01 교정)

**기존 지침의 "5섹션 × 3~4불릿 = 1~2분"은 틀렸다.** 실제 낭독 속도로 재보면 약 6분이다.
한국어 격식체 낭독은 **350~450자/분**이며, 아래 표를 기준으로 삼는다.

| 목표 | 본문 글자수 | 불릿 수 | 분량 |
|---|---|---|---|
| 1분 | 약 450~500자 | 5~6개 (섹션당 1개) | A4 반쪽 |
| **2분 (기본값)** | **850~950자** | **11개 내외 (섹션당 2~3개)** | **A4 1쪽** |
| 3분 | 약 1,300자 | 15~16개 | A4 1.5쪽 |

- 섹션 5개 구조는 어떤 분량에서도 유지한다(5-3 참조).
- 강조(`**...**`)는 분량에 비례시킨다. 2분이면 5개 내외가 적정이며,
  분량이 줄었는데 5~7개를 고집하면 거의 모든 불릿이 노랗게 되어 강조 효과가 사라진다.
- 작성 후 `본문 글자수 ÷ 400`으로 낭독 시간을 확인한다.

### 5-6. 화면 투사용 PDF (2026-09-01 신설)

발표 중 화면에 띄우고 설명할 용도. docx(원고)와 짝으로 만든다.

- 파일명: `MMDD_MMDD_시황브리핑_핵심요약.pdf`, **A4 가로 2쪽** (1쪽 ≈ 1분)
- 1쪽: KPI 4개 + 코스피 5거래일 선차트 + 핵심 3가지 + 그 외 짚어둘 숫자
- 2쪽: 근거 차트 3개(실적·금리·수급) + 향후 일정
- 소스는 `briefings/highlight_MMDD_MMDD.html`. 차트는 인라인 SVG로 직접 그린다.
- **한글 폰트가 이 환경에 없다.** `npm pack @fontsource/noto-sans-kr`으로 받아
  woff2를 base64로 HTML에 내장한다. (fonts.google.com은 네트워크 정책상 차단됨)
- PDF 변환·검증(LibreOffice 불가 대신):

```bash
/opt/pw-browsers/chromium-1194/chrome-linux/chrome --headless --no-sandbox --disable-gpu \
  --no-pdf-header-footer --virtual-time-budget=12000 \
  --print-to-pdf="<출력>.pdf" <입력>.html
```
```bash
pip install --quiet pypdfium2 pillow && python3 -c "
import pypdfium2 as pdfium
d=pdfium.PdfDocument('<출력>.pdf')
for i in range(len(d)): d[i].render(scale=2).to_pil().save(f'/tmp/p{i+1}.png')
"
```

렌더된 PNG를 **직접 눈으로 보고** 잘림·겹침·빈 공간을 확인한다.

산출물: `MMDD_MMDD_시황브리핑_발표용.docx`(원고) + `MMDD_MMDD_시황브리핑_핵심요약.pdf`(화면용).
**8/4~8/11, 8/25~9/1 주차 생성 완료.**

---

## 6. 데이터 소스

| 구분 | 소스 | 비고 |
|---|---|---|
| 해외 시세 | yfinance | |
| 국내 지수 | 네이버금융 폴링 API | pykrx는 KRX 로그인 요구로 사용 불가 |
| 해외 마감 시세 | `t.me/s/globalmktinsight` | 숫자만 추출 |
| 리서치 · 아카이브 | 구독 채널 7곳 | 본문 전체 |

**구독 채널** — `RESEARCH_CHANNELS` 리스트 한 곳에서 중앙 관리. 마켓 코멘트와 주간 아카이브에 동시 적용.

| 표시이름 | 채널 |
|---|---|
| SK증권IT | `skitteam` |
| 미래에셋시황 | `globalmktinsight` |
| 키움전략 | `hedgecat0301` |
| 메리츠테크 | `merITz_tech` |
| SK증권리서치 | `sksresearch` |
| 이동지 | `ehdwl` |
| 이그전 | `egzion` |

- 원래 3곳 → 2026-08-11에 7곳으로 확대 (merITz_tech, sksresearch, ehdwl, egzion 추가). 뉴스 RSS(연합뉴스)는 제거.
- **보완 로직**: yfinance 부실 항목(브렌트유 `BZ=F`, 미 2년물 `2YY=F`)은 채널 스냅샷 값으로 자동 대체.
- **미확보**: 두바이유(무료 실시간 소스 없음), 브라질 국채금리(yfinance 미지원).

---

## 7. 저작권·컴플라이언스 (전 산출물 공통)

- 숫자 해석은 수집 숫자만 근거로 스크립트가 직접 생성. **외부 AI API 미사용(비용 0원).**
- 채널 원문 문장이 포함된 마켓 코멘트는 **사내 전용**. 대외 배포·고객 제공·자료 인용 금지. 하단 고지 문구 자동 첨부.
- **주간 브리핑에는 채널 원문을 그대로 옮기지 않는다. 문장은 새로 작성한다.**
- **애널리스트 개인 판단·전망·투자의견은 출처를 밝혀도 어떤 브리핑에도 넣지 않는다.**
- 컴플라이언스 하드 차단이 코드에 구현돼 있다: `_OPINION_PATTERN`(투자의견성 문장 차단) + `FILTER_STATS`(차단 집계).

---

## 8. 예약 작업 (claude.ai 트리거) — ⚠️ 이관 시 정리 필요

> **Claude Code로 이사하면 이 트리거들은 따라오지 않는다.** 아래 상태를 보고 정리·재구축을 결정할 것.

| 작업 | trigger_id | 주기 | 상태 |
|---|---|---|---|
| 일간 시황 개인메일 발송 | `trig_01WxtqRGP74UK373dPxtTrFf` | 평일 07:00 KST (cron `0 22 * * 0-4` UTC) | **고장 — 기기 바인딩 없음 (08-25 확정, 08-26 재확인)** |
| 주간 시황브리핑 작성·메일 발송 | `trig_01F1HkgHWtmGuQAjiUeEpqFs` | 화요일 15:10 KST (cron `10 6 * * 2` UTC) | 바인딩 미확인, 같은 문제 가능성 높음 |

- 수신: `seen_sks@naver.com` / 발신: Gmail 커넥터 `jse0930@gmail.com`
- **고장 원인**: 두 작업 모두 사용자 PC 접근(`requires_local_device`)이 필요한데, remote-devices 도구가 세션에 바인딩되지 않음. 클라우드 세션에서 만든 예약 작업에는 바인딩을 붙일 수 없다는 것이 08-25에 확정됨(`not bound: no_signed_approval`). **바인딩은 노트북의 Claude 데스크톱 앱에서 작업을 만들고 승인할 때만 붙는다.** 기존 작업에 나중에 추가 불가.
- 일간 메일 작업의 정확한 동작 사양: `archive\brief\`에서 오늘 날짜 파일을 찾아, 제목 `[데일리 시황] M월 D일`, 본문은 원문 그대로(두 부분을 소제목으로 구분, 숫자 목록 monospace), txt 첨부, 하단 사내한 고지. **오늘 파일이 없으면 조용히 종료**(실패 메일 금지).
- 주간 작업 사양: 오늘 날짜(MMDD)로 끝나는 주간 파일 확보 → 스킬로 docx 생성(`YYYYMMDD_시황브리핑.docx`) → archive에 사본 저장 → 제목 `[MM/DD~MM/DD 시황 브리핑]` + 핵심 3줄 요약 + docx 첨부 발송. 실패 시 `[시황브리핑 작성 실패]` 메일.
- **이관 후 권장**: Claude Code에서는 트리거 대신 (a) 수동 실행 또는 (b) Windows 작업 스케줄러 + Claude Code 헤드리스 실행으로 대체 검토. 대체가 정착되면 위 두 트리거는 삭제(중복 발송 방지).

---

## 9. weekly-market-briefing 스킬 이관

- claude.ai에서는 `/mnt/skills/user/weekly-market-briefing/`에 있었다. Claude Code에서는 자동으로 안 붙는다.
- **함께 전달한 `weekly-market-briefing_skill.zip`을 레포의 `.claude/skills/weekly-market-briefing/`에 풀어 넣을 것.** 구성: `SKILL.md`, `scripts/build_briefing.js`(docx 빌더, Node), `references/example_content.json`(완성 예시).
- 빌드 의존성: Node.js + `docx` 패키지(`package.json` 포함, `npm install`).
- **검증 단계 주의**: SKILL.md는 LibreOffice/pdftoppm을 쓰라고 하지만 이 환경에서는 둘 다 못 쓴다.
  LibreOffice는 일반 txt조차 변환 실패하고 pdftoppm은 미설치다. 대체 방법은 5-4·5-6 참조.
- **⚠️ 스킬이 두 곳에 있다.** 레포 사본(`.claude/skills/`)과 claude.ai 계정 동기화 사본
  (`~/.claude/skills/synced/…`)이 공존한다. 계정 사본은 어느 세션에서나 뜨지만 CLAUDE.md는 안 따라온다.
  SKILL.md 원문은 "전망성 문장은 출처를 명시하면 허용"이라 5-3의 절대 금지 규칙과 충돌하므로,
  **이 레포 밖에서 브리핑을 만들면 컴플라이언스 위반이 난다.** 반드시 이 레포 세션에서 작업할 것.

---

## 10. Axtival 공모전 (✅ 2026-09-08 접수 완료 — 결과 대기)

| 항목 | 값 |
|---|---|
| 주제 | AI Agent 업무 활용 사례 / Agent명 **데일리 시황 에이전트** |
| **접수 마감** | **9월 8일(화)** — 그룹웨어 메일, HR부 김아름 차장(02-3773-8053) |
| 일정 | 1차 결과 9.14 / 2차 PT 9.16 / 최종 9.30 / 글로벌 P/G 11월(항저우) |
| 제출물 | `데일리시황에이전트_Axtival.pptx`(10p, 발표노트 포함) + PDF + `산출물_설명.md` + `telegram_market_report.py` |
| 위치 | `C:\Telegram Desktop\Axtival\` |

핵심 메시지 5: ① 이미 매일 돌아가는 실사용 ② 컴플라이언스를 코드로 강제 ③ 본문 전체를 읽는다 ④ 0원 ⑤ 설정 3곳 교체로 복제.

성과 수치: 일간 40분×250일=167h + 주간 60분×52주=52h = **연 219시간(27.4 영업일)**. 스크립트의 `MANUAL_MINUTES_DAILY`/`MANUAL_MINUTES_WEEKLY`와 일치시킬 것. 확산 시나리오는 "가정" 명시.

공모전용 추가 기능(08-20 구현): 워치리스트(`WATCHLIST`, `build_watch_rows()`), 컴플라이언스 차단·집계(`_OPINION_PATTERN`, `FILTER_STATS`), 절감시간 계측(`update_stats()`, `--stats`).

**접수 완료 (2026-09-08).** 준비했던 자료를 수정 없이 그대로 제출했다.
따라서 아래 항목들은 제출본에 반영되지 않은 상태로 마감됐다 — 2차 PT 진출 시 보완 대상이다.

- [x] 9/8 그룹웨어 접수 (PPT 원본 + PDF + 산출물) — **완료**
- [ ] PPT 표지·마지막장 2곳 `○○○` 실명 교체 *(미반영 제출)*
- [ ] 실제 텔레그램 발송 화면 캡처로 6페이지 목업 교체 *(미반영 제출)*
- [ ] `--stats` 실측 누적 후 7페이지 수치 갱신 *(미반영 제출)*
- [ ] 2차 PT(9.16) 대비 `--stats` 시연 준비 — 1차 결과 9/14 확인 후 진행

**다음 확인일: 9/14 (1차 결과 발표).**

---

## 11. 문제 해결 표

| 증상 | 원인 / 조치 |
|---|---|
| 텔레그램이 안 옴 | `log.txt` 확인. `[생략]`이면 주말·지연 조건 (정상) |
| 1건만 오고 코멘트가 안 옴 | `[전송:comment]` 줄 확인. 대상의 `send_comment` 점검 |
| 그룹방에만 안 옴 | 봇 추방·차단 또는 chat_id 변경. `[전송 실패]` 줄에 사유 |
| 문장이 `…`로 잘림 | 발생하면 안 됨. `clean_cut()` 우회 지점 점검 |
| 종목 시세 나열이 들어옴 | `is_price_list()` 기준(퍼센트 괄호 3개) 조정 |
| 종목 섹션이 비어 있음 | 완성 문장 조건. `STOCK_MIN_SCORE` 낮추면 늘어남 |
| 코멘트가 통째로 비어 있음 | `[분석] 문장 N개` 확인. 0이면 채널 수집 실패 |
| 지난 날짜 시황 뒤늦게 도착 | `MAX_DELAY_HOURS` 확인 |
| 로그가 비어 있음 | 파이썬 경로 문제 (`WindowsApps` 껍데기) |
| 마지막 결과 `-1073741510` | 배치파일 인코딩 문제. 파이썬 직접 실행으로 등록 |
| 특정 지표가 `-` | 티커 문제. 스냅샷 보완 대상 추가 또는 티커 교체 |
| 실행했는데 응답 없음 | 채널 7곳 수집에 2~3분 소요 (정상) |
| 새 테마가 안 잡힘 | `TOPIC_KEYWORDS`에 주제·키워드 추가 |
| 특정 채널 내용이 안 보임 | `[채널 실패]` 기록 확인. 아이디 오타·비공개 전환 점검 |
| 예약 메일이 안 옴 | 8절 참조 — 기기 바인딩 문제 (알려진 고장) |

---

## 12. 미해결 / 개선 여지

1. **예약 메일 발송 2건 모두 사실상 고장** (기기 바인딩) — 8절. 최우선 정리 대상.
2. 주제 판별이 `TOPIC_KEYWORDS` 사전 의존 → 새 테마 수동 추가.
3. 두바이유·브라질 국채금리 소스 미확보.
4. 경제지표 발표 캘린더 미구현 (investing.com 크롤링은 차단·약관 문제로 배제, FRED API 보류).
5. 일정 섹션은 채널 글에 언급된 일정만 잡음 → 언급 없으면 빈 채로 나갈 수 있음.
6. Axtival은 9/8 접수 완료. 1차 결과(9/14) 확인 후 2차 PT 준비 여부 결정 (10절).
7. `weekly-market-briefing` 스킬이 레포·계정 두 곳에 존재하고 SKILL.md와 CLAUDE.md 5-3의
   컴플라이언스 규칙이 서로 충돌한다. 계정 사본은 claude.ai에서만 수정 가능 (9절).

---

## 13. 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-08-11 | 발송 06:00→06:30, 마켓 코멘트 통합, 뉴스 RSS 제거, 채널 3곳→7곳 |
| 2026-08-19 | **하루 2건 분리 발송**, 그룹방 발송 재개(사내용 확인), 채널 본문 전체 분석 엔진, '오늘 개장 체크' 신설 |
| 2026-08-20 | `…` 잘림 전면 제거(clean_cut), 시세 나열·깨진 문장 필터, 점수 상한제, 섹션 재구성(핵심 3줄+구분선), 섹션 간 중복 제거. 주간 브리핑 자동발송 트리거 등록. Axtival 착수 + 공모전용 3기능 구현 |
| 2026-08-21 | 일간 메일 발송 트리거 등록 → 첫 실행에서 PC 미연결 확인 |
| 2026-08-25 | 기기 바인딩 부재 확정 (클라우드 생성 작업엔 바인딩 불가). 중복 방지용 임시 작업 삭제 |
| 2026-08-26 | 미발송 재확인. **Claude Code 레포로 이관 결정, 본 인수인계서 작성**. 토큰·chat_id를 `.env`로 분리, 스킬을 레포에 배치 |
| 2026-09-01 | 8/25~9/1 주차 브리핑 생성. **분량 기준이 실측과 3배 어긋난 것을 확인해 5-5 신설**. LibreOffice 변환 불가 확인 → 검증 방법 교체. **화면 투사용 PDF(5-6) 신설** |
| 2026-09-08 | **Axtival 접수 완료**(수정 없이 제출). 본 지침을 9/1 실측 결과로 갱신 |

---

## 14. Claude Code 이관 체크리스트

1. ✅ **완료** — 레포 루트에 이 파일을 `CLAUDE.md`로 배치 (자동 로드).
2. ✅ **완료** — `telegram_market_report.py`, `rebuild_weekly.py` 커밋. 하드코딩돼 있던 `TELEGRAM_BOT_TOKEN`과 `chat_id`는 `.env` 파일로 분리했다 (3절 참조). 코드에는 남아있지 않다.
3. ✅ **완료** — `weekly-market-briefing` 스킬을 `.claude/skills/weekly-market-briefing/`에 배치. `docx` 의존성용 `package.json` 추가, 예시 content.json으로 빌드 검증 완료.
4. ⬜ 프로젝트 문서 4종(`프로젝트_지침.md`, `claude/주간브리핑_자동발송.md`, `claude/일간시황_메일발송.md`, `claude/Axtival_공모전.md`)도 레포에 보존 권장 — 본 문서가 통합본이지만 원본 이력 가치가 있다.
5. ⬜ claude.ai 트리거 2건은 대체 방안 정착 후 삭제 (8절).
6. ⬜ Gmail 발송이 필요하면 Claude Code에 Gmail MCP 연결을 별도 설정해야 한다 (claude.ai 커넥터는 안 따라옴).
7. ✅ 조치 불필요 — Windows 작업 스케줄러(`DailyMarketBrief`)는 Claude와 무관하게 계속 동작.

### 이관 후 사용자 PC에서 해야 할 일 (1회)

`C:\Telegram Desktop\` 폴더에 `.env` 파일을 만들고 토큰·채팅방 번호를 넣어야
일간 발송이 계속 동작한다. 이 작업 전에는 `[설정 오류]`를 남기고 종료한다.

### ⚠️ 레포 공개 상태 관련 미해결 사항

- 이 레포는 **public**이다. 사내 전용 자료(채널 원문)가 올라가지 않도록
  `backdata/`, `archive/`, `briefings/`, `log.txt`를 `.gitignore`에 등록해 두었다.
- **채팅방 번호 2개가 초기 커밋(`9c81f83`) 이력에 남아 있다.** 봇 토큰은 포함되지 않았다.
  레포를 private으로 전환하는 것이 가장 확실한 해결책이다.
- 7절 컴플라이언스(대외 배포·인용 금지)를 고려하면 **private 전환을 권장**한다.
