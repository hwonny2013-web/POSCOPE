"""
POSCOPE Crawler
POSCO INTERNATIONAL 글로벌 비즈니스 기회 자동 수집기

4개 사업본부(철강/소재바이오/에너지사업/가스사업) 전체에 걸쳐 협업·판매
가능성이 있는 기회를 수집한다. 정식 PJT뿐 아니라 오프테이크·현물거래·RFQ 같은
대형 INQUIRY(문의)성 기회도 kind="INQ"로 함께 수집 대상이 된다.

소스 (모두 실패해도 서로 영향 없이 try/except로 격리됨):
- Google News RSS (본부 4개 x 일반/INQ 키워드, 한글+영문)
- 해외건설협회 공지, KOICA ODA 포털
- World Bank 진행중(Active) 프로젝트 / 조달공고 공개 API
- 업계 전문지 RSS (config.json sources.industry_rss — 건설/곡물/LNG/가스 업계지 기본 제공)
- 지역별 정부/국제기구 조달 포털 (config.json sources.regional_portals)
- GPT(있으면) 또는 키워드 규칙으로 본부/세부사업/PJT·INQ 구분 + 요약

한계: Platts·Argus·MEED·ENR·GAFTA 등 유료 구독 기반 트레이드 인텔리전스는
공개 API/RSS가 없어 이 크롤러로는 수집할 수 없다. 그런 소스는 본부 담당자가
직접 확인 후 수동입력으로 등록하는 것이 정확하다.

새 소스의 URL/선택자는 실제 네트워크 환경에서 1회 실행해보고 0건이 나오면
config.json 또는 이 파일의 해당 함수를 조정해야 할 수 있다.
"""

import json, os, re, sys
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.parse import quote
from urllib.error import URLError
import xml.etree.ElementTree as ET

import db

# ── 설정 ──────────────────────────────────────────────────
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print("[경고] config.json 없음. OpenAI API 없이 실행합니다.")
        return {}
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)

# ── 1. Google News RSS 수집 ──────────────────────────────
# 본부별(철강/소재바이오/에너지사업/가스사업) 검색 키워드.
# 정식 발주/입찰뿐 아니라 오프테이크·현물거래·RFQ 같은 INQ성 키워드도 함께 검색해
# "비단 PJT가 아니어도" 잡히는 기회를 넓힌다.
STEEL_NEWS_KEYWORDS = [
    # 에너지인프라강재(건설/인프라용 강재) — 기존 주력 영역
    "해외건설 발주", "건설 프로젝트 입찰", "ODA 건설 발주", "철강재 해외공사",
    "해외 인프라 프로젝트", "해상풍력 발주", "교량 건설 발주",
    "항만 확장 프로젝트", "철도 건설 프로젝트", "철강 장기공급계약 문의",
    "construction project steel bid", "overseas infrastructure tender",
    "offshore wind project steel", "bridge construction tender",
    "port expansion project steel", "steel long-term supply inquiry",
    # 자동차소재 · 모빌리티(구동모터코아/전기강판)
    "자동차강판 공급계약", "구동모터코아 공장 증설", "전기강판 공급계약",
    "automotive steel supply deal", "motor core plant expansion", "electrical steel supply contract",
]
MATERIALS_NEWS_KEYWORDS = [
    # 식량사업 (곡물·팜유 트레이딩)
    "곡물 수출 계약", "곡물 터미널 발주", "팜오일 플랜트 투자", "곡물 오프테이크 계약",
    "농산물 트레이딩 계약", "곡물 엘리베이터 건설",
    "grain export deal", "grain terminal tender", "palm oil plant investment",
    "grain offtake agreement",
    # 원료소재 (이차전지 소재·핵심광물)
    "이차전지 소재 공급계약", "흑연 광산 지분 투자", "리튬 니켈 공급계약", "희토류 공급계약",
    "battery materials supply deal", "graphite mine investment", "rare earth supply agreement",
    # 산업소재 (화섬/합성수지/비료/암모니아/SAF 등 케미컬)
    "비료공장 발주", "암모니아 생산설비 투자", "지속가능항공유 SAF 공급계약", "생분해 플라스틱 공급계약",
    "fertilizer plant contract", "ammonia plant investment", "SAF supply agreement",
    "biodegradable plastic supply deal",
]
ENERGY_NEWS_KEYWORDS = [
    # LNG사업/터미널사업 (트레이딩 · 현물 · 벙커링)
    "LNG 터미널 계약", "LNG 현물 카고 거래", "LNG 벙커링 계약", "LNG 직수입 계약",
    "LNG terminal investment", "LNG spot cargo deal", "LNG bunkering contract",
    # 발전사업개발 (태양광·해상풍력·CCS·수소암모니아)
    "발전소 건설 발주", "신재생에너지 발주", "수소 암모니아 사업", "탄소포집 CCS 사업",
    "power plant EPC contract", "renewable energy project tender",
    "hydrogen ammonia project", "carbon capture CCS project",
]
GAS_NEWS_KEYWORDS = [
    # E&P · 가스개발 · 가스전운영
    "가스전 탐사 계약", "가스전 개발 투자", "해상 광구 탐사권 확보", "가스 공동조사 협약",
    "gas exploration contract", "offshore block farm-in", "upstream gas asset acquisition",
    "gas joint study agreement",
]
KEYWORDS = STEEL_NEWS_KEYWORDS + MATERIALS_NEWS_KEYWORDS + ENERGY_NEWS_KEYWORDS + GAS_NEWS_KEYWORDS

