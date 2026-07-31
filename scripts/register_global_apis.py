"""글로벌 제휴마케팅 정보(xlsx) → 네트워크 카탈로그 등록 + 실수집.

- 파일의 모든 사이트를 core.networks 에 카탈로그로 등록(글로벌 시스템 완성).
- 실제 상품 데이터를 주는 Travelpayouts(공개 Data API)는 라이브 수집한다.
- 키/비번/ID는 절대 저장·출력하지 않는다. Travelpayouts 토큰만 이 프로세스 env 로 전달.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import openpyxl  # noqa: E402

XLSX = sys.argv[1] if len(sys.argv) > 1 else r"C:/Users/user/Downloads/글로벌 제휴마케팅 정보.xlsx"


def _clean(v: object) -> str:
    return "".join(str(v).split()) if v is not None else ""


def is_real_key(v: object) -> bool:
    s = _clean(v)
    if len(s) < 12 or not s.isascii() or s.startswith("http") or "@" in s:
        return False
    low = s.lower()
    if any(k in low for k in ["없음", "진행", "유료", "해당", "가입", "필요", "종료", "발급", "이후"]):
        return False
    return bool(re.search(r"[A-Za-z0-9]{12,}", re.sub(r"[-_.]", "", s)))


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return ("g_" + s)[:48] or "g_net"


def read_rows() -> list[tuple[str, str, bool, str | None]]:
    """(name, url, has_key, travelpayouts_token) 목록."""
    ws = openpyxl.load_workbook(XLSX, data_only=True).worksheets[0]
    out = []
    for r in ws.iter_rows(values_only=True):
        if not r or not r[0]:
            continue
        name = str(r[0]).strip()
        if name.lower() in ("사이트명", "name", "번호"):
            continue
        if re.fullmatch(r"[0-9]+\.?[0-9]*", name):  # 숫자만(날짜/번호 오염) 제외
            continue
        url = str(r[1]).strip() if len(r) > 1 and r[1] else ""
        keys = [c for c in r[3:] if is_real_key(c)]
        tp = None
        if "Travelpayouts" in name and keys:
            tp = _clean(keys[0])
        out.append((name, url, bool(keys), tp))
    return out


def main() -> int:
    rows = read_rows()
    tp_token = next((t for *_, t in rows if t), None)
    if tp_token:
        os.environ["GAMDAP_TRAVELPAYOUTS_TOKEN"] = tp_token  # config 로드 전 주입

    os.environ.setdefault("GAMDAP_DB_HOST", "127.0.0.1")
    os.environ.setdefault("GAMDAP_DB_PORT", "5433")
    os.environ.setdefault("GAMDAP_DB_NAME", "gamdap")
    os.environ.setdefault("GAMDAP_DB_USER", "postgres")
    os.environ.setdefault("GAMDAP_DB_PASSWORD", "x")

    import json

    from gamdap.db import transaction

    # 실제 상품 데이터를 주는 커넥터 매핑(공개 카탈로그)
    connector_for = {"Travelpayouts": "travelpayouts"}

    registered = 0
    keyed = 0
    with transaction() as conn:
        for name, url, has_key, _ in rows:
            code = slug(name)
            adapter = connector_for.get(name)
            meta = json.dumps({"registered_from": "global_file", "key_present": has_key,
                               "homepage": url[:120], "connector": bool(adapter)}, ensure_ascii=False)
            exist = conn.execute("SELECT id FROM core.networks WHERE code=%s", (code,)).fetchone()
            if exist:
                conn.execute("UPDATE core.networks SET display_name=%s, adapter=%s, is_active=true, "
                             "meta=%s::jsonb, updated_at=now() WHERE code=%s",
                             (name, adapter, meta, code))
            else:
                conn.execute("INSERT INTO core.networks (code, display_name, data_source, adapter, "
                             "tracking_param, is_active, meta) VALUES (%s,%s,'aggregator_api',%s,'ref',true,%s::jsonb)",
                             (code, name, adapter, meta))
            registered += 1
            keyed += 1 if has_key else 0

    print(f"■ 글로벌 네트워크 카탈로그 등록: {registered}개 (실 키 보유 {keyed}개)")

    # Travelpayouts 실수집(실 항공권 특가)
    if tp_token:
        from gamdap.connectors import get_connector
        from gamdap.ingest import run_ingestion

        # travelpayouts 네트워크가 커넥터를 쓰도록 code 를 표준화
        with transaction() as conn:
            conn.execute("UPDATE core.networks SET adapter='travelpayouts' "
                         "WHERE display_name ILIKE 'Travelpayouts%%'")
            # run_ingestion 은 network_code 로 조회 → travelpayouts 코드 확보
            row = conn.execute("SELECT code FROM core.networks WHERE display_name ILIKE 'Travelpayouts%%' LIMIT 1").fetchone()
        tp_code = row["code"] if row else None
        ok = get_connector("travelpayouts").health()
        print(f"\n■ Travelpayouts 인증: {'OK' if ok else '실패'}")
        if ok and tp_code:
            rep = run_ingestion(tp_code, limit=1500, job_type="full")
            st = rep.stats
            print(f"  수집 fetched={rep.fetched} 신규={st.inserted} 갱신={st.updated} 상태={rep.status}")
            # 신규 오퍼 점수·분류 반영
            from gamdap.analytics import compute_scores
            from gamdap.analytics.classification import compute_classifications
            with transaction() as conn:
                compute_scores(conn)
            with transaction() as conn:
                compute_classifications(conn)
            print("  점수·분류 반영 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
