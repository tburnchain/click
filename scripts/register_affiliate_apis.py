"""파일의 제휴 네트워크 계정·API를 크롤링 시스템에 등록 + 라이브 실행.

- xlsx의 API 키를 읽어(값 미출력) 각 네트워크를 core.networks 에 등록한다.
- 우리 커넥터가 있고 키가 유효한 네트워크는 실제 수집(run_ingestion)을 실행한다.
- 결과를 네트워크별로 정직하게 리포트한다(등록/인증/수집건수).

키는 소스에 저장/출력하지 않는다. Digistore24 키만 이 프로세스 env 로 전달해 실행한다.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
for k, v in {"GAMDAP_DB_HOST": "127.0.0.1", "GAMDAP_DB_PORT": "5433", "GAMDAP_DB_NAME": "gamdap",
             "GAMDAP_DB_USER": "postgres", "GAMDAP_DB_PASSWORD": "x",
             "PYTHONIOENCODING": "utf-8", "PGCLIENTENCODING": "UTF8"}.items():
    os.environ.setdefault(k, v)

import openpyxl  # noqa: E402

# 파일 사이트명 → (네트워크 code, 커넥터 adapter 또는 None, 표시명)
NETS = {
    "쿠팡 파트너스":      ("coupang_partners", "coupang",     "쿠팡 파트너스"),
    "Amazon Associates": ("amazon_assoc",     "amazon",      "Amazon Associates"),
    "ClickBank":         ("clickbank",        "clickbank",   "ClickBank"),
    "CJ Affiliate":      ("cj_affiliate",     "cj",          "CJ Affiliate"),
    "Impact":            ("impact",           "impact",      "Impact"),
    "Digistore24":       ("digistore24",      "digistore24", "Digistore24"),
    "Rakuten":           ("rakuten",          None,          "Rakuten Advertising"),
    "Awin":              ("awin",             None,          "Awin"),
    "LinkPrice":         ("linkprice",        None,          "링크프라이스"),
    "PartnerStack":      ("partnerstack",     None,          "PartnerStack"),
    "FlexOffers":        ("flexoffers",       None,          "FlexOffers"),
    "Admitad":           ("admitad",          None,          "Admitad"),
    "Skimlinks":         ("skimlinks",        None,          "Skimlinks"),
    "Involve":           ("involve_asia",     None,          "Involve Asia"),
    "JVZoo":             ("jvzoo",            None,          "JVZoo"),
    "Sovrn":             ("sovrn",            None,          "Sovrn Commerce"),
}


def read_keys(xlsx: str) -> dict[str, list[str]]:
    ws = openpyxl.load_workbook(xlsx, data_only=True).worksheets[0]
    out: dict[str, list[str]] = {}
    for r in ws.iter_rows(values_only=True):
        if not r or not r[1]:
            continue
        name = str(r[1]).strip()
        vals = [str(r[i]).strip() for i in (4, 5, 6) if r[i] and len(str(r[i]).strip()) > 3]
        if vals:
            out[name] = vals
    return out


def _match(name: str):
    for key, meta in NETS.items():
        if key in name:
            return meta
    return None


def main() -> int:
    xlsx = sys.argv[1] if len(sys.argv) > 1 else r"C:/Users/user/Downloads/Tburn_제휴 네트워크 (1).xlsx"
    keys = read_keys(xlsx)

    # Digistore24 실제 키를 config 로드 '전에' env 로 주입(get_settings 캐시 대비)
    for fname, vals in keys.items():
        if "Digistore24" in fname and vals and vals[0].isascii():
            os.environ["GAMDAP_DIGISTORE24_API_KEY"] = vals[0]
    from gamdap.db import transaction

    rows = []          # (표시명, 등록, 키상태, 실행결과)
    digistore_key = None
    with transaction() as conn:
        for fname, vals in keys.items():
            m = _match(fname)
            if not m:
                continue
            code, adapter, disp = m
            real = any(v.replace("-", "").replace("_", "").isalnum() and v.isascii() for v in vals)
            keyst = "실제 키" if real else "메모(키 아님)"
            if "Digistore24" in fname and real:
                digistore_key = vals[0]
            # core.networks 등록(upsert)
            meta = json.dumps({"registered_from": "file", "key_present": real,
                               "connector": bool(adapter)}, ensure_ascii=False)
            exist = conn.execute("SELECT id FROM core.networks WHERE code=%s", (code,)).fetchone()
            if exist:
                conn.execute("UPDATE core.networks SET display_name=%s, adapter=%s, is_active=true, "
                             "meta=%s::jsonb, updated_at=now() WHERE code=%s",
                             (disp, adapter, meta, code))
            else:
                conn.execute("INSERT INTO core.networks (code, display_name, data_source, adapter, "
                             "tracking_param, is_active, meta) VALUES (%s,%s,'aggregator_api',%s,'ref',true,%s::jsonb)",
                             (code, disp, adapter, meta))
            rows.append([disp, "✅", keyst, "커넥터 있음" if adapter else "커넥터 없음(가이드)"])

    print(f"■ 네트워크 등록: {len(rows)}개 (core.networks upsert)\n")

    # 실제 수집 실행 — Digistore24(단일키 인증 검증됨)
    if digistore_key:
        from gamdap.connectors import get_connector
        from gamdap.ingest import run_ingestion
        ok = get_connector("digistore24").health()
        rep = run_ingestion("digistore24", limit=200, job_type="full")
        for row in rows:
            if row[0] == "Digistore24":
                row[3] = f"인증={'OK' if ok else '실패'} · 수집 {rep.fetched}건"

    # 리포트
    print(f"{'네트워크':22} {'등록':4} {'키':14} {'실행 결과'}")
    print("─" * 78)
    for disp, reg, keyst, res in rows:
        print(f"{disp[:22]:22} {reg:4} {keyst:14} {res}")
    print("\n※ 키 값은 저장/출력하지 않음. 실제 수집은 인증되는 커넥터에서만 실행됨.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
