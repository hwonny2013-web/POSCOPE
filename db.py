"""
POSCOPE DB
SQLite 기반 프로젝트/업로드이력 영속화 레이어
"""

import json
import os
import re
import sqlite3
from datetime import datetime

DB_FILE = os.path.join(os.path.dirname(__file__), "poscope.db")


def normalize_title(title):
    """공백/대소문자/구두점 차이로 인한 중복 적재를 막기 위한 제목 정규화."""
    t = re.sub(r"\s+", " ", title or "").strip().lower()
    t = re.sub(r"[^\w가-힣 ]+", "", t)
    return t[:40]

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    div TEXT DEFAULT 'steel',
    country TEXT DEFAULT '',
    region TEXT DEFAULT '',
    owner TEXT DEFAULT '',
    epc TEXT DEFAULT '',
    size TEXT DEFAULT '',
    steel TEXT DEFAULT '',
    tons TEXT DEFAULT '',
    deadline TEXT DEFAULT '',
    urgency INTEGER DEFAULT 0,
    is_auto INTEGER DEFAULT 1,
    is_new INTEGER DEFAULT 1,
    source TEXT DEFAULT '',
    source_date TEXT DEFAULT '',
    memo TEXT DEFAULT '',
    ai_summary TEXT DEFAULT '',
    link TEXT DEFAULT '',
    sf_history_json TEXT DEFAULT '[]',
    normalized_title TEXT DEFAULT '',
    created_at TEXT DEFAULT '',
    status TEXT DEFAULT '검토중',
    kind TEXT DEFAULT 'PJT',
    manager TEXT DEFAULT '',
    progress_log_json TEXT DEFAULT '[]',
    sub_business TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_projects_normtitle ON projects(normalized_title);

CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    cnt INTEGER NOT NULL,
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS contractors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    aliases_json TEXT DEFAULT '[]',
    website TEXT DEFAULT '',
    enr_rank TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