def extract_source_from_title(title):
    """Google News RSS 제목은 보통 '헤드라인 - 매체명' 형태라 매체명을 분리해낼 수 있다."""
    m = re.search(r" - ([^-]{2,40})$", title)
    return m.group(1).strip() if m else "Google News"


def fetch_google_news(keyword, max_items=6):
    encoded = quote(keyword)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=10) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        results = []
        for item in items[:max_items]:
            title = item.findtext("title", "").strip()
            link  = item.findtext("link",  "").strip()
            pub   = item.findtext("pubDate", "").strip()
            desc  = item.findtext("description", "").strip()
            desc  = re.sub(r"<[^>]+>", "", desc)[:200]
            if title:
                results.append({
                    "title": title, "link": link,
                    "published": pub[:16], "summary": desc,
                    "source": extract_source_from_title(title),
                    "keyword": keyword,
                })
        return results
    except Exception as e:
        print(f"  [News] '{keyword}' 수집 실패: {e}")
        return []

# ── 2. 게시판형 소스 (해외건설협회 / KOICA / 지역 포털 공통) ──
def fetch_board_notices(url, source_name, max_items=8):
    """제목 목록 위주의 게시판 HTML에서 공고 제목을 정규식으로 추출하는 범용 파서.
    사이트 구조가 다르면 0건이 나올 수 있으며, 그 경우 해당 사이트의 실제 HTML을
    확인해 정규식을 조정해야 한다."""
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        patterns = [
            r'class="subject"[^>]*>\s*<a[^>]*>([^<]+)<',
            r'<a[^>]*class="[^"]*(?:subject|tit|title)[^"]*"[^>]*>([^<]+)</a>',
            r'<td[^>]*class="[^"]*subject[^"]*"[^>]*>\s*<a[^>]*>([^<]+)</a>',
        ]
        titles = []
        for p in patterns:
            titles = re.findall(p, html)
            if titles:
                break
        results = []
        for t in titles[:max_items]:
            t = t.strip()
            if t:
                results.append({"title": t, "source": source_name,
                                 "published": datetime.now().strftime("%Y-%m-%d"), "summary": ""})
        return results
    except Exception as e:
        print(f"  [{source_name}] 수집 실패: {e}")
        return []

