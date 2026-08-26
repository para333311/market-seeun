# -*- coding: utf-8 -*-
"""
데일리 마켓 브리핑 텔레그램 자동 발송  (2026-08-20 개편)

[발송 구조]  ★ 하루 2건으로 분리 발송
 1건차 : 📊 시황 데이터
         환율 / 금리·원자재 / 해외증시 / 국내증시 / 해외 마감 시세
 2건차 : 🧭 마켓 코멘트
         📌 오늘의 핵심 3가지
         ■ 전일 시장 → ■ 오늘 개장 체크 → ■ 일정·이벤트
         → ■ 종목 이슈 → ■ 테마·매크로

[마켓 코멘트 작성 원칙]
 · 채널 글의 "제목"이 아니라 "본문 전체"를 문장 단위로 분해한다.
 · 인사말·구독안내·컴플라이언스 문구, 앞이 잘린 문장, 종목 시세 나열은 버린다.
 · 숫자·인과·촉매(수주/가이던스/상회·하회/규제 등)가 담긴 문장에 가중치를 준다.
 · **문장을 '…'로 자르지 않는다.** 길면 절이 끝나는 지점까지만 쓰고,
   깔끔하게 끊을 수 없으면 그 문장을 아예 쓰지 않는다 (clean_cut).
 · 섹션 간·섹션 내 중복 내용을 제거한다 (picked_all 공용 목록).
 · 수집한 숫자만으로 "오늘의 핵심"과 "오늘 개장 체크"를 자동 생성한다.

※ 채널 원문 문장이 포함되므로 사내 참고용으로만 사용한다.
"""

import os
import re
import sys
import html as htmlmod
import datetime
import requests

# ══════════════════════════ 설정 ══════════════════════════
# ─────────────────────────────────────────────────────────────
#  비밀값(봇 토큰·채팅방 번호)은 코드에 적지 않는다.
#  이 파일과 같은 폴더의 `.env` 파일에서 읽어온다.
#  `.env` 는 깃에 올라가지 않는다(.gitignore). 작성법은 `.env.example` 참고.
# ─────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(_BASE_DIR, ".env")


def load_local_env(path=ENV_PATH):
    """스크립트 옆의 .env 파일을 읽어 환경변수로 올린다 (외부 패키지 불필요).

    형식: 한 줄에 KEY=값. `#`으로 시작하는 줄과 빈 줄은 무시한다.
    이미 설정된 환경변수가 있으면 그 값을 우선한다.
    """
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_local_env()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# ─────────────────────────────────────────────────────────────
#  발송 대상  ★ 대상별로 어떤 메시지를 받을지 여기서 정한다
#     send_market  : 1건차 시황 데이터
#     send_comment : 2건차 마켓 코멘트
#  → 그룹방에 코멘트를 빼고 싶으면 send_comment 를 False 로 바꾸면 된다.
#  채팅방 번호(chat_id)는 .env 의 TELEGRAM_CHAT_ID_PERSONAL / _GROUP 에서 읽는다.
# ─────────────────────────────────────────────────────────────
CHAT_TARGETS = [
    {"name": "개인 채팅",        "chat_id": os.environ.get("TELEGRAM_CHAT_ID_PERSONAL", ""), "send_market": True, "send_comment": True},
    {"name": "그룹 J의 시황정보", "chat_id": os.environ.get("TELEGRAM_CHAT_ID_GROUP", ""),    "send_market": True, "send_comment": True},
]
# chat_id 가 비어 있는 대상은 발송에서 제외한다.
CHAT_TARGETS = [t for t in CHAT_TARGETS if t["chat_id"]]

TELEGRAM_CHAT_IDS = [t["chat_id"] for t in CHAT_TARGETS]        # 하위 호환
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_IDS[0] if TELEGRAM_CHAT_IDS else "")


def check_credentials():
    """설정 누락 시 무엇을 해야 하는지 알려주고 중단한다."""
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_IDS:
        missing.append("TELEGRAM_CHAT_ID_PERSONAL 또는 TELEGRAM_CHAT_ID_GROUP")
    if missing:
        # log() 는 아래에서 정의되지만 호출 시점에는 이미 존재한다.
        log("[설정 오류] 다음 값이 없습니다: " + ", ".join(missing))
        log(f"            {ENV_PATH} 파일을 만들고 값을 넣어주세요.")
        log("            작성 예시는 같은 폴더의 .env.example 파일에 있습니다.")
        return False
    return True

HEADERS = {"User-Agent": "Mozilla/5.0"}

# 시세 스냅샷을 가져올 공개 채널 (숫자만 추출)
SNAPSHOT_CHANNEL = "globalmktinsight"
SNAPSHOT_KEYS = [
    "DOW", "S&P500", "NASDAQ", "러셀2000",
    "MSCI 한국지수", "KRX KOSPI 200", "NDF 환율", "필라델피아 반도체",
    "2년물", "10년물", "브렌트유",
]

# ─────────────────────────────────────────────────────────────
#  구독 채널 목록  ★ 채널을 추가·삭제하려면 여기만 고치면 된다
# ─────────────────────────────────────────────────────────────
RESEARCH_CHANNELS = [
    ("SK증권IT",     "skitteam"),
    ("미래에셋시황",  "globalmktinsight"),
    ("키움전략",      "hedgecat0301"),
    ("메리츠테크",    "merITz_tech"),
    ("SK증권리서치",  "sksresearch"),
    ("이동지",       "ehdwl"),
    ("이그전",       "egzion"),
]

# ── 마켓 코멘트 조절값 ────────────────────────────────────────
RESEARCH_HOURS = 26          # 최근 몇 시간 이내 글을 볼지
SENT_MIN_LEN = 18            # 이보다 짧은 문장은 버림
SENT_MAX_LEN = 170           # 후보로 삼을 문장의 최대 길이
THEME_TOPIC_COUNT = 4        # '테마·매크로'에 넣을 주제 수
THEME_LINES_PER_TOPIC = 2    # 주제당 문장 수
STOCK_LINE_COUNT = 4         # '개별 종목' 줄 수
SCHEDULE_LINE_COUNT = 3      # '일정·이벤트' 줄 수
COMMON_MIN_CHANNELS = 2      # 테마: 몇 개 채널 이상 언급 시 채택
STOCK_MIN_SCORE = 4.0        # 개별 종목 문장 최소 점수

# 섹션별 출력 길이 — 이 안에서 '문장이 끝나는 지점'까지만 쓴다. 억지로 자르지 않는다.
THEME_LINE_LEN = 125
STOCK_LINE_LEN = 115
SCHED_LINE_LEN = 115

# 하위 호환용(이전 설정 이름)
RESEARCH_LINE_LEN = SENT_MAX_LEN
COMMON_TOPIC_COUNT = THEME_TOPIC_COUNT

# ─────────────────────────────────────────────────────────────
#  관심종목 워치리스트  ★ 내 커버리지 종목을 여기에 넣으면 최우선으로 잡아준다
#  형식: ("표시이름", ["같은 뜻으로 쓰이는 표현", ...])
# ─────────────────────────────────────────────────────────────
WATCHLIST = [
    ("삼성전자",      ["삼성전자", "삼전", "005930"]),
    ("SK하이닉스",    ["SK하이닉스", "SK 하이닉스", "하이닉스", "000660"]),
    ("한화오션",      ["한화오션"]),
    ("HD현대일렉트릭", ["HD현대일렉트릭", "현대일렉트릭"]),
    ("알테오젠",      ["알테오젠"]),
]
WATCH_LINE_COUNT = 4         # 워치리스트 섹션 최대 줄 수
WATCH_LINE_LEN = 115

# ─────────────────────────────────────────────────────────────
#  성과 계측  ★ 자동화 이전 수작업 소요시간 (분)
# ─────────────────────────────────────────────────────────────
MANUAL_MINUTES_DAILY = 40    # 일간 시황 수집·정리·발송에 걸리던 시간
MANUAL_MINUTES_WEEKLY = 60   # 주간 브리핑 작성에 걸리던 시간
STATS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archive", "agent_stats.json")

# 브리핑 백데이터로 매일 저장할 채널 (위 목록을 그대로 사용)
ARCHIVE_CHANNELS = list(RESEARCH_CHANNELS)
ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archive")
ARCHIVE_KEEP_DAYS = 14   # 이보다 오래된 아카이브 파일은 자동 삭제

INDICATORS_FX = [
    ("USD/KRW", "KRW=X", "", 1),
    ("USD/JPY", "JPY=X", "", 2),
    ("USD/BRL(헤알)", "BRL=X", "", 3),
    ("달러인덱스", "DX-Y.NYB", "", 2),
]
INDICATORS_RATE = [
    ("미 2년물", "2YY=F", "%", 3),
    ("미 10년물", "^TNX", "%", 3),
    ("미 30년물", "^TYX", "%", 3),
    ("WTI", "CL=F", "$", 2),
    ("브렌트유", "BZ=F", "$", 2),
    ("금", "GC=F", "$", 2),
]
INDICATORS_GLOBAL = [("S&P500", "^GSPC", "", 2), ("나스닥", "^IXIC", "", 2), ("니케이225", "^N225", "", 2)]


# ══════════════════════════ 로그 ══════════════════════════
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.txt")