"""

# 실제 확인된 홈페이지 기준. ENR 순위는 2025년 Top 250 International Contractors가 구독 전용이라
# 공개적으로 확인 가능한 수치(2023년 기준 등)만 표기하고, 나머지는 '등재(정확한 순위 비공개)'로 둔다.
SEED_CONTRACTORS = [
    dict(name="삼성물산", aliases=["Samsung C&T", "삼성물산 건설부문"],
         website="https://www.samsungcnt.com/", enr_rank="ENR Top250 International 등재(순위 비공개)"),
    dict(name="현대건설", aliases=["Hyundai E&C", "Hyundai Engineering & Construction"],
         website="https://www.hdec.kr/", enr_rank="ENR Top250 International 등재(순위 비공개)"),
    dict(name="GS건설", aliases=["GS E&C"],
         website="https://www.gsenc.com/", enr_rank="ENR Top250 International 등재(순위 비공개)"),
    dict(name="현대엔지니어링", aliases=["Hyundai Engineering"],
         website="https://www.hec.co.kr/", enr_rank="ENR Top250 International 등재(순위 비공개)"),
    dict(name="대우건설", aliases=["Daewoo E&C", "Daewoo Engineering"],
         website="https://www.daewooenc.com/", enr_rank="57위 (2023년 기준, 최신 순위는 ENR 구독 필요)"),
    dict(name="Bechtel", aliases=[],
         website="https://www.bechtel.com/", enr_rank="美 상업건설사 2위, 매출 $19.5B (2025년)"),
    dict(name="Skanska", aliases=[],
         website="https://www.skanska.com/", enr_rank="ENR Top250 International 상위권 등재(순위 비공개)"),
    dict(name="TechnipFMC", aliases=[],
         website="https://www.technipfmc.com/", enr_rank="글로벌 에너지 EPC, ENR Top250 등재(순위 비공개)"),
]

SEED_PROJECTS = [
    # ── 철강본부 (강재가 소요되는 PJT는 업종 불문 전부 철강본부 소관) ──
    dict(title='사우디 NEOM 스마트시티 2단계 철골 발주', div='steel', sub_business='에너지인프라강재사업',
         kind='PJT', manager='김철수 차장',
         country='중동', region='사우디아라비아',
         owner='NEOM Company', epc='Samsung C&T / Hyundai E&C', size='약 $180M', steel='H형강 · 각형강관',
         tons='28,000톤', deadline='2026-07-31', urgency=1, is_auto=1, is_new=1, source='해외건설협회',
         source_date='2026-06-16',
         sf_history=[{"date": "2026-03-11", "who": "김철수 차장 (철강본부)", "memo": "NEOM 1단계 납품 이후 2단계 물량 사전 협의. 바이어 측 \"포스코인터내셔널 우선 협력사 고려\" 언급."},
                      {"date": "2025-11-04", "who": "이영희 과장 (건설강재그룹)", "memo": "NEOM 현장 방문, 1단계 품질 평가 긍정적. 2단계 추가 물량 확보 요청."}],
         progress_log=[{"date": "2026-06-10 09:30", "author": "김철수 차장", "note": "오퍼 가격 내부 검토 완료. 다음주 바이어 미팅 예정."}],
         ai_summary='NEOM 2단계는 1단계 대비 철골 물량 약 40% 증가한 대형 건. 기존 공급이력 및 바이어 우호관계 활용 시 수주 가능성 높음. 7월 말 마감 전 선제 오퍼 권장.'),
    dict(title='UAE 두바이 항만 확장 강재 입찰', div='steel', sub_business='에너지인프라강재사업',
         kind='PJT', manager='박지민 과장', country='중동', region='UAE',
         owner='DP World', epc='Bechtel', size='약 $95M', steel='후판 · 강관파일', tons='15,000톤',
         deadline='2026-07-15', urgency=1, is_auto=1, is_new=1, source='MEED', source_date='2026-06-15',
         sf_history=[{"date": "2026-02-20", "who": "박지민 과장 (두바이지사)", "memo": "DP World 담당자 면담. 항만 3·4단계 확장 관련 강관파일 대량 소요 예상."}],
         ai_summary='두바이지사 접촉이력 활용 가능. 강관파일 경쟁력이 관건. 7월 마감 임박.'),
    dict(title='베트남 하노이-하이퐁 고속도로 교량', div='steel', sub_business='에너지인프라강재사업',
         kind='PJT', manager='여동진 과장', country='동남아', region='베트남',
         owner='베트남 교통부', epc='GS건설 컨소시엄', size='약 $220M', steel='교량용 후판 · H형강', tons='35,000톤',
         deadline='2026-08-20', urgency=0, is_auto=1, is_new=0, source='KOICA ODA', source_date='2026-06-14',
         sf_history=[{"date": "2026-04-07", "who": "여동진 과장 (건설강재그룹)", "memo": "GS건설 하노이 법인 방문. 후판 오퍼 검토 요청 수령."},
                      {"date": "2025-09-12", "who": "강현구 담당자 (하노이지사)", "memo": "베트남 교통부 ODA 협의. GS건설 컨소시엄 구성 확인."}],
         ai_summary='ODA 프로젝트 + 한국 EPC. GS건설 접촉이력 2건. 공식 오퍼 제출 단계.'),
    dict(title='이집트 수에즈 LNG 터미널 강재', div='steel', sub_business='에너지인프라강재사업',
         kind='PJT', country='중동', region='이집트',
         owner='이집트 국영에너지공사', epc='TechnipFMC', size='약 $450M', steel='LNG탱크용 저온강판', tons='8,000톤',
         deadline='2026-09-10', urgency=0, is_auto=1, is_new=1, source='뉴스', source_date='2026-06-13',
         sf_history=[], ai_summary='LNG 터미널 자체 사업이 아니라 터미널에 들어가는 저온강판 공급 기회 — 철강본부(에너지인프라강재) 소관. 접촉이력 없어 신규 개척 필요.'),
    dict(title='인도네시아 자카르타 해수담수화 플랜트', div='steel', sub_business='에너지인프라강재사업',
         kind='PJT', country='동남아', region='인도네시아',
         owner='인도네시아 국토부', epc='현대엔지니어링', size='약 $130M', steel='강관 · 특수강판', tons='5,500톤',
         deadline='2026-08-05', urgency=0, is_auto=1, is_new=0, source='해외건설협회', source_date='2026-06-12',
         sf_history=[{"date": "2026-01-15", "who": "이상훈 과장 (자카르타지사)", "memo": "현대엔지니어링 인니 법인 접촉. 담수화 플랜트 소요 강재 협의."}],
         ai_summary='자카르타지사 이력 확인. 현대엔지니어링 협력 가능.'),
    dict(title='브라질 파라나 곡물 사일로 복합단지', div='steel', sub_business='에너지인프라강재사업',
         kind='PJT', country='남미', region='브라질',
         owner='Amaggi Group', epc='현지 EPC', size='약 $75M', steel='구조용 형강', tons='9,000톤',
         deadline='2026-10-01', urgency=0, is_auto=1, is_new=0, source='뉴스', source_date='2026-06-11',
         sf_history=[{"date": "2025-12-03", "who": "김민준 대리 (상파울루지사)", "memo": "Amaggi 농업 복합단지 2단계. 사일로 구조용 강재 약 9,000톤 소요 예상."}],
         ai_summary='곡물 사업자가 발주주체이지만 소요 품목은 구조용 형강 — 철강본부 소관. 소재바이오본부와는 별개로, 상파울루지사 이력을 활용한 강재 영업 기회.'),
    dict(title='필리핀 마닐라 메트로 6호선 교량', div='steel', sub_business='에너지인프라강재사업',
         kind='PJT', country='동남아', region='필리핀',
         owner='필리핀 교통부 (ODA)', epc='대우건설', size='약 $110M', steel='교량용 H형강 · 후판', tons='18,000톤',
         deadline='2026-08-30', urgency=0, is_auto=1, is_new=0, source='KOICA ODA', source_date='2026-06-10',
         sf_history=[{"date": "2026-05-02", "who": "박현수 차장 (마닐라지사)", "memo": "대우건설 마닐라 법인 미팅. 메트로 6호선 교량 철골 오퍼 요청."},
                      {"date": "2026-03-18", "who": "박현수 차장 (마닐라지사)", "memo": "필리핀 교통부 ODA 승인 확인. 대우건설 우선 협상대상자 선정."}],
         ai_summary='ODA+한국 EPC 유리 조합. 마닐라지사 이력 2건. 정식 오퍼 시급.'),
    dict(title='폴란드 바르샤바 데이터센터 철골', div='steel', sub_business='에너지인프라강재사업',
         kind='PJT', country='유럽', region='폴란드',
         owner='Microsoft Poland', epc='Skanska', size='약 $60M', steel='H형강 · 데크플레이트', tons='4,200톤',
         deadline='2026-07-20', urgency=1, is_auto=1, is_new=1, source='뉴스', source_date='2026-06-16',
         sf_history=[], ai_summary='유럽 데이터센터 붐 연계. 접촉이력 없어 신규 개척 필요.'),
    dict(title='멕시코 모터코어 공장 증설용 전기강판 공급', div='steel', sub_business='모빌리티사업',
         kind='PJT', manager='정수민 차장', country='북미', region='멕시코',
         owner='POSCO INTERNATIONAL Mexico E-Mobility', epc='-', size='약 $40M', steel='고효율 전기강(Hyper NO)',
         tons='6,200톤', deadline='2026-09-01', urgency=0, is_auto=0, is_new=1, source='수동입력',
         source_date='2026-06-08',
         sf_history=[], ai_summary='멕시코 구동모터코아 법인 증설(연 350만대) 연계 전기강판 내부 공급 물량 확정 필요.'),

    # ── 소재바이오본부 (곡물·팜유·배터리원료·화섬/케미컬 — 철강 무관 트레이딩/투자) ──
    dict(title='우크라이나 미콜라이우 곡물터미널 가동재개 대비 옥수수 신규 바이어 문의', div='materials',
         sub_business='식량사업', kind='INQ', manager='최유진 과장', country='유럽', region='우크라이나',
         owner='-', epc='-', size='-', steel='옥수수 · 밀', tons='연 250만톤 처리능력',
         deadline='', urgency=0, is_auto=1, is_new=1, source='뉴스', source_date='2026-06-09',
         sf_history=[], ai_summary='2022년부터 가동 중단 중인 MMW Grain Terminal(지분 100%). 정세 안정 시 즉시 재가동 가능하도록 상시 준비 중 — 재가동 대비 신규 트레이딩 바이어 문의가 들어온 사안.'),
    dict(title='탄자니아 마헹게 흑연광산 지분 추가 확보 검토', div='materials', sub_business='원료소재사업',
         kind='PJT', manager='한도윤 대리', country='아프리카', region='탄자니아',
         owner='Tanzania Mahenge Mine', epc='-', size='-', steel='흑연(이차전지 음극재 원료)', tons='연 최대 6만톤',
         deadline='2026-12-31', urgency=0, is_auto=0, is_new=1, source='수동입력', source_date='2026-06-05',
         sf_history=[], ai_summary='현재 지분 19.9% 보유. 그룹사 이차전지 소재 수요 증가에 대응한 지분 추가 확보 검토 건.'),
    dict(title='동남아 PET·화섬 원료 장기공급계약 문의', div='materials', sub_business='산업소재사업',
         kind='INQ', country='동남아', region='베트남', owner='-', epc='-', size='-',
         steel='PX · PTA · PET', tons='-', deadline='', urgency=0, is_auto=1, is_new=1, source='업계전문지',
         source_date='2026-06-07',
         sf_history=[], ai_summary='베트남 섬유업체向 PET/화섬 원료 장기 오프테이크 문의. 산업소재사업(케미컬 트레이딩) 신규 거래선 후보.'),

    # ── 에너지사업본부 (LNG 트레이딩·터미널·발전 — 가스 E&P는 별도 가스사업본부) ──
    dict(title='카타르 라스라판 LNG 현물 카고 대량 구매 문의', div='energy', sub_business='LNG사업',
         kind='INQ', manager='오세훈 차장', country='중동', region='카타르', owner='QatarEnergy',
         epc='-', size='약 $60M (1카고)', steel='LNG 현물 카고', tons='17만 ㎥ 1카고',
         deadline='2026-07-25', urgency=1, is_auto=1, is_new=1, source='뉴스', source_date='2026-06-17',
         sf_history=[], ai_summary='광양LNG터미널 재고 운영 연계 가능한 현물 카고 매물. 가스트라이얼/단기 트레이딩 기회로 검토 필요.'),
    dict(title='베트남 해상풍력 개발사업 지분 참여 검토', div='energy', sub_business='발전사업개발',
         kind='PJT', country='동남아', region='베트남', owner='베트남 산업부', epc='-',
         size='약 $300M (지분 투자)', steel='-', tons='-', deadline='2027-03-31', urgency=0,
         is_auto=0, is_new=1, source='수동입력', source_date='2026-06-04',
         sf_history=[], ai_summary='신안 해상풍력 운영 경험을 활용한 해외 재생에너지 개발사업 지분 참여 검토 건.'),

    # ── 가스사업본부 (E&P · 가스개발 · 가스전운영) ──
    dict(title='말레이시아 PM524 광구 후속 개발투자 검토', div='gas', sub_business='E&P사업',
         kind='PJT', manager='윤지호 부장', country='동남아', region='말레이시아',
         owner='Petronas Carigali', epc='-', size='-', steel='-', tons='-', deadline='2026-10-31',
         urgency=0, is_auto=0, is_new=1, source='수동입력', source_date='2026-06-03',
         sf_history=[{"date": "2026-05-20", "who": "윤지호 부장 (E&P사업)", "memo": "광구 유망성 종합 재평가(~2026.10) 진행 중. 평가 결과에 따라 후속 개발투자 규모 결정 예정."}],
         ai_summary='지분 80%(운영권자) 보유 광구. 유망성 재평가 결과가 7월 마감 전 나올 예정이라 후속투자 의사결정 시급.'),
    dict(title='인도네시아 Bunga 광구 탐사시추 일정 관련 공동조사 문의', div='gas', sub_business='가스개발사업',
         kind='INQ', country='동남아', region='인도네시아', owner='PHE', epc='-', size='-',
         steel='-', tons='-', deadline='', urgency=0, is_auto=1, is_new=1, source='뉴스',
         source_date='2026-06-02',
         sf_history=[], ai_summary='지분 50%(운영권자). 2028년 탐사시추 계획 중이며 E&P/CCS 확장을 위한 공동조사사업이 진행 중 — 파트너사 문의 대응 필요.'),
]


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
    if "normalized_title" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN normalized_title TEXT DEFAULT ''")
        rows = conn.execute("SELECT id, title FROM projects").fetchall()
        for r in rows:
            conn.execute(
                "UPDATE projects SET normalized_title=? WHERE id=?",
                (normalize_title(r["title"]), r["id"]),
            )
        conn.commit()
    if "status" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN status TEXT DEFAULT '검토중'")
        conn.commit()
    if "kind" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN kind TEXT DEFAULT 'PJT'")
        conn.commit()
    if "manager" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN manager TEXT DEFAULT ''")
        conn.commit()
    if "progress_log_json" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN progress_log_json TEXT DEFAULT '[]'")
        conn.commit()
    if "sub_business" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN sub_business TEXT DEFAULT ''")
        conn.commit()
    # 구 본부 체계(construction/energy/agri) → 신 본부 체계(steel/energy/materials) 이전.
    conn.execute("UPDATE projects SET div='steel' WHERE div='construction'")
    conn.execute("UPDATE projects SET div='materials' WHERE div='agri'")
    conn.commit()
    # 기존에 잘못 분류돼 있던 시드 데이터 보정: 강재가 소요되는 PJT는 발주처 업종과
    # 무관하게 철강본부(에너지인프라강재사업) 소관 — 이미 가동 중인 DB에도 동일하게 반영.
    _STEEL_DEMAND_FIXUPS = [
        '이집트 수에즈 LNG 터미널 강재',
        '인도네시아 자카르타 해수담수화 플랜트',
        '브라질 파라나 곡물 사일로 복합단지',
    ]
    for title in _STEEL_DEMAND_FIXUPS:
        conn.execute(
            "UPDATE projects SET div='steel', sub_business='에너지인프라강재사업' "
            "WHERE normalized_title=? AND div!='steel'",
            (normalize_title(title),),
        )
    conn.commit()


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate(conn)
    # 제목 기준으로 이미 있으면 건너뛰므로, 기존 가동 중인 DB에도 신규 시드(데모) 건만
    # 안전하게 추가로 반영된다 (기존 데이터는 손대지 않음).
    for p in SEED_PROJECTS:
        title = p.get("title", "")
        row = conn.execute(
            "SELECT id FROM projects WHERE normalized_title=? LIMIT 1", (normalize_title(title),)
        ).fetchone()
        if row is None:
            insert_project(p, sf_history=p.get("sf_history", []), conn=conn)
    conn.commit()
    seeded = conn.execute("SELECT COUNT(*) c FROM contractors").fetchone()["c"]
    if seeded == 0:
        for c in SEED_CONTRACTORS:
            conn.execute(
                "INSERT OR IGNORE INTO contractors (name, aliases_json, website, enr_rank) VALUES (?,?,?,?)",
                (c["name"], json.dumps(c["aliases"], ensure_ascii=False), c["website"], c["enr_rank"]),
            )
        conn.commit()
    conn.close()


def _row_to_dict(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "div": row["div"],
        "country": row["country"],
        "region": row["region"],
        "owner": row["owner"],
        "epc": row["epc"],
        "size": row["size"],
        "steel": row["steel"],
        "tons": row["tons"],
        "deadline": row["deadline"],
        "urgency": bool(row["urgency"]),
        "isAuto": bool(row["is_auto"]),
        "isNew": bool(row["is_new"]),
        "source": row["source"],
        "sourceDate": row["source_date"],
        "memo": row["memo"],
        "aiSummary": row["ai_summary"],
        "link": row["link"],
        "sfHistory": json.loads(row["sf_history_json"] or "[]"),
        "status": row["status"] or "검토중",
        "kind": row["kind"] or "PJT",
        "manager": row["manager"] or "",
        "progressLog": json.loads(row["progress_log_json"] or "[]"),
        "subBusiness": row["sub_business"] or "",
    }


def list_projects(div_filter=None):
    conn = get_conn()
    if div_filter:
        rows = conn.execute(
            "SELECT * FROM projects WHERE div=? ORDER BY id DESC", (div_filter,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    auto = conn.execute("SELECT COUNT(*) c FROM projects WHERE is_auto=1").fetchone()["c"]
    manual = conn.execute("SELECT COUNT(*) c FROM projects WHERE is_auto=0").fetchone()["c"]
    sf = conn.execute("SELECT COUNT(*) c FROM projects WHERE sf_history_json != '[]'").fetchone()["c"]
    conn.close()
    return {"total": total, "auto": auto, "manual": manual, "sfLinked": sf}


def insert_project(p, sf_history=None, conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    title = p.get("title", "")
    cur = conn.execute(
        """INSERT INTO projects
           (title, div, country, region, owner, epc, size, steel, tons, deadline, urgency,
            is_auto, is_new, source, source_date, memo, ai_summary, link, sf_history_json,
            normalized_title, created_at, kind, manager, progress_log_json, sub_business)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            title, p.get("div", "steel"), p.get("country", ""),
            p.get("region", p.get("country", "")), p.get("owner", ""), p.get("epc", ""),
            p.get("size", ""), p.get("steel", ""), p.get("tons", ""), p.get("deadline", ""),
            int(bool(p.get("urgency", False))), int(bool(p.get("is_auto", True))),
            int(bool(p.get("is_new", True))), p.get("source", ""), p.get("source_date", ""),
            p.get("memo", ""), p.get("ai_summary", ""), p.get("link", ""),
            json.dumps(sf_history or [], ensure_ascii=False),
            normalize_title(title),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            p.get("kind", "PJT"), p.get("manager", ""),
            json.dumps(p.get("progress_log") or [], ensure_ascii=False),
            p.get("sub_business", ""),
        ),
    )
    new_id = cur.lastrowid
    if own_conn:
        conn.commit()
        conn.close()
    return new_id