# ── 3. 업계 전문지 RSS (config.json sources.industry_rss) ────
def fetch_rss(url, source_name, max_items=8):
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=10) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        results = []
        for item in items[:max_items]:
            title = (item.findtext("title", "") or "").strip()
            link = (item.findtext("link", "") or "").strip()
            desc = (item.findtext("description", "") or item.findtext("summary", "") or "").strip()
            desc = re.sub(r"<[^>]+>", "", desc)[:200]
            if title:
                results.append({"title": title, "link": link, "summary": desc,
                                 "source": source_name,
                                 "published": datetime.now().strftime("%Y-%m-%d")})
        return results
    except Exception as e:
        print(f"  [{source_name}] RSS 수집 실패: {e}")
        return []

# ── 4. World Bank 공개 API (진행중 프로젝트 / 조달공고) ──────
def _wb_records(data, key):
    val = data.get(key)
    if isinstance(val, dict):
        return list(val.values())
    if isinstance(val, list):
        return val
    return []

def fetch_worldbank_projects(rows=50):
    """World Bank 'Active'(진행중) 프로젝트 목록 공개 API."""
    url = f"https://search.worldbank.org/api/v3/projects?format=json&status=Active&rows={rows}"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = []
        for rec in _wb_records(data, "projects"):
            title = rec.get("project_name") or rec.get("projectname") or ""
            if not title:
                continue
            country = rec.get("countryname")
            if isinstance(country, list):
                country = ", ".join(country)
            summary = (rec.get("pdo") or rec.get("project_abstract") or "")
            if isinstance(summary, str):
                summary = re.sub(r"<[^>]+>", "", summary)[:200]
            else:
                summary = ""
            results.append({
                "title": title, "summary": summary,
                "country": country or "", "link": rec.get("url", ""),
                "source": "World Bank (진행중 프로젝트)",
                "published": str(rec.get("boardapprovaldate", ""))[:10],
            })
        return results
    except Exception as e:
        print(f"  [World Bank Projects] 수집 실패: {e}")
        return []

def fetch_worldbank_procurement(rows=50):
    """World Bank 조달공고(Procurement Notices) 공개 API."""
    url = f"https://search.worldbank.org/api/v3/procnotices?format=json&rows={rows}"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = []
        for rec in _wb_records(data, "procnotices"):
            title = rec.get("notice_title") or rec.get("notice_text") or rec.get("project_name") or ""
            if not title:
                continue
            results.append({
                "title": title,
                "summary": rec.get("project_name", "") or "",
                "country": rec.get("country", "") or "",
                "link": rec.get("url", ""),
                "source": "World Bank (조달공고)",
                "published": str(rec.get("noticedate") or rec.get("submission_date") or "")[:10],
            })
        return results
    except Exception as e:
        print(f"  [World Bank Procurement] 수집 실패: {e}")
        return []

# ── 5. 본부/세부사업 분류 및 PJT·INQ 구분 ──────────────────
# 4개 본부(철강/소재바이오/에너지사업/가스사업) 모두 동등하게 탐지 대상.
# "가스전 개발/E&P"는 LNG·발전(에너지사업)과 조직상 별도인 가스사업본부 소관이므로
# energy보다 먼저 매칭을 시도해 가스전 관련 기사가 energy로 오분류되지 않게 한다.
DIV_KEYWORDS = {
    "gas": ["가스전", "e&p", "탐사시추", "광구", "gas field", "exploration block",
            "upstream gas", "farm-in"],
    "steel": ["형강", "후판", "강관", "철강", "철골", "강재", "h형강",
              "각형강관", "데크", "plate", "steel", "structural", "교량", "철도",
              "항만", "인프라", "구동모터코아", "모터코아", "전기강판", "motor core",
              "electrical steel"],
    "materials": ["곡물", "비료", "팜오일", "팜유", "이차전지", "양극재", "음극재",
                  "흑연", "리튬", "니켈", "희토류", "바이오디젤", "농산물", "사일로",
                  "엘리베이터", "암모니아 생산", "saf", "생분해", "화섬", "합성수지",
                  "grain", "fertilizer", "palm oil", "battery material", "biodiesel",
                  "rare earth", "graphite"],
    "energy": ["lng", "가스", "정유", "발전소", "신재생", "해상풍력", "수소", "암모니아",
               "원유", "ccs", "탄소포집", "벙커링", "gas field", "power plant", "renewable",
               "hydrogen", "ammonia", "oil refinery", "bunkering", "carbon capture"],
}