def log(msg=""):
    """콘솔이 없어도 안전하게 기록한다."""
    line = str(msg)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line)
    except Exception:
        pass


# ══════════════════════════ 해외 시세 ══════════════════════════
def get_price(ticker):
    try:
        import yfinance as yf
        d = yf.Ticker(ticker).history(period="10d").dropna(subset=["Close"])
        if len(d) < 2:
            return None, None
        last, prev = float(d["Close"].iloc[-1]), float(d["Close"].iloc[-2])
        if prev == 0 or last != last or prev != prev:
            return None, None
        return last, (last - prev) / prev * 100
    except Exception:
        return None, None


def fmt_line(name, v, c, unit="", digits=2):
    if v is None or c is None:
        return f"• {name}: -" if v is None else f"• {name}: {v:,.{digits}f}{unit}"
    return f"• {name}: {v:,.{digits}f}{unit} {'▲' if c >= 0 else '▼'}{abs(c):.2f}%"


# ══════════════════════════ 국내 지수 ══════════════════════════
def get_naver_index(code):
    try:
        r = requests.get(
            f"https://polling.finance.naver.com/api/realtime/domestic/index/{code}",
            headers={**HEADERS, "Referer": "https://finance.naver.com/"}, timeout=10)
        r.raise_for_status()
        it = r.json()["datas"][0]
        return (float(str(it["closePrice"]).replace(",", "")),
                float(str(it["fluctuationsRatio"]).replace(",", "")))
    except Exception:
        return None, None


def _kr_change_from_yahoo(ticker, price):
    """네이버 등락률이 0.00%로 초기화됐을 때 야후 일봉으로 전일 대비 등락률을 다시 구한다."""
    try:
        import yfinance as yf
        d = yf.Ticker(ticker).history(period="15d").dropna(subset=["Close"])
        closes = [float(x) for x in d["Close"].tolist() if x == x]
        if len(closes) < 2:
            return None
        if price is None:
            price, prev = closes[-1], closes[-2]
        elif abs(closes[-1] - price) <= max(0.5, price * 0.001):
            prev = closes[-2]      # 야후 최신 종가 = 네이버 값 → 그 직전 종가와 비교
        else:
            prev = closes[-1]      # 네이버 값이 더 최신 → 야후 최신 종가가 전일 종가
        if not prev:
            return None
        return (price - prev) / prev * 100
    except Exception:
        return None


def get_korea_market():
    out = []
    for name, code, tk in [("KOSPI", "KOSPI", "^KS11"), ("KOSDAQ", "KOSDAQ", "^KQ11")]:
        v, c = get_naver_index(code)
        if v is None:
            v, c = get_price(tk)
        # 장 시작 전에는 네이버 폴링 API가 등락률을 0.00%로 초기화한다.
        if v is not None and (c is None or abs(c) < 0.005):
            fixed = _kr_change_from_yahoo(tk, v)
            if fixed is not None:
                log(f"[보정] {name} 등락률 0.00% -> {fixed:+.2f}% (야후 일봉 기준)")
                c = fixed
        out.append(fmt_line(name, v, c))
    return out


# ══════════════════════════ 텔레그램 공개채널 ══════════════════════════
_PAGE_CACHE = {}


def _channel_page(channel):
    """채널 웹 미리보기 HTML을 한 번만 받아 재사용한다."""
    if channel in _PAGE_CACHE:
        return _PAGE_CACHE[channel]
    html = ""
    try:
        r = requests.get(f"https://t.me/s/{channel}", headers=HEADERS, timeout=15)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        log(f"[채널 실패] {channel}: {e}")
    _PAGE_CACHE[channel] = html
    return html


def _clean_html(fragment):
    t = fragment.replace("<br/>", "\n").replace("<br>", "\n")
    t = re.sub(r"<[^>]+>", "", t)
    return htmlmod.unescape(t)


def _channel_blocks(channel):
    """공개 채널 웹 미리보기에서 메시지 본문 텍스트 목록을 반환"""
    html = _channel_page(channel)
    if not html:
        return []
    raw = re.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, re.S)
    return [_clean_html(b) for b in raw]


def _parse_msg_time(value):
    """'2026-08-11T08:30:12+00:00' → 로컬 시각(naive)"""
    try:
        dt = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _channel_messages(channel):
    """(작성시각, 본문) 목록. 시각을 못 읽으면 None."""
    html = _channel_page(channel)
    if not html:
        return []
    out = []
    for part in re.split(r'<div class="tgme_widget_message[ "]', html)[1:]:
        m = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', part, re.S)
        if not m:
            continue
        text = _clean_html(m.group(1)).strip()
        if not text:
            continue
        md = re.search(r'<time[^>]+datetime="([^"]+)"', part)
        out.append((_parse_msg_time(md.group(1)) if md else None, text))
    return out


def fetch_snapshot():
    """해외 마감 시세: 숫자 라인만 추출"""
    for txt in reversed(_channel_blocks(SNAPSHOT_CHANNEL)):
        if "Global Market Snapshot" not in txt:
            continue
        m = re.search(r"\(([0-9]{1,2}/[0-9]{1,2})\)", txt)
        head = m.group(1) if m else ""
        rows = []
        for line in txt.split("\n"):
            line = line.strip().lstrip("-").strip()
            if any(line.startswith(k) for k in SNAPSHOT_KEYS):
                rows.append("• " + line)
        if rows:
            return head, rows
    return None


# ══════════════════════════ 주제 사전 ══════════════════════════
# 형식: "대표주제": (["같은 뜻으로 쓰이는 표현", ...], 분류)
#   분류 stock = 개별 종목 섹션 / theme·macro = 테마·매크로 섹션
TOPIC_KEYWORDS = {
    # ── 개별 종목 ─────────────────────────────
    "삼성전자":      (["삼성전자", "삼전", "005930"], "stock"),
    "SK하이닉스":    (["SK하이닉스", "하이닉스", "000660"], "stock"),
    "엔비디아":      (["엔비디아", "NVDA", "NVIDIA"], "stock"),
    "마이크론":      (["마이크론", "MU "], "stock"),
    "TSMC":         (["TSMC", "대만 반도체"], "stock"),
    "인텔":          (["인텔", "INTC"], "stock"),
    "AMD":          (["AMD"], "stock"),
    "브로드컴":      (["브로드컴", "AVGO"], "stock"),
    "애플":          (["애플", "아이폰", "AAPL"], "stock"),
    "테슬라":        (["테슬라", "TSLA"], "stock"),
    "빅테크":        (["마이크로소프트", "아마존", "구글", "알파벳", "메타 플랫폼", "하이퍼스케일러"], "stock"),
    "현대차·기아":   (["현대차", "기아", "현대자동차"], "stock"),
    "네이버·카카오": (["네이버", "카카오"], "stock"),
    "LG에너지솔루션": (["LG에너지솔루션", "엘지엔솔", "LG엔솔"], "stock"),
    "한화·HD현대":   (["한화오션", "한화에어로", "HD현대", "HD한국조선"], "stock"),

    # ── 테마 ─────────────────────────────────
    "HBM":          (["HBM", "고대역폭"], "theme"),
    "메모리 가격":   (["DRAM", "디램", "D램", "낸드", "NAND", "메모리 가격", "고정거래가"], "theme"),
    "AI 데이터센터": (["데이터센터", "AI 인프라", "CAPEX", "캐펙스", "설비투자"], "theme"),
    "전력기기":      (["전력기기", "변압기", "전선", "전력설비", "송배전"], "theme"),
    "로봇":          (["로봇", "휴머노이드", "피지컬AI", "피지컬 AI"], "theme"),
    "방산":          (["방산", "K방산", "무기 수출"], "theme"),
    "조선":          (["조선", "선박", "LNG선", "수주잔고"], "theme"),
    "원전":          (["원전", "원자력", "SMR"], "theme"),
    "화장품":        (["화장품", "K뷰티", "뷰티"], "theme"),
    "제약바이오":    (["바이오", "제약", "임상", "FDA"], "theme"),
    "2차전지":       (["2차전지", "이차전지", "배터리", "양극재", "전기차"], "theme"),
    "MLCC":         (["MLCC", "적층세라믹"], "theme"),
    "실적시즌":      (["어닝", "실적 발표", "가이던스", "컨센서스", "영업이익", "서프라이즈"], "theme"),

    # ── 매크로 ───────────────────────────────
    "미국 물가":     (["CPI", "소비자물가", "PCE", "PPI", "인플레이션"], "macro"),
    "미국 고용":     (["고용보고서", "비농업", "실업률", "신규 실업수당"], "macro"),
    "FOMC·금리":    (["FOMC", "연준", "기준금리", "금리 인상", "금리 인하", "페드워치", "FedWatch", "파월"], "macro"),
    "미 국채금리":   (["국채금리", "10년물", "2년물", "장단기 금리차"], "macro"),
    "환율":          (["환율", "달러/원", "달러-원", "원달러", "달러인덱스", "원화 약세", "원화 강세"], "macro"),
    "유가·에너지":   (["유가", "WTI", "브렌트", "호르무즈", "OPEC", "감산"], "macro"),
    "금·귀금속":     (["금값", "금 가격", "온스당", "은 가격", "귀금속"], "macro"),
    "외국인 수급":   (["외국인 순매수", "외국인 순매도", "외국인 수급", "기관 순매수", "프로그램 매매"], "macro"),
    "증시 유동성":   (["신용융자", "예탁금", "레버리지 ETF", "공매도"], "macro"),
    "코스닥":        (["코스닥"], "macro"),
    "관세·무역":     (["관세", "수출", "무역", "무역수지", "통상"], "macro"),
    "중국":          (["중국", "CXMT", "본토", "홍콩", "위안화"], "macro"),
    "일본":          (["일본", "니케이", "엔화", "BOJ"], "macro"),
}