def update_project(project_id, data):
    conn = get_conn()
    allowed = [
        "title", "div", "country", "region", "owner", "epc", "size", "steel",
        "tons", "deadline", "urgency", "memo", "ai_summary", "status", "kind", "manager",
        "sub_business",
    ]
    fields, vals = [], []
    for k in allowed:
        if k in data:
            fields.append(f"{k}=?")
            v = data[k]
            if k == "urgency":
                v = int(bool(v))
            vals.append(v)
    if "title" in data:
        fields.append("normalized_title=?")
        vals.append(normalize_title(data["title"]))
    if not fields:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        conn.close()
        return _row_to_dict(row) if row else None
    vals.append(project_id)
    conn.execute(f"UPDATE projects SET {','.join(fields)} WHERE id=?", vals)
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def delete_project(project_id):
    conn = get_conn()
    conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    conn.commit()
    conn.close()


def title_exists(title):
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM projects WHERE normalized_title=? LIMIT 1", (normalize_title(title),)
    ).fetchone()
    conn.close()
    return row is not None


def link_exists(link):
    """출처 링크 기준 중복 체크. 제목을 단순화하면 서로 다른 기사가 같은 제목으로
    겹칠 수 있으므로, link가 있으면 link로(없으면 title로) 중복을 판단한다."""
    if not link:
        return False
    conn = get_conn()
    row = conn.execute("SELECT id FROM projects WHERE link=? LIMIT 1", (link,)).fetchone()
    conn.close()
    return row is not None