SUB_BUSINESS_KEYWORDS = {
    "steel": {
        "모빌리티사업": ["구동모터코아", "모터코아", "motor core"],
        "자동차소재사업": ["자동차강판", "차체용강판", "automotive steel"],
        "스테인리스사업": ["스테인리스", "stainless"],
        "냉연사업": ["냉연", "cold rolled"],
        "후판선재사업": ["후판", "선재", "plate", "wire rod"],
        "열연조강사업": ["열연", "hot rolled"],
        "에너지인프라강재사업": ["교량", "항만", "철도", "인프라", "발전소 강재", "lng탱크"],
    },
    "materials": {
        "원료소재사업": ["이차전지", "양극재", "음극재", "흑연", "리튬", "니켈", "희토류",
                     "battery material", "rare earth", "graphite", "리사이클링"],
        "산업소재사업": ["비료", "암모니아 생산", "saf", "생분해", "화섬", "합성수지",
                     "합성고무", "인광석", "fertilizer", "ammonia plant", "plastic"],
        "식량사업": ["곡물", "팜오일", "팜유", "옥수수", "밀", "대두", "쌀", "grain",
                  "palm oil", "wheat", "corn", "soybean"],
    },
    "energy": {
        "LNG사업": ["lng 트레이딩", "카고", "cargo", "lng trading", "lng spot", "벙커링", "bunkering"],
        "터미널사업": ["터미널", "재기화", "terminal", "regasification"],
        "발전사업개발": ["발전소", "태양광", "해상풍력", "풍력", "solar", "offshore wind",
                     "power plant", "renewable"],
        "에너지운영": ["ccs", "탄소포집", "수소", "암모니아", "hydrogen", "carbon capture"],
    },
    "gas": {
        "E&P사업": ["e&p", "탐사", "exploration", "farm-in", "광구"],
        "가스개발사업": ["가스개발", "gas field development", "가스 생산"],
        "가스전운영": ["가스전 운영", "생산설비"],
    },
}

INQ_KEYWORDS = [
    "문의", "rfq", "request for quotation", "오프테이크", "offtake", "스팟", "spot cargo",
    "공동조사", "joint study", "검토 중", "협의 중", "타진",
]