# ══════════════════════════ 본문 문장 분석 ══════════════════════════

# 문장 앞에 자주 붙는 군더더기 (숫자는 지우지 않는다 — '9월 DRAM…'이 잘리는 것을 방지)
_NOISE_PREFIX = re.compile(r"^(?:[\s\-•·▶️▶◆◇■□▼△▲*※#\]]+|\d{1,2}[\.\)]\s+)+")

# 통째로 버릴 문장 (인사말·구독안내·컴플라이언스 등)
_NOISE_PATTERN = re.compile(
    r"(https?://|t\.me/|텔레그램\s*채널|채널\s*(안내|링크)|구독|보고서\s*원문|자료\s*문의|"
    r"컴플라이언스|준법감시|무단\s*(전재|복제|배포)|배포\s*금지|투자판단의\s*최종|"
    r"본\s*자료는|당사는|감사합니다|안녕하세요|드림$|올림$|좋은\s*하루|"
    r"카카오톡|유튜브|네이버\s*블로그|애널리스트\s*$|\d{2,3}-\d{3,4}-\d{4}|@\w+)"
)

# 근거·촉매가 담긴 표현 (가점)
_SIGNAL_PATTERN = re.compile(
    r"(상회|하회|서프라이즈|쇼크|급등|급락|강세|약세|반등|조정|신고가|신저가|사상\s*최고|"
    r"가이던스|컨센서스|수주|계약|증설|감산|점유율|출하|재고|마진|영업이익|매출|순이익|"
    r"순매수|순매도|수급|외국인|기관|밸류에이션|목표가|가격\s*(인상|인하)|"
    r"금리|환율|유가|발표|예정|전망치|규제|관세|제재|승인|출시|양산|공급|수요|"
    r"상향|하향|둔화|확대|축소|상승|하락|마감|급증|급감|호조|부진|우려|기대)"
)

# 일정·이벤트 신호 — 실제 '행사·발표'를 가리키는 표현만 인정한다
_EVENT_PATTERN = re.compile(
    r"(예정|발표|공개|개최|만기|입찰|연설|회의|공시|상장|배당락|"
    r"FOMC|CPI|PCE|PPI|고용보고서|실적\s*발표|어닝|옵션만기|선물만기|금통위|잭슨홀)"
)
_TIMEWORD_PATTERN = re.compile(r"(오늘|금일|내일|모레|이번\s*주|다음\s*주|장\s*마감\s*후|장\s*시작|새벽)")
_DATE_PATTERN = re.compile(r"(\d{1,2}\s*월\s*\d{1,2}\s*일|\d{1,2}/\d{1,2}|[월화수목금]요일)")
_SCHEDULE_PATTERN = _EVENT_PATTERN   # 하위 호환


def _tidy(line):
    """URL·군더더기 제거 후 한 줄로 정리"""
    line = re.sub(r"https?://\S+", "", line)
    line = _NOISE_PREFIX.sub("", line)
    line = re.sub(r"\s+", " ", line).strip()
    return line


def _cut(text, limit=SENT_MAX_LEN):
    """하위 호환용. 새 코드에서는 clean_cut()을 쓴다."""
    return text if len(text) <= limit else text[:limit].rstrip(" ,·-") + "…"


# 리포트 머리에 붙는 태그  예) [메리츠증권 반도체/디스플레이 김선우]
_TAG_PREFIX = re.compile(r"^\[[^\]]{4,40}\]\s*")
# 종목명(±x%) 나열 — 정보 가치가 낮아 코멘트에 쓰지 않는다
_PRICE_TOKEN = re.compile(r"\(\s*[+\-−▲▼]?\s*\d+(?:\.\d+)?\s*%\s*\)")
# 문장이 깨진 채 시작하는 경우(조사·닫는 괄호로 시작)
_PARTICLE_START = set("는은이가을를도의에와과로며고만")
# 문장이 온전히 끝났는지 판단
_SENT_END = re.compile(r"(다\.?|음\.?|함\.?|요\.?|[.!?…]|기록|전망|예정|발표|계획)$")


def strip_tag(text):
    """앞머리 [증권사 애널리스트] 태그 제거"""
    t = _TAG_PREFIX.sub("", text).strip()
    return t if len(t) >= SENT_MIN_LEN else text.strip()


def is_price_list(sent):
    """'삼성전자(-2.2%), 마이크론(-7%), …' 형태의 시세 나열인지"""
    return len(_PRICE_TOKEN.findall(sent)) >= 3


def is_broken_start(sent):
    """'는(+0.76%) 이번주…'처럼 앞이 잘려 시작하는 문장인지"""
    if not sent:
        return True
    if sent[0] in _PARTICLE_START:
        return True
    return sent[0] in ")]},·"


def clean_cut(text, limit):
    """길면 '문장·절이 끝나는 지점'까지만 남긴다.
       깔끔하게 끊을 수 없으면 None을 돌려 그 문장을 아예 쓰지 않는다.
       → '…'로 잘린 문장이 나가지 않도록 하는 장치."""
    text = text.strip().rstrip(" ,·-")
    if len(text) <= limit:
        return text
    head = text[:limit]
    for pat in ("다. ", "다.", "니다. ", ". ", "며, ", "하고, ", "고, "):
        idx = head.rfind(pat)
        if idx >= limit * 0.45:
            return head[:idx + len(pat)].strip().rstrip(" ,")
    idx = head.rfind(", ")
    if idx >= limit * 0.6:
        return head[:idx].strip()
    return None


# ── 존댓말 → 개조식 변환 (시황 전달용) ──────────────────────
#    "마감했습니다" → "마감",  "부각됐습니다" → "부각됨",  "긍정적입니다" → "긍정적"
_POLITE_RULES = [
    (r"하기로 했습니다", "하기로 결정"), (r"기로 했습니다", "기로 결정"),
    (r"할 예정입니다", "할 예정"), (r"할 계획입니다", "할 계획"),
    (r"하였습니다", ""), (r"했습니다", ""), (r"합니다", ""),
    (r"되었습니다", "됨"), (r"됐습니다", "됨"), (r"됩니다", "됨"),
    (r"이었습니다", ""), (r"였습니다", ""), (r"입니다", ""),
    (r"있습니다", "있음"), (r"없습니다", "없음"),
    (r"겠습니다", "겠음"), (r"습니다", "음"),
    (r"하십시오", ""), (r"십시오", ""), (r"세요", ""),
    (r"드립니다", ""), (r"봅니다", "봄"),
]