def update_sf_history(project_id, sf_history):
    conn = get_conn()
    conn.execute(
        "UPDATE projects SET sf_history_json=? WHERE id=?",
        (json.dumps(sf_history, ensure_ascii=False), project_id),
    )
    conn.commit()
    conn.close()


def add_progress_log(project_id, author, note, status=None):
    """담당자가 남기는 진행 업데이트 1건을 progress_log에 추가하고, status가 오면 같이 갱신."""
    conn = get_conn()
    row = conn.execute("SELECT progress_log_json FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        conn.close()
        return None
    log = json.loads(row["progress_log_json"] or "[]")
    log.insert(0, {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "author": author,
        "note": note,
    })
    if status:
        conn.execute(
            "UPDATE projects SET progress_log_json=?, status=? WHERE id=?",
            (json.dumps(log, ensure_ascii=False), status, project_id),
        )
    else:
        conn.execute(
            "UPDATE projects SET progress_log_json=? WHERE id=?",
            (json.dumps(log, ensure_ascii=False), project_id),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def get_project(project_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def add_upload_history(type_, name, cnt):
    conn = get_conn()
    conn.execute(
        "INSERT INTO upload_history (type, name, cnt, created_at) VALUES (?,?,?,?)",
        (type_, name, cnt, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def list_upload_history():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM upload_history ORDER BY id DESC").fetchall()
    conn.close()
    return [
        {"type": r["type"], "name": r["name"], "cnt": r["cnt"], "date": r["created_at"]}
        for r in rows
    ]


def list_contractors():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM contractors ORDER BY name").fetchall()
    conn.close()
    return [
        {
            "name": r["name"],
            "aliases": json.loads(r["aliases_json"] or "[]"),
            "website": r["website"],
            "enrRank": r["enr_rank"],
            "notes": r["notes"],
        }
        for r in rows
    ]


def upsert_contractor(data):
    name = (data.get("name") or "").strip()
    if not name:
        return None
    conn = get_conn()
    conn.execute(
        """INSERT INTO contractors (name, aliases_json, website, enr_rank, notes)
           VALUES (?,?,?,?,?)
           ON CONFLICT(name) DO UPDATE SET
             aliases_json=excluded.aliases_json, website=excluded.website,
             enr_rank=excluded.enr_rank, notes=excluded.notes""",
        (
            name,
            json.dumps(data.get("aliases") or [], ensure_ascii=False),
            data.get("website", ""),
            data.get("enrRank", ""),
            data.get("notes", ""),
        ),
    )
    conn.commit()
    conn.close()
    return name