# ── 7. 카드 제목 단순화 ────────────────────────────────────
# 원본 기사 제목을 그대로 노출하면 매체마다 어투/길이가 달라 목록이 너저분해진다.
# "{국가} {세부사업 토픽} {프로젝트|INQ}" 형태로 통일해 한눈에 훑을 수 있게 만든다.
# 원문 제목/요약은 aiSummary에 보존되고 link로 원문에 접근할 수 있다.
COUNTRY_KEYWORDS = {
    "이집트": "이집트", "egypt": "이집트",
    "베트남": "베트남", "vietnam": "베트남",
    "인도네시아": "인도네시아", "indonesia": "인도네시아",
    "인도": "인도", "india": "인도",
    "사우디아라비아": "사우디아라비아", "사우디": "사우디아라비아",
    "saudi arabia": "사우디아라비아", "saudi": "사우디아라비아",
    "uae": "UAE", "아랍에미리트": "UAE", "dubai": "UAE", "두바이": "UAE",
    "카타르": "카타르", "qatar": "카타르",
    "말레이시아": "말레이시아", "malaysia": "말레이시아",
    "필리핀": "필리핀", "philippines": "필리핀",
    "태국": "태국", "thailand": "태국",
    "브라질": "브라질", "brazil": "브라질",
    "멕시코": "멕시코", "mexico": "멕시코",
    "아르헨티나": "아르헨티나", "argentina": "아르헨티나",
    "콜롬비아": "콜롬비아", "colombia": "콜롬비아",
    "페루": "페루", "peru": "페루",
    "파나마": "파나마", "panama": "파나마",
    "호주": "호주", "australia": "호주",
    "나이지리아": "나이지리아", "nigeria": "나이지리아",
    "모로코": "모로코", "morocco": "모로코",
    "알제리": "알제리", "algeria": "알제리",
    "남아공": "남아공", "south africa": "남아공",
    "케냐": "케냐", "kenya": "케냐",
    "탄자니아": "탄자니아", "tanzania": "탄자니아",
    "러시아": "러시아", "russia": "러시아",
    "우크라이나": "우크라이나", "ukraine": "우크라이나",
    "튀르키예": "튀르키예", "turkey": "튀르키예",
    "폴란드": "폴란드", "poland": "폴란드",
    "독일": "독일", "germany": "독일",
    "영국": "영국", "britain": "영국", "united kingdom": "영국",
    "캐나다": "캐나다", "canada": "캐나다",
    "미국": "미국", "united states": "미국", "usa": "미국",
    "중국": "중국", "china": "중국",
    "일본": "일본", "japan": "일본",
    "싱가포르": "싱가포르", "singapore": "싱가포르",
    "파키스탄": "파키스탄", "pakistan": "파키스탄",
    "방글라데시": "방글라데시", "bangladesh": "방글라데시",
    "미얀마": "미얀마", "myanmar": "미얀마",
    "카자흐스탄": "카자흐스탄", "kazakhstan": "카자흐스탄",
    "모잠비크": "모잠비크", "mozambique": "모잠비크",
    "이라크": "이라크", "iraq": "이라크",
    "오만": "오만", "oman": "오만",
    "쿠웨이트": "쿠웨이트", "kuwait": "쿠웨이트",
    "인도네시아어": "인도네시아",
    "한국": "국내", "korea": "국내",
}

def detect_country(text):
    """텍스트에서 국가명을 찾아 표준 한글 국가명으로 반환. 없으면 빈 문자열."""
    text_lower = (text or "").lower()
    for kw, canon in COUNTRY_KEYWORDS.items():
        if kw in text_lower:
            return canon
    return ""


# 원문 헤드라인의 정보(국가·발주처·품목 등)는 최대한 살리고, "[단독]" 같은
# 클릭베이트 태그나 끝에 붙는 매체명만 정리해서 카드 제목으로 쓴다.
# (완전히 새로 짧게 재구성하면 오히려 정보가 빠져 보인다는 피드백을 반영.)
_LEADING_TAG_RE = re.compile(r"^(\[[^\]]{1,12}\]|\([^)]{1,10}\))\s*")


def strip_source_suffix(title, source):
    """제목 끝의 ' - 매체명' / ' | 매체명'을 제거한다. source가 실제 끝부분과
    정확히 일치할 때만 지워서, 본문 정보를 잘못 잘라내는 일이 없게 한다."""
    if not source:
        return title
    pattern = re.compile(r"\s*[-|]\s*" + re.escape(source) + r"\s*$")
    return pattern.sub("", title).strip()


def clean_headline(title, max_len=80):
    t = (title or "").strip()
    while True:
        stripped = _LEADING_TAG_RE.sub("", t).strip()
        if stripped == t:
            break
        t = stripped
    t = re.sub(r"\s+", " ", t)
    if len(t) > max_len:
        t = t[:max_len].rstrip() + "…"
    return t or (title or "").strip()