def to_plain(text):
    """문장 끝 존댓말을 개조식으로 바꾼다. 문장 중간(…했습니다. …)에도 적용된다."""
    t = text
    for pat, rep in _POLITE_RULES:
        t = re.sub(pat, rep, t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([.,])", r"\1", t)
    return t.rstrip(" ,·-")


def _words(sent):
    return set(w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", sent))


def is_duplicate_of(sent, picked):
    """이미 뽑은 문장들과 내용이 겹치는지"""
    w = _words(sent)
    if not w:
        return True
    for p in picked:
        pw = _words(p)
        if not pw:
            continue
        if len(w & pw) / float(min(len(w), len(pw))) > 0.6:
            return True
    return False


def split_sentences(text):
    """글 본문 전체를 문장 단위로 쪼갠다. (제목 줄만 보지 않는다)"""
    out = []
    for raw in text.split("\n"):
        line = _tidy(raw)
        if not line:
            continue
        if len(line) <= SENT_MAX_LEN:
            out.append(line)
            continue
        for s in re.split(r"(?<=다\.)\s+|(?<=[.!?])\s+|(?<=음\.)\s+", line):
            s = s.strip()
            if s:
                out.append(s)
    return out


# ── 컴플라이언스: 타사 애널리스트의 투자의견·판단은 코멘트에 싣지 않는다 ──
#    (프로젝트 지침 7장. 사실·수치만 사용하고 의견성 문장은 원천 차단한다)
_OPINION_PATTERN = re.compile(
    r"(투자의견|목표주가|목표가|적정주가|매수\s*의견|매도\s*의견|비중\s*(확대|축소)|"
    r"탑픽|톱픽|Top\s?Pick|최선호|차선호|추천\s*(종목|업종)|"
    r"전망합니다|판단합니다|판단됩니다|기대합니다|권고|사야|팔아야|"
    r"BUY|SELL|Overweight|Underweight)", re.I
)

# 필터 집계 — 컴플라이언스 리포트용
FILTER_STATS = {"scanned": 0, "kept": 0, "opinion": 0,
                "price_list": 0, "broken": 0, "boilerplate": 0, "too_short": 0}


def reset_filter_stats():
    for k in FILTER_STATS:
        FILTER_STATS[k] = 0


def is_noise(sent):
    """버려야 할 문장인지 판단. 사유별로 집계해 컴플라이언스 리포트에 쓴다."""
    FILTER_STATS["scanned"] += 1
    if len(sent) < SENT_MIN_LEN or len(sent) > 400:
        FILTER_STATS["too_short"] += 1
        return True
    if _NOISE_PATTERN.search(sent):
        FILTER_STATS["boilerplate"] += 1
        return True
    if _OPINION_PATTERN.search(sent):        # ★ 투자의견성 문장 원천 차단
        FILTER_STATS["opinion"] += 1
        return True
    if is_broken_start(sent):
        FILTER_STATS["broken"] += 1
        return True
    if is_price_list(sent):          # 종목 시세 나열은 코멘트로 쓰지 않는다
        FILTER_STATS["price_list"] += 1
        return True
    if sent.count("(") >= 6:         # 괄호 범벅인 표·나열
        FILTER_STATS["price_list"] += 1
        return True
    # 해시태그·기호만 있는 줄
    if len(re.sub(r"[^가-힣A-Za-z0-9]", "", sent)) < 12:
        FILTER_STATS["too_short"] += 1
        return True
    # 한글 비중이 지나치게 낮은 줄(티커 나열 등)
    hangul = len(re.findall(r"[가-힣]", sent))
    if hangul < 5 and not re.search(r"\d", sent):
        FILTER_STATS["boilerplate"] += 1
        return True
    FILTER_STATS["kept"] += 1
    return False


def score_sentence(sent):
    """매매 참고 가치가 높은 문장에 높은 점수를 준다."""
    score = 0.0
    # 숫자는 '있으면 좋은 것'이지 많을수록 좋은 게 아니다 (나열문 방지 위해 상한을 둔다)
    score += min(3, len(re.findall(r"\d+(?:\.\d+)?\s*%", sent))) * 2.0
    score += min(3, len(re.findall(r"\d[\d,\.]*\s*(?:조|억|만|달러|원|엔|bp|p|배|톤|배럴|단|나노)", sent))) * 2.0
    score += 2.0 * len(set(_SIGNAL_PATTERN.findall(sent)))              # 촉매 표현 종류 수
    if re.search(r"(때문|영향|덕분|따라|여파|기인|배경|덕에|탓에)", sent):   # 인과 설명
        score += 2.5
    if re.search(r"(발표|공시|계획|합의|승인|타결|체결|확정|결정)", sent):   # 확정된 사실
        score += 1.5
    if 30 <= len(sent) <= 110:
        score += 2.0
    if len(sent) > 150:
        score -= 2.0
    if _SENT_END.search(sent):                                          # 문장이 온전히 끝남
        score += 1.5
    # 쉼표로 나열만 이어지는 문장은 감점
    score -= 0.6 * max(0, sent.count(",") - 3)
    score -= 1.5 * len(_PRICE_TOKEN.findall(sent))
    if re.search(r"(전망합니다|판단합니다|추천|비중\s*확대|매수 의견|목표주가|투자의견)", sent):
        score -= 2.0    # 투자의견성 문장은 후순위
    return score


def _norm_key(sent):
    return re.sub(r"[^가-힣A-Za-z0-9]", "", sent)


def _too_similar(a, b):
    if not a or not b:
        return False
    if a[:22] and a[:22] == b[:22]:
        return True
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return False
    return len(sa & sb) / float(len(sa | sb)) > 0.88


def collect_research(hours=RESEARCH_HOURS):
    """모든 구독 채널에서 최근 글 본문을 모은다.
       반환: {표시이름: [본문, ...]}"""
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=hours)
    result = {}
    for label, ch in RESEARCH_CHANNELS:
        msgs = _channel_messages(ch)
        if not msgs:
            continue
        recent = [t for dt, t in msgs if dt is None or dt >= cutoff]
        if not recent:                      # 최근 글이 없으면 마지막 글 1건만
            recent = [msgs[-1][1]]
        result[label] = list(reversed(recent))
    return result


def build_sentence_pool(research):
    """채널 본문 전체 → 정제된 문장 목록 [(점수, 채널, 문장)]"""
    pool, keys = [], []
    for label, texts in research.items():
        for txt in texts:
            for sent in split_sentences(txt):
                sent = strip_tag(sent)
                if is_noise(sent):
                    continue
                key = _norm_key(sent)
                if any(_too_similar(key, k) for k in keys):
                    continue
                keys.append(key)
                pool.append((score_sentence(sent), label, sent))
    pool.sort(key=lambda x: x[0], reverse=True)
    return pool


def match_topics(sent):
    """문장이 어떤 주제에 해당하는지 반환"""
    found = []
    for topic, (words, kind) in TOPIC_KEYWORDS.items():
        if any(w in sent for w in words):
            found.append((topic, kind))
    return found


def group_by_topic(pool):
    """주제별로 {주제: {'kind':.., 'channels': set(), 'sents': [(점수, 채널, 문장)]}}"""
    groups = {}
    for score, label, sent in pool:
        for topic, kind in match_topics(sent):
            g = groups.setdefault(topic, {"kind": kind, "channels": set(), "sents": []})
            g["channels"].add(label)
            g["sents"].append((score, label, sent))
    for g in groups.values():
        g["sents"].sort(key=lambda x: x[0], reverse=True)
    return groups


def build_watch_rows(pool, used_keys, picked_all=None):
    """관심종목 워치리스트 — 내 커버리지 종목이 언급되면 최우선으로 올린다."""
    picked = picked_all if picked_all is not None else []
    rows = []
    for name, words in WATCHLIST:
        best = None
        for score, label, sent in pool:          # pool은 점수 내림차순
            if not any(w in sent for w in words):
                continue
            key = _norm_key(sent)
            if key in used_keys:
                continue
            text = clean_cut(sent, WATCH_LINE_LEN)
            if not text or is_duplicate_of(text, picked):
                continue
            best = (key, text)
            break
        if best:
            used_keys.add(best[0])
            picked.append(best[1])
            rows.append(f"⭐ <b>{esc(name)}</b> — {esc(to_plain(best[1]))}")
        if len(rows) >= WATCH_LINE_COUNT:
            break
    return rows


def build_theme_rows(groups, used_keys, picked_all=None):
    """주요 테마·매크로 이슈: 2곳 이상 채널이 다룬 주제 우선"""
    allt = [(t, g) for t, g in groups.items() if g["kind"] in ("theme", "macro") and g["sents"]]
    common = [(t, g) for t, g in allt if len(g["channels"]) >= COMMON_MIN_CHANNELS]
    common.sort(key=lambda x: (len(x[1]["channels"]), x[1]["sents"][0][0]), reverse=True)

    # 자리가 남으면 단독 언급이라도 점수가 높은 주제로 채운다
    if len(common) < THEME_TOPIC_COUNT:
        solo = [(t, g) for t, g in allt if (t, g) not in common]
        solo.sort(key=lambda x: x[1]["sents"][0][0], reverse=True)
        common += solo[:THEME_TOPIC_COUNT - len(common)]

    picked_all = picked_all if picked_all is not None else []
    rows = []
    for topic, g in common[:THEME_TOPIC_COUNT]:
        picked, seen_ch = [], set()
        for score, label, sent in g["sents"]:
            key = _norm_key(sent)
            if key in used_keys:
                continue
            if label in seen_ch and picked:
                continue          # 되도록 서로 다른 채널 문장을 섞는다
            text = clean_cut(sent, THEME_LINE_LEN)
            if not text or is_duplicate_of(text, picked_all):
                continue
            picked.append(text)
            picked_all.append(text)
            seen_ch.add(label)
            used_keys.add(key)
            if len(picked) >= THEME_LINES_PER_TOPIC:
                break
        if not picked:
            continue
        if rows:
            rows.append("")       # 주제 사이 한 줄 띄우기
        rows.append(f"▸ <b>{esc(topic)}</b>")
        for s in picked:
            rows.append(f"   {esc(to_plain(s))}")
    return rows


def build_stock_rows(groups, used_keys, picked_all=None):
    """개별 종목 코멘트: 숫자·촉매가 담긴 문장만"""
    cands = [(t, g) for t, g in groups.items() if g["kind"] == "stock" and g["sents"]]
    cands.sort(key=lambda x: (x[1]["sents"][0][0], len(x[1]["channels"])), reverse=True)

    picked = picked_all if picked_all is not None else []
    rows = []
    for topic, g in cands:
        for score, label, sent in g["sents"]:
            key = _norm_key(sent)
            if key in used_keys or score < STOCK_MIN_SCORE:
                continue
            # 종목 코멘트는 '무슨 일이 있었는지'가 담긴 완성된 문장이어야 한다
            if len(set(_SIGNAL_PATTERN.findall(sent))) < 2:
                continue
            if not _SENT_END.search(sent.rstrip()):
                continue            # 리포트 제목·머리말은 제외
            text = clean_cut(sent, STOCK_LINE_LEN)
            if not text or is_duplicate_of(text, picked):
                continue
            rows.append(f"· <b>{esc(topic)}</b> — {esc(to_plain(text))}")
            picked.append(text)
            used_keys.add(key)
            break
        if len(rows) >= STOCK_LINE_COUNT:
            break
    return rows


def build_schedule_rows(pool, used_keys, picked_all=None):
    """일정·이벤트 문장 추출"""
    scored = []
    for score, label, sent in pool:
        key = _norm_key(sent)
        if key in used_keys:
            continue
        hits = len(set(_EVENT_PATTERN.findall(sent)))
        if hits == 0:
            continue                      # '발표·예정' 같은 이벤트 표현이 없으면 일정이 아니다
        bonus = 2.0 if _DATE_PATTERN.search(sent) else 0.0
        if _TIMEWORD_PATTERN.search(sent):
            bonus += 2.5
        if hits < 2 and bonus == 0:
            continue
        length_penalty = 2.0 if len(sent) > 120 else 0.0
        scored.append((hits + bonus + score * 0.2 - length_penalty, sent, key))
    scored.sort(key=lambda x: x[0], reverse=True)

    picked = picked_all if picked_all is not None else []
    rows = []
    for _, sent, key in scored:
        text = clean_cut(sent, SCHED_LINE_LEN)
        if not text or is_duplicate_of(text, picked):
            continue
        rows.append(f"· {esc(to_plain(text))}")
        picked.append(text)
        used_keys.add(key)
        if len(rows) >= SCHEDULE_LINE_COUNT:
            break
    return rows


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ══════════════════════════ 성과 계측 (절감시간 · 컴플라이언스) ══════════════════════════
def _load_stats():
    import json
    try:
        with open(STATS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_stats(data):
    import json
    try:
        os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)
        with open(STATS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"[통계 저장 실패] {e}")


def update_stats(sent_count=0, channels=0):
    """실행 1회분 실적을 누적한다. 반환: 갱신된 통계"""
    today = _today_str()
    s = _load_stats()
    s.setdefault("first_run", today)
    s["last_run"] = today
    s["runs"] = s.get("runs", 0) + 1
    s["messages_sent"] = s.get("messages_sent", 0) + 2      # 시황 + 코멘트
    s["channels_scanned"] = s.get("channels_scanned", 0) + channels
    s["sentences_scanned"] = s.get("sentences_scanned", 0) + FILTER_STATS["scanned"]
    s["sentences_used"] = s.get("sentences_used", 0) + sent_count

    f = s.setdefault("filtered", {})
    for k in ("opinion", "price_list", "broken", "boilerplate", "too_short"):
        f[k] = f.get(k, 0) + FILTER_STATS[k]

    s["minutes_saved"] = s.get("minutes_saved", 0) + MANUAL_MINUTES_DAILY
    # 주간 브리핑은 화요일 1회 기준으로 가산
    if datetime.datetime.now().weekday() == BRIEFING_WEEKDAY:
        s["minutes_saved"] += MANUAL_MINUTES_WEEKLY
        s["weekly_briefs"] = s.get("weekly_briefs", 0) + 1

    _save_stats(s)
    return s


def stats_footer(s):
    """코멘트 하단에 넣을 한 줄 요약 (시연·심사용 근거)"""
    if not s:
        return ""
    hours = s.get("minutes_saved", 0) / 60.0
    return (f"오늘 문장 {FILTER_STATS['scanned']}건 검토 · "
            f"컴플라이언스 필터 {FILTER_STATS['opinion']}건 제외 · "
            f"누적 절감 {hours:,.1f}시간({s.get('runs', 0)}회 실행)")


def print_stats_report():
    """`python telegram_market_report.py --stats` 로 호출하는 성과 리포트"""
    s = _load_stats()
    if not s:
        log("[통계] 아직 누적된 실행 기록이 없습니다.")
        return
    f = s.get("filtered", {})
    total_filtered = sum(f.values())
    mins = s.get("minutes_saved", 0)
    lines = [
        "=" * 52,
        "  데일리 시황 에이전트 · 누적 성과 리포트",
        "=" * 52,
        f"  집계 기간      : {s.get('first_run')} ~ {s.get('last_run')}",
        f"  실행 횟수      : {s.get('runs', 0):,}회",
        f"  발송 메시지    : {s.get('messages_sent', 0):,}건",
        f"  주간 브리핑    : {s.get('weekly_briefs', 0):,}건",
        "-" * 52,
        f"  검토 문장      : {s.get('sentences_scanned', 0):,}건",
        f"  채택 문장      : {s.get('sentences_used', 0):,}건",
        f"  필터 제외      : {total_filtered:,}건",
        f"    · 투자의견성  : {f.get('opinion', 0):,}건   ← 컴플라이언스 차단",
        f"    · 시세 나열   : {f.get('price_list', 0):,}건",
        f"    · 문장 손상   : {f.get('broken', 0):,}건",
        f"    · 정형 문구   : {f.get('boilerplate', 0):,}건",
        f"    · 길이 미달   : {f.get('too_short', 0):,}건",
        "-" * 52,
        f"  절감 시간      : {mins:,}분 = {mins/60:,.1f}시간 = {mins/60/8:,.1f} 영업일",
        f"  연 환산        : {MANUAL_MINUTES_DAILY*250 + MANUAL_MINUTES_WEEKLY*52:,}분 "
        f"= {(MANUAL_MINUTES_DAILY*250 + MANUAL_MINUTES_WEEKLY*52)/60:,.0f}시간/년",
        "=" * 52,
    ]
    for ln in lines:
        log(ln)


# ══════════════════════════ 브리핑 백데이터 아카이브 ══════════════════════════

# 주간 브리핑 집계 기준: 지난주 화요일 15:00 ~ 이번주 화요일 15:00
BRIEFING_WEEKDAY = 1     # 0=월 … 1=화
BRIEFING_HOUR = 15       # 마감 시각


def weekly_window(now=None):
    """현재 시점이 속한 집계 창의 (시작일, 종료일)을 반환."""
    now = now or datetime.datetime.now()
    d = now.date()
    ahead = (BRIEFING_WEEKDAY - d.weekday()) % 7
    tue = d + datetime.timedelta(days=ahead)
    if ahead == 0 and now.hour >= BRIEFING_HOUR:
        tue = tue + datetime.timedelta(days=7)
    return tue - datetime.timedelta(days=7), tue


def _today_str():
    return datetime.datetime.now().strftime("%Y-%m-%d")


def archive_channels():
    """구독 채널 원문을 날짜별 파일로 저장하고, 주간 파일에도 누적한다."""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    today = _today_str()
    daily_path = os.path.join(ARCHIVE_DIR, f"{today}.txt")

    existing = ""
    if os.path.exists(daily_path):
        with open(daily_path, encoding="utf-8") as f:
            existing = f.read()

    chunks = []
    for label, ch in ARCHIVE_CHANNELS:
        blocks = _channel_blocks(ch)
        if not blocks:
            continue
        body = []
        for b in blocks:
            t = re.sub(r"\n{3,}", "\n\n", b).strip()
            if len(t) < 15:
                continue
            if t in existing:          # 중복 방지
                continue
            body.append(t)
        if body:
            chunks.append(f"\n{'='*60}\n[{label}] @{ch}\n{'='*60}\n\n" + "\n\n---\n\n".join(body))

    if not chunks:
        return None, 0

    header = "" if existing else f"# {today} 채널 아카이브\n# (내부 브리핑 작성용 참고자료 / 원문 인용 시 출처 표기)\n"
    text = header + "".join(chunks)

    with open(daily_path, "a", encoding="utf-8") as f:
        f.write(text)

    start, end = weekly_window()
    weekly_path = os.path.join(
        ARCHIVE_DIR,
        f"{start.strftime('%m%d')}_{end.strftime('%m%d')}_주간백데이터.txt")
    with open(weekly_path, "a", encoding="utf-8") as f:
        f.write(f"\n\n{'#'*70}\n# {today}\n{'#'*70}\n" + text)

    return weekly_path, sum(len(c) for c in chunks)


def cleanup_archive(keep_days=ARCHIVE_KEEP_DAYS):
    """보관 기간이 지난 아카이브 파일을 삭제한다."""
    if not os.path.isdir(ARCHIVE_DIR):
        return []
    cutoff = datetime.date.today() - datetime.timedelta(days=keep_days)
    removed = []

    for name in os.listdir(ARCHIVE_DIR):
        path = os.path.join(ARCHIVE_DIR, name)
        if not os.path.isfile(path):
            continue

        file_date = None

        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})\.txt$", name)
        if m:
            try:
                file_date = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                file_date = None

        if file_date is None:
            m = re.match(r"^(\d{2})(\d{2})_(\d{2})(\d{2})_", name)
            if m:
                mm, dd = int(m.group(3)), int(m.group(4))
                today = datetime.date.today()
                for yr in (today.year, today.year - 1):
                    try:
                        cand = datetime.date(yr, mm, dd)
                    except ValueError:
                        continue
                    if cand <= today + datetime.timedelta(days=7):
                        file_date = cand
                        break

        if file_date is None:
            m = re.match(r"^(\d{4})-W(\d{2})_", name)
            if m:
                try:
                    file_date = datetime.date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
                except ValueError:
                    file_date = None

        if file_date is None:
            file_date = datetime.date.fromtimestamp(os.path.getmtime(path))

        if file_date < cutoff:
            try:
                os.remove(path)
                removed.append(name)
            except OSError:
                pass

    return removed


# ══════════════════════════ 숫자 해석 ══════════════════════════
def _num(txt):
    """'• KOSPI: 6,170.42 ▼1.39%' → (6170.42, -1.39)"""
    m = re.search(r":\s*([\d,\.]+)[^\d▲▼]*([▲▼])([\d\.]+)%", txt)
    if not m:
        return None, None
    val = float(m.group(1).replace(",", ""))
    chg = float(m.group(3)) * (1 if m.group(2) == "▲" else -1)
    return val, chg


def _find(rows, key):
    for r in rows:
        if r.startswith(f"• {key}:"):
            return _num(r)
    return None, None


def _snap_value(rows, key):
    """스냅샷 한 줄에서 (값, 등락률%) 추출."""
    for r in rows or []:
        if key not in r:
            continue
        body = r.split(":", 1)[-1]
        mv = re.search(r"([\d,]+\.?\d*)", body)
        if not mv:
            continue
        val = float(mv.group(1).replace(",", ""))
        mp = re.search(r"([+\-])([\d\.]+)%\)", body)
        pct = float(mp.group(2)) * (1 if mp.group(1) == "+" else -1) if mp else None
        return val, pct
    return None, None


def _snap_pct(rows, key):
    """'• 필라델피아 반도체: 12,179.26 (+748.91, +6.55%)' → 6.55"""
    for r in rows or []:
        if key in r:
            m = re.search(r"([+\-△▲▼]?[\d\.]+)%\)", r)
            if m:
                try:
                    return float(m.group(1).replace("+", ""))
                except ValueError:
                    return None
    return None