def prefix_country(title, country):
    """헤드라인에 국가명이 안 보이면 앞에 [국가]를 붙여 한눈에 구분되게 한다.
    '해외'는 국가를 못 찾았다는 뜻일 뿐 정보가 아니라서 붙이지 않는다."""
    if country and country != "해외" and country not in title:
        return f"[{country}] {title}"
    return title


def build_clean_title(original_title, source, country):
    cleaned = clean_headline(strip_source_suffix(original_title, source))
    return prefix_country(cleaned, country)

def classify_div(text):
    """본부 키워드 매칭 결과를 반환. 매칭이 없으면 None."""
    text_lower = text.lower()
    for div in ("gas", "steel", "materials", "energy"):
        if any(kw.lower() in text_lower for kw in DIV_KEYWORDS[div]):
            return div
    return None

def classify_sub_business(div, text):
    """선택된 본부 내에서 세부사업 키워드 매칭. 매칭 없으면 빈 문자열."""
    text_lower = text.lower()
    for sub, kws in SUB_BUSINESS_KEYWORDS.get(div, {}).items():
        if any(kw.lower() in text_lower for kw in kws):
            return sub
    return ""

def classify_kind(text):
    """정식 PJT/발주 공고가 아니라 문의·오프테이크·현물거래성 기사면 INQ로 분류."""
    text_lower = text.lower()
    return "INQ" if any(kw.lower() in text_lower for kw in INQ_KEYWORDS) else "PJT"

def gpt_analyze_batch(batch, api_key):
    try:
        import urllib.request
        import json as _json
        texts = "\n".join([
            f"{i+1}. {a['title']}" + (f" — {a['summary']}" if a.get("summary") else "")
            for i, a in enumerate(batch)
        ])
        prompt = f"""당신은 포스코인터내셔널의 4개 사업본부와 협업·판매 가능성이 있는 글로벌 비즈니스 기회를 선별하는 애널리스트입니다.
다음 뉴스/공고 목록에서 아래 4개 본부 중 하나라도 관련된 항목만 선별하여 JSON으로 반환하세요. 정식 발주/입찰(PJT)뿐 아니라
오프테이크·현물거래·RFQ·공동조사 같은 문의(INQ)성 기회도 동등하게 포함하세요.

- steel (철강본부): 열연/후판/냉연/스테인리스 등 강재 트레이딩, 에너지·인프라용 강재(건설/교량/항만 등), 자동차소재, 모빌리티(구동모터코아·전기강판)
- materials (소재바이오본부): 원료소재(이차전지 소재·핵심광물·희토류·흑연), 식량사업(곡물·팜유 트레이딩), 산업소재(화섬·합성수지·비료·암모니아·SAF 등 케미컬)
- energy (에너지사업본부): LNG 트레이딩·터미널, 발전사업개발(태양광·해상풍력), CCS·수소·암모니아 등 에너지 운영
- gas (가스사업본부): 가스전 E&P(탐사·개발·생산), 가스개발사업, 가스전운영

뉴스 목록:
{texts}

반환 형식 (JSON 배열):
[{{"index": 1, "div": "steel", "subBusiness": "에너지인프라강재사업", "kind": "PJT", "country": "국가명", "owner": "발주처/거래선", "title": "심플한 카드 제목(예: 이집트 LNG터미널 프로젝트, 20자 이내)", "summary": "50자 이내 한국어 요약", "steel": "예상 품목(강재/소재/에너지 품목)", "tons": "예상 물량"}}]

div는 "steel", "materials", "energy", "gas" 중 하나. kind는 정식 발주/계약이면 "PJT", 문의·오프테이크·현물·공동조사 단계면 "INQ".
subBusiness는 해당 본부의 세부사업명(위 설명 참고, 모르면 빈 문자열). 4개 본부 중 어디에도 해당하지 않으면 제외.
title은 매체명이나 "[단독]" 같은 클릭베이트성 태그만 정리하고, 국가·발주처·품목 등
원문 헤드라인에 있던 핵심 정보는 생략하지 말고 살려서 60자 이내로 작성.
관련 없으면 빈 배열 [] 반환."""

        payload = _json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 1500
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {api_key}"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read())
        content = data["choices"][0]["message"]["content"].strip()
        content = re.sub(r"```json\s*|\s*```", "", content).strip()
        parsed = _json.loads(content)
        results = []
        for item in parsed:
            idx = item.get("index", 1) - 1
            if 0 <= idx < len(batch):
                orig = batch[idx]
                div = item.get("div", "steel")
                sub_business = item.get("subBusiness", "")
                kind = item.get("kind", "PJT")
                country = item.get("country") or orig.get("country") or detect_country(orig["title"]) or "해외"
                clean_title = (item.get("title") or "").strip() or build_clean_title(orig["title"], orig.get("source", ""), country)
                summary = item.get("summary", "")
                ai_summary = orig["title"]
                if summary and summary != orig["title"]:
                    ai_summary = f"{orig['title']} — {summary}"
                results.append({
                    "title": clean_title,
                    "div": div,
                    "subBusiness": sub_business,
                    "kind": kind,
                    "country": country,
                    "region": country,
                    "owner": item.get("owner", "미상"),
                    "steel": item.get("steel", ""),
                    "tons": item.get("tons", ""),
                    "size": "",
                    "aiSummary": ai_summary[:200],
                    "source": orig.get("source", "자동수집"),
                    "sourceDate": datetime.now().strftime("%Y-%m-%d"),
                    "deadline": "",
                    "link": orig.get("link", ""),
                })
        return results
    except Exception as e:
        print(f"  [GPT] 분석 실패: {e}")
        return []