def _snap_raw(rows, key):
    """스냅샷 줄의 본문 문자열 그대로 반환"""
    for r in rows or []:
        if key in r:
            return r.split(":", 1)[-1].strip()
    return None


def make_comment(fx, rate, glob, kr, snap_rows=None):
    """수집된 숫자만으로 전일 시장 정리를 조립한다. (외부 API 불필요)"""
    out = []
    snap_rows = snap_rows or []

    # 1) 환율
    v, c = _find(fx, "USD/KRW")
    if v is not None:
        _, dxy_c = _find(fx, "달러인덱스")
        line = f"· 원/달러 {v:,.1f}원 {'상승' if c >= 0 else '하락'}({c:+.2f}%)"
        if dxy_c is not None:
            same = (c >= 0) == (dxy_c >= 0)
            line += f" — 달러인덱스({dxy_c:+.2f}%)와 {'같은' if same else '반대'} 방향"
        out.append(line)

    # 1-b) 엔·헤알 (신흥국 통화 방향 확인용)
    jpy_v, jpy_c = _find(fx, "USD/JPY")
    brl_v, brl_c = _find(fx, "USD/BRL(헤알)")
    seg_fx = []
    if jpy_v is not None:
        seg_fx.append(f"엔/달러 {jpy_v:,.2f}({jpy_c:+.2f}%)")
    if brl_v is not None:
        seg_fx.append(f"헤알/달러 {brl_v:,.3f}({brl_c:+.2f}%)")
    if seg_fx:
        note = ""
        if brl_c is not None and c is not None:
            same_em = (brl_c >= 0) == (c >= 0)
            note = (" — 원화와 같은 방향, 신흥국 통화 동조"
                    if same_em else " — 원화와 반대 방향, 통화별 차별화")
        out.append("· " + " / ".join(seg_fx) + note)

    # 2) 국내 증시 (+ 외국인 시각 지표)
    ks_v, ks_c = _find(kr, "KOSPI")
    kq_v, kq_c = _find(kr, "KOSDAQ")
    if ks_v is not None and kq_v is not None:
        if (ks_c >= 0) == (kq_c >= 0):
            tone = "동반 상승" if ks_c >= 0 else "동반 하락"
            line = f"· KOSPI {ks_v:,.0f}p({ks_c:+.2f}%)·KOSDAQ {kq_v:,.0f}p({kq_c:+.2f}%) {tone}"
        else:
            lead = "대형주" if ks_c > kq_c else "중소형주"
            line = f"· KOSPI {ks_c:+.2f}% vs KOSDAQ {kq_c:+.2f}%, {lead} 우위"
        msci = _snap_pct(snap_rows, "MSCI 한국지수")
        if msci is not None:
            line += f" / MSCI 한국 ETF {msci:+.2f}%"
        out.append(line)
    elif ks_v is not None:
        out.append(f"· KOSPI {ks_v:,.0f}p({ks_c:+.2f}%)")

    # 3) 해외 증시 (+ 필라델피아 반도체)
    #    마감 스냅샷이 있으면 그 값을 우선 사용한다 (확정 종가 기준)
    sp_c = _snap_pct(snap_rows, "S&P500")
    nq_c = _snap_pct(snap_rows, "NASDAQ")
    if sp_c is None:
        _, sp_c = _find(glob, "S&P500")
    if nq_c is None:
        _, nq_c = _find(glob, "나스닥")
    if sp_c is not None and nq_c is not None:
        if (sp_c >= 0) == (nq_c >= 0):
            tone = "상승" if sp_c >= 0 else "하락"
            lead = "기술주 주도" if abs(nq_c) > abs(sp_c) else "지수 전반"
            line = f"· 미 증시 S&P500 {sp_c:+.2f}%·나스닥 {nq_c:+.2f}% {tone}, {lead}"
        else:
            line = f"· 미 증시 S&P500 {sp_c:+.2f}%·나스닥 {nq_c:+.2f}%로 업종별 차별화"
        sox = _snap_pct(snap_rows, "필라델피아 반도체")
        if sox is not None:
            line += f" / 필라델피아 반도체 {sox:+.2f}%"
        out.append(line)

    # 4) 금리·원자재
    ty_v, ty_c = _find(rate, "미 10년물")
    wti_v, wti_c = _find(rate, "WTI")
    gold_v, gold_c = _find(rate, "금")
    seg = []
    if ty_v is not None:
        seg.append(f"미 10년물 {ty_v:.2f}%({ty_c:+.2f}%)")
    if wti_v is not None:
        seg.append(f"WTI ${wti_v:,.1f}({wti_c:+.2f}%)")
    if gold_v is not None:
        seg.append(f"금 ${gold_v:,.0f}({gold_c:+.2f}%)")
    if seg:
        risk_on = (sp_c is not None and sp_c > 0) and (ks_c is not None and ks_c > 0)
        note = ""
        if gold_c is not None and ty_c is not None and gold_c > 0 and ty_c < 0:
            note = (" — 금리 하락 속 위험자산·금 동반 강세"
                    if risk_on else " — 금리 하락·금 강세로 안전자산 선호")
        elif wti_c is not None and wti_c <= -3:
            note = " — 유가 낙폭 확대"
        elif ty_c is not None and ty_c > 2:
            note = " — 금리 상승 압력 확대"
        out.append("· " + " / ".join(seg) + note)

    return out


def make_headline(fx, glob, kr, snap_rows):
    """한 줄 요약 — 위험선호 방향을 숫자로 판정"""
    sp_c = _snap_pct(snap_rows, "S&P500")
    nq_c = _snap_pct(snap_rows, "NASDAQ")
    if sp_c is None:
        _, sp_c = _find(glob, "S&P500")
    if nq_c is None:
        _, nq_c = _find(glob, "나스닥")
    _, ks_c = _find(kr, "KOSPI")
    krw_v, krw_c = _find(fx, "USD/KRW")

    parts = []
    if sp_c is not None and nq_c is not None:
        if sp_c > 0 and nq_c > 0:
            parts.append("간밤 미 증시는 강세로 마감했습니다")
        elif sp_c < 0 and nq_c < 0:
            parts.append("간밤 미 증시는 약세로 마감했습니다")
        else:
            parts.append("간밤 미 증시는 지수별로 엇갈렸습니다")

    if krw_v is not None:
        parts.append(f"원/달러는 {krw_v:,.1f}원으로 {'올랐습니다' if krw_c >= 0 else '내렸습니다'}")

    if ks_c is not None and sp_c is not None:
        if (ks_c >= 0) != (sp_c >= 0):
            parts.append("국내 증시는 미 증시와 방향이 엇갈렸습니다")
        elif ks_c >= 0:
            parts.append("국내 증시도 같은 방향으로 올랐습니다")
        else:
            parts.append("국내 증시도 같은 방향으로 밀렸습니다")

    return ["· " + ". ".join(parts) + "." ] if parts else []