def gpt_analyze(articles, api_key, chunk_size=15):
    """소스가 많아져도 전체 기사를 청크 단위로 빠짐없이 분석."""
    results = []
    for i in range(0, len(articles), chunk_size):
        chunk = articles[i:i + chunk_size]
        results.extend(gpt_analyze_batch(chunk, api_key))
    return results

def rule_based_filter(articles):
    results = []
    for a in articles:
        text = a.get("title", "") + " " + a.get("summary", "")
        div = classify_div(text)
        if not div:
            continue
        sub_business = classify_sub_business(div, text)
        kind = classify_kind(text)
        country = a.get("country") or detect_country(text) or "해외"
        summary = a.get("summary", "").strip()
        original_title = a["title"]
        ai_summary = original_title
        if summary and summary != original_title:
            ai_summary = f"{original_title} — {summary}"
        results.append({
            "title": build_clean_title(original_title, a.get("source", ""), country),
            "div": div,
            "subBusiness": sub_business,
            "kind": kind,
            "country": country,
            "region": country,
            "owner": "",
            "steel": "",
            "tons": "",
            "size": "",
            "aiSummary": ai_summary[:200],
            "source": a.get("source", "뉴스"),
            "sourceDate": datetime.now().strftime("%Y-%m-%d"),
            "deadline": "",
            "link": a.get("link", ""),
        })
    return results

# ── 6. 결과 저장 (SQLite) ──────────────────────────────
def save_to_db(items):
    """이미 DB에 있는 항목을 제외하고 새 항목만 적재. 추가된 건수를 반환.
    제목을 단순화하면 서로 다른 기사가 같은 제목으로 겹칠 수 있어, link가 있으면
    link 기준으로(없으면 제목 기준으로) 중복을 판단한다."""
    added = 0
    for item in items:
        link = item.get("link", "")
        if link:
            if db.link_exists(link):
                continue
        elif db.title_exists(item["title"]):
            continue
        db.insert_project({
            "title": item["title"],
            "div": item.get("div", "steel"),
            "sub_business": item.get("subBusiness", ""),
            "kind": item.get("kind", "PJT"),
            "country": item.get("country", item.get("region", "해외")),
            "region": item.get("region", item.get("country", "해외")),
            "owner": item.get("owner", ""),
            "size": item.get("size", ""),
            "steel": item.get("steel", ""),
            "tons": item.get("tons", ""),
            "deadline": item.get("deadline", ""),
            "urgency": False,
            "is_auto": True,
            "is_new": True,
            "source": item.get("source", "자동수집"),
            "source_date": item.get("sourceDate", datetime.now().strftime("%Y-%m-%d")),
            "ai_summary": item.get("aiSummary", ""),
            "link": item.get("link", ""),
        }, sf_history=[])
        added += 1
    return added