def make_key_points(fx, rate, glob, kr, snap_rows, theme_rows=None, sched_rows=None):
    """오늘 꼭 알아야 할 것 3가지 — 숫자로 확인되는 사실만 넣는다."""
    pts = []
    snap_rows = snap_rows or []

    # ① 국내 증시 방향 + 오늘 개장 힌트
    _, ks_c = _find(kr, "KOSPI")
    msci = _snap_pct(snap_rows, "MSCI 한국지수")
    k200 = _snap_pct(snap_rows, "KRX KOSPI 200")
    if ks_c is not None:
        line = f"국내 증시 — 전일 KOSPI {ks_c:+.2f}% 마감"
        if msci is not None and k200 is not None:
            gap = msci - k200
            if abs(gap) >= 1:
                line += (f". 야간 MSCI 한국 ETF가 KOSPI200 대비 {gap:+.2f}%p"
                         f" → {'상승' if gap > 0 else '하락'} 갭 출발 가능성")
            else:
                line += ". 야간 한국물 괴리 크지 않음"
        elif msci is not None:
            line += f". 야간 MSCI 한국 ETF {msci:+.2f}%"
        pts.append(line)

    # ② 그날 변동이 가장 컸던 자산
    movers = []
    sox = _snap_pct(snap_rows, "필라델피아 반도체")
    if sox is not None:
        movers.append((abs(sox), f"필라델피아 반도체 {sox:+.2f}% → 국내 반도체 대형주에 "
                                 f"{'상승' if sox > 0 else '하락'} 압력"))
    gold_v, gold_c = _find(rate, "금")
    if gold_c is not None:
        movers.append((abs(gold_c), f"금 온스당 {gold_v:,.0f}달러 {gold_c:+.2f}% → 안전자산 선호 "
                                    f"{'확대' if gold_c > 0 else '축소'} 여부 점검"))
    wti_v, wti_c = _find(rate, "WTI")
    if wti_c is not None:
        movers.append((abs(wti_c), f"WTI 배럴당 {wti_v:,.1f}달러 {wti_c:+.2f}%"))
    krw_v, krw_c = _find(fx, "USD/KRW")
    if krw_c is not None:
        movers.append((abs(krw_c) * 3, f"원/달러 {krw_v:,.1f}원 {krw_c:+.2f}% → 외국인 수급에 직결"))
    if movers:
        movers.sort(key=lambda x: x[0], reverse=True)
        pts.append(movers[0][1])

    # ③ 임박 일정 또는 채널이 가장 많이 다룬 주제
    third = None
    if sched_rows:
        # 되도록 '오늘·내일 예정'인 항목을 고른다
        cand = [re.sub(r"<[^>]+>", "", r).lstrip("· ").strip() for r in sched_rows]
        upcoming = [c for c in cand if _TIMEWORD_PATTERN.search(c) or "예정" in c]
        raw = (upcoming or cand)[0]
        short = clean_cut(raw, 70)
        if short:
            third = short
    if third is None and theme_rows:
        m = re.search(r"<b>([^<]+)</b>", theme_rows[0])
        if m:
            body = None
            for r in theme_rows[1:3]:
                if not r.startswith("▸") and r.strip():
                    body = clean_cut(re.sub(r"<[^>]+>", "", r).strip(), 80)
                    break
            third = (f"최다 언급 주제 — {m.group(1)}"
                     + (f". {body}" if body else ""))
    if third:
        pts.append(third)

    out = []
    for i, p in enumerate(pts[:3], 1):
        out.append(f"{i}. {to_plain(p).rstrip(' .')}")
    return out


def make_open_check(fx, rate, glob, kr, snap_rows):
    """오늘 개장 체크 — 장 시작 전에 바로 참고할 항목만 뽑는다."""
    out = []
    snap_rows = snap_rows or []

    # 1) NDF 환율 → 개장 환율 방향
    ndf = _snap_raw(snap_rows, "NDF 환율")
    if ndf:
        out.append(f"· 환율: {esc(_cut(ndf, 90))}")
    else:
        v, c = _find(fx, "USD/KRW")
        if v is not None:
            out.append(f"· 환율: 원/달러 {v:,.1f}원 ({c:+.2f}%) — 수출주·외국인 수급에 직결")

    # 2) 필라델피아 반도체 → 국내 반도체 대형주
    sox = _snap_pct(snap_rows, "필라델피아 반도체")
    if sox is not None:
        if sox <= -2:
            note = "삼성전자·SK하이닉스 등 반도체 대형주 약세 압력"
        elif sox >= 2:
            note = "반도체 대형주 강세 흐름 기대"
        else:
            note = "반도체 대형주 방향성 제한적"
        out.append(f"· 반도체: 필라델피아 반도체 {sox:+.2f}% — {note}")

    # 3) MSCI 한국 ETF vs KOSPI200 → 외국인 시각·갭
    msci = _snap_pct(snap_rows, "MSCI 한국지수")
    k200 = _snap_pct(snap_rows, "KRX KOSPI 200")
    if msci is not None:
        line = f"· 외국인 시각: MSCI 한국 ETF {msci:+.2f}%"
        if k200 is not None:
            gap = msci - k200
            if abs(gap) >= 1:
                line += f" (KOSPI200 {k200:+.2f}% 대비 {gap:+.2f}%p 괴리 → 갭 등락 가능)"
            else:
                line += f" (KOSPI200 {k200:+.2f}%와 유사)"
        out.append(line)

    # 4) 미 금리 → 성장주/가치주
    ty_v, ty_c = _find(rate, "미 10년물")
    tw_v, _ = _find(rate, "미 2년물")
    if ty_v is not None:
        if ty_c is not None and ty_c <= -1:
            note = "금리 하락 → 성장주·중소형주에 우호적"
        elif ty_c is not None and ty_c >= 1:
            note = "금리 상승 → 고밸류 성장주 부담"
        else:
            note = "금리 변동 제한적"
        line = f"· 금리: 미 10년물 {ty_v:.2f}%"
        if tw_v is not None:
            line += f" / 2년물 {tw_v:.2f}%"
        out.append(line + f" — {note}")

    # 5) 원자재
    wti_v, wti_c = _find(rate, "WTI")
    gold_v, gold_c = _find(rate, "금")
    if wti_v is not None and wti_c is not None and abs(wti_c) >= 1.5:
        out.append(f"· 유가: WTI ${wti_v:,.1f} ({wti_c:+.2f}%) — "
                   f"{'정유·조선 등 에너지 관련주 관심' if wti_c > 0 else '항공·운송 비용 부담 완화'}")
    if gold_v is not None and gold_c is not None and gold_c >= 1.5:
        out.append(f"· 금: ${gold_v:,.0f} ({gold_c:+.2f}%) — 안전자산 선호 확대 신호")

    return out


# ══════════════════════════ 리포트 조립 ══════════════════════════
def collect_market_data():
    """시세 수집 → 리포트 조립에 필요한 값 묶음 반환"""
    snap = fetch_snapshot()
    snap_head, snap_rows = (snap if snap else ("", []))

    fx = [fmt_line(n, *get_price(t), unit=u, digits=d) for n, t, u, d in INDICATORS_FX]
    rate = [fmt_line(n, *get_price(t), unit=u, digits=d) for n, t, u, d in INDICATORS_RATE]
    glob = [fmt_line(n, *get_price(t), unit=u, digits=d) for n, t, u, d in INDICATORS_GLOBAL]

    # yfinance가 부실한 항목은 채널 스냅샷 값으로 보완
    for i, row in enumerate(rate):
        name = row.split(":")[0].replace("• ", "").strip()
        need = row.endswith("-") or "▲0.00%" in row or "▼0.00%" in row
        if not need:
            continue
        key = {"브렌트유": "브렌트유", "미 2년물": "2년물", "미 30년물": "30년물"}.get(name)
        if not key:
            continue
        v, p = _snap_value(snap_rows, key)
        if v is None:
            continue
        unit = "%" if "년물" in name else "$"
        if p is None:
            rate[i] = f"• {name}: {v:,.3f}{unit}" if unit == "%" else f"• {name}: {v:,.2f}{unit}"
        else:
            rate[i] = fmt_line(name, v, p, unit, 3 if unit == "%" else 2)

    kr = get_korea_market()
    return {"fx": fx, "rate": rate, "glob": glob, "kr": kr,
            "snap_head": snap_head, "snap_rows": snap_rows}


def build_market_report(data):
    """1건차 — 시황 데이터"""
    today = datetime.datetime.now().strftime("%Y-%m-%d (%a)")
    L = [f"📊 <b>{today} 데일리 시황</b>"]

    def section(title, rows):
        if not rows:
            return
        L.append("")
        L.append(f"<b>{title}</b>")
        L.extend(rows)

    section("■ 환율", data["fx"])
    section("■ 금리 · 원자재", data["rate"])
    section("■ 해외 증시", data["glob"])
    section("■ 국내 증시", data["kr"])
    if data["snap_rows"]:
        head = f" ({data['snap_head']})" if data["snap_head"] else ""
        section(f"■ 해외 마감 시세{head}", data["snap_rows"])

    L.append("")
    L.append("<i>데이터: Yahoo Finance / 네이버금융 / 공개 텔레그램 채널</i>")
    return "\n".join(L)


def build_comment_report(data, research=None):
    """2건차 — 마켓 코멘트 (증시브리핑 형식)"""
    today = datetime.datetime.now().strftime("%Y-%m-%d (%a)")
    fx, rate, glob, kr = data["fx"], data["rate"], data["glob"], data["kr"]
    snap_rows = data["snap_rows"]

    # ── 채널 본문 전체 분석 ──
    if research is None:
        try:
            research = collect_research()
        except Exception as e:
            log(f"[리서치 수집 실패] {e}")
            research = {}

    watch_rows = []
    try:
        reset_filter_stats()
        pool = build_sentence_pool(research)
        groups = group_by_topic(pool)
        used = set()
        # 뽑는 순서가 곧 우선순위다.
        #  ① 관심종목 ② 일정 ③ 개별 종목 ④ 테마·매크로
        picked_all = []          # 섹션 간 내용 중복 방지용 공용 목록
        watch_rows = build_watch_rows(pool, used, picked_all)
        sched_rows = build_schedule_rows(pool, used, picked_all)
        stock_rows = build_stock_rows(groups, used, picked_all)
        theme_rows = build_theme_rows(groups, used, picked_all)
        log(f"[분석] 문장 {len(pool)}개 / 주제 {len(groups)}개 / "
            f"필터 제외 {FILTER_STATS['scanned'] - FILTER_STATS['kept']}건"
            f"(의견성 {FILTER_STATS['opinion']}건)")
    except Exception as e:
        log(f"[리서치 분석 실패] {e}")
        theme_rows = stock_rows = sched_rows = []

    L = [f"🧭 <b>{today} 마켓 코멘트</b>"]
    DIV = "━━━━━━━━━━━━━━"

    def section(title, rows, divider=True):
        if not rows:
            return
        L.append("")
        if divider:
            L.append(DIV)
        L.append(f"<b>{title}</b>")
        L.extend(rows)

    section("📌 오늘의 핵심",
            make_key_points(fx, rate, glob, kr, snap_rows, theme_rows, sched_rows),
            divider=False)
    section("⭐ 관심종목", watch_rows)
    section("■ 전일 시장", make_comment(fx, rate, glob, kr, snap_rows))
    section("■ 오늘 개장 체크", make_open_check(fx, rate, glob, kr, snap_rows))
    section("■ 일정 · 이벤트", sched_rows)
    section("■ 종목 이슈", stock_rows)
    section("■ 테마 · 매크로", theme_rows)

    # 성과·컴플라이언스 계측 (실패해도 브리핑은 정상 발송)
    try:
        used_cnt = len(watch_rows) + len(sched_rows) + len(stock_rows) + len(theme_rows)
        s = update_stats(sent_count=used_cnt, channels=len(research or {}))
        footer = stats_footer(s)
    except Exception as e:
        log(f"[통계 실패] {e}")
        footer = ""

    L.append("")
    if footer:
        L.append(f"<i>{esc(footer)}</i>")
    L.append("<i>구독 채널 본문 분석 · 사내 참고용. 대외 배포·인용 금지</i>")
    return "\n".join(L)


def build_reports():
    """(시황 메시지, 코멘트 메시지) 두 건을 만든다."""
    data = collect_market_data()
    return build_market_report(data), build_comment_report(data)


# 하위 호환: 예전 이름으로 호출해도 동작하도록
def build_report():
    m, c = build_reports()
    return m + "\n\n" + c


TELEGRAM_LIMIT = 3800    # 텔레그램 1건 제한(4096)보다 여유 있게


def split_message(text, limit=TELEGRAM_LIMIT):
    """줄 단위로 잘라 여러 건으로 나눈다."""
    if len(text) <= limit:
        return [text]
    parts, buf = [], ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > limit and buf:
            parts.append(buf.rstrip())
            buf = ""
        buf += line + "\n"
    if buf.strip():
        parts.append(buf.rstrip())
    total = len(parts)
    return [f"{p}\n\n<i>({i}/{total})</i>" for i, p in enumerate(parts, 1)]


def send_telegram(text, kind="market"):
    """kind='market'|'comment' — 대상별 수신 설정에 따라 발송한다."""
    import time
    flag = "send_market" if kind == "market" else "send_comment"
    targets = [t for t in CHAT_TARGETS if t.get(flag, True)]
    if not targets:
        log(f"[전송 생략] {kind}: 수신 대상 없음")
        return 0

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunks = split_message(text)
    ok, fail = 0, []
    for t in targets:
        cid = t["chat_id"]
        sent = 0
        for chunk in chunks:
            r = None
            try:
                r = requests.post(
                    url,
                    data={"chat_id": cid, "text": chunk,
                          "parse_mode": "HTML", "disable_web_page_preview": True},
                    timeout=20)
                r.raise_for_status()
                sent += 1
                if len(chunks) > 1:
                    time.sleep(1)
            except Exception as e:
                detail = ""
                try:
                    detail = r.text[:200] if r is not None else ""
                except Exception:
                    pass
                fail.append(f"{t['name']}({cid}): {e} {detail}")
                break
        if sent:
            ok += 1

    for f in fail:
        log(f"[전송 실패] {f}")
    if ok == 0:
        raise RuntimeError(f"{kind}: 모든 대상 전송 실패")
    log(f"[전송:{kind}] 대상 {ok}곳 / 메시지 {len(chunks)}건 / 실패 {len(fail)}건")
    return ok


def wait_for_network(max_wait=180):
    """부팅 직후 네트워크가 붙을 때까지 대기"""
    import time
    waited = 0
    while waited < max_wait:
        try:
            requests.get("https://api.telegram.org", timeout=5)
            if waited:
                log(f"[네트워크] {waited}초 대기 후 연결됨")
            return True
        except Exception:
            time.sleep(10)
            waited += 10
    log("[네트워크] 대기 시간 초과 - 그대로 진행")
    return False


def save_sent_brief(market_msg, comment_msg):
    """발송한 브리핑 원문을 날짜별 파일로 남긴다.
       → 개인 메일 발송·월간 회고·고객 상담 근거 자료로 재활용한다."""
    try:
        d = os.path.join(ARCHIVE_DIR, "brief")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{_today_str()}_브리핑.txt")
        plain = lambda t: re.sub(r"<[^>]+>", "", t)
        with open(path, "w", encoding="utf-8") as f:
            f.write(plain(market_msg) + "\n\n" + "=" * 40 + "\n\n" + plain(comment_msg) + "\n")
        log(f"[브리핑 저장] {path}")
        return path
    except Exception as e:
        log(f"[브리핑 저장 실패] {e}")
        return None


def main():
    import time
    try:
        wpath, size = archive_channels()
        if wpath:
            log(f"[아카이브] {size:,}자 저장 -> {wpath}")
        else:
            log("[아카이브] 새로 저장할 내용 없음")
        gone = cleanup_archive()
        if gone:
            log(f"[정리] {ARCHIVE_KEEP_DAYS}일 경과 파일 {len(gone)}개 삭제")
    except Exception as e:
        log(f"[아카이브 실패] {e}")

    data = collect_market_data()

    # 1건차 : 시황 데이터
    market_msg = build_market_report(data)
    log(market_msg)
    send_telegram(market_msg, kind="market")

    time.sleep(2)

    # 2건차 : 마켓 코멘트
    comment_msg = build_comment_report(data)
    log(comment_msg)
    send_telegram(comment_msg, kind="comment")

    # 발송 원문 보관 (개인 메일 발송·월간 회고용)
    save_sent_brief(market_msg, comment_msg)

    log("[OK] 텔레그램 2건 전송 완료")


# ══════════════════════════ 실행 조건 ══════════════════════════
SKIP_WEEKEND = True      # 토·일에는 발송하지 않음
SCHEDULED_HOUR = 6       # 예정 발송 시각 (시)
SCHEDULED_MINUTE = 30    # 예정 발송 시각 (분)
MAX_DELAY_HOURS = 6      # 예정 시각보다 이만큼 늦게 실행되면 발송 생략


def should_run(now=None):
    """지금 발송해야 하는 상황인지 판단한다."""
    now = now or datetime.datetime.now()

    if SKIP_WEEKEND and now.weekday() >= 5:
        return False, f"주말({'월화수목금토일'[now.weekday()]}요일) - 발송 생략"

    scheduled = now.replace(hour=SCHEDULED_HOUR, minute=SCHEDULED_MINUTE,
                            second=0, microsecond=0)
    if now > scheduled:
        delay = (now - scheduled).total_seconds() / 3600
        if delay > MAX_DELAY_HOURS:
            return False, f"예정 시각보다 {delay:.1f}시간 지연 - 발송 생략"

    return True, ""


if __name__ == "__main__":
    import time, traceback
    log(f"\n{'='*55}")
    log(f"[START] {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    log(f"{'='*55}")

    if "--stats" in sys.argv:          # 누적 성과 리포트만 출력하고 종료
        print_stats_report()
        sys.exit(0)

    if not check_credentials():        # 봇 토큰·채팅방 번호 확인
        log("[END] 설정 누락으로 종료")
        sys.exit(1)

    force = "--force" in sys.argv
    ok_to_run, reason = should_run()
    if not ok_to_run and not force:
        log(f"[생략] {reason}")
        log("[END] 종료")
        sys.exit(0)
    if force and not ok_to_run:
        log(f"[강제실행] {reason}")

    try:
        wait_for_network()
        for attempt in range(1, 4):
            try:
                main()
                log("[END] 정상 종료")
                break
            except Exception as e:
                log(f"[실패 {attempt}/3] {type(e).__name__}: {e}")
                log(traceback.format_exc())
                if attempt < 3:
                    time.sleep(30)
                else:
                    log("[중단] 3회 시도 후 포기")
                    sys.exit(1)
    except SystemExit:
        raise
    except BaseException as e:
        log(f"[치명적 오류] {type(e).__name__}: {e}")
        log(traceback.format_exc())
        sys.exit(1)