# ── 수집 파이프라인 ────────────────────────────────────────
def collect():
    config = load_config()
    api_key = config.get("openai_api_key", "")
    src_cfg = config.get("sources", {})

    all_articles = []

    print("\n[1/4] Google News RSS 수집 중...")
    for kw in KEYWORDS:
        articles = fetch_google_news(kw, max_items=6)
        all_articles.extend(articles)
        print(f"  → '{kw}': {len(articles)}건")

    print("\n[2/4] 해외건설협회 / KOICA ODA / 지역 조달포털 수집 중...")
    icak = fetch_board_notices("https://www.icak.or.kr/nou/noticeList.do", "해외건설협회")
    all_articles.extend(icak)
    print(f"  → 해외건설협회: {len(icak)}건")

    koica_url = src_cfg.get("koica_oda_url") or "https://www.koica.go.kr/koica_kr/945/subview.do"
    koica = fetch_board_notices(koica_url, "KOICA ODA")
    all_articles.extend(koica)
    print(f"  → KOICA ODA: {len(koica)}건")

    for portal in src_cfg.get("regional_portals", []):
        notices = fetch_board_notices(portal.get("url", ""), portal.get("name", "지역 조달포털"))
        all_articles.extend(notices)
        print(f"  → {portal.get('name')}: {len(notices)}건")

    print("\n[3/4] World Bank 공개 데이터 / 업계 RSS 수집 중...")
    wb_projects = fetch_worldbank_projects()
    all_articles.extend(wb_projects)
    print(f"  → World Bank 진행중 프로젝트: {len(wb_projects)}건")
    wb_proc = fetch_worldbank_procurement()
    all_articles.extend(wb_proc)
    print(f"  → World Bank 조달공고: {len(wb_proc)}건")

    for rss_url in src_cfg.get("industry_rss", []):
        items = fetch_rss(rss_url, "업계전문지")
        all_articles.extend(items)
        print(f"  → {rss_url}: {len(items)}건")

    seen, unique = set(), []
    for a in all_articles:
        k = db.normalize_title(a["title"])
        if k and k not in seen:
            seen.add(k); unique.append(a)
    print(f"\n  총 {len(unique)}건 (중복 제거 후, 원본 {len(all_articles)}건)")

    print("\n[4/4] 본부(철강/소재바이오/에너지사업/가스사업) 및 세부사업 분석 중...")
    if api_key and api_key != "your-openai-api-key-here":
        print(f"  → GPT 분석 사용 ({len(unique)}건, {(len(unique)+14)//15}개 배치)")
        results = gpt_analyze(unique, api_key)
    else:
        print("  → 키워드 기반 필터링 사용 (GPT 미설정)")
        results = rule_based_filter(unique)
    print(f"     4개 본부 관련 {len(results)}건 선별")
    return results

def collect_and_save():
    db.init_db()
    results = collect()
    added = save_to_db(results)
    return added, len(results)

# ── 메인 (CLI 단독 실행 / 작업 스케줄러용) ────────────────
def main():
    print("=" * 50)
    print("  POSCOPE 자동 수집기 시작")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    added, total = collect_and_save()

    print("\n" + "=" * 50)
    print(f"  완료! 신규 {added}건 저장 (분석된 {total}건 중 중복 제외)")
    print("  Flask 서버(python app.py)를 실행해 대시보드에서 확인하세요.")
    print("=" * 50)

if __name__ == "__main__":
    main()
