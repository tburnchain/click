"""제휴 네트워크 API 키 안전 적용 + 라이브 진단.

- xlsx의 API 키를 로컬 .env.keys(gitignore, 이 기기 전용)로 매핑 저장한다. **값은 출력하지 않는다.**
- 각 네트워크 API에 실제 인증 요청을 보내 상태를 진단한다(키 유효성/카탈로그 접근).
- 로그인 비밀번호는 다루지 않는다(추출 자격증명만).

사용: python scripts/apply_affiliate_keys.py "C:/.../Tburn_제휴 네트워크 (1).xlsx"
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import openpyxl

# 파일 사이트명 → (우리 시스템 env 이름들, 우리 커넥터 존재?, 추출에 필요한 자격증명 수)
NET = {
    "쿠팡 파트너스":       ("coupang",     True,  2, "ACCESS_KEY+SECRET_KEY"),
    "Amazon Associates":  ("amazon",      True,  3, "ACCESS_KEY+SECRET_KEY+PARTNER_TAG (+PA-API 3판매 조건)"),
    "ClickBank":          ("clickbank",   True,  2, "DEV_KEY+CLERK_KEY"),
    "CJ Affiliate":       ("cj",          True,  3, "TOKEN+COMPANY_ID+WEBSITE_ID"),
    "Impact":             ("impact",      True,  2, "ACCOUNT_SID+AUTH_TOKEN"),
    "Rakuten":            ("rakuten",     False, 3, "OAuth client/secret/token"),
    "Awin":               ("awin",        False, 2, "API_TOKEN+PUBLISHER_ID"),
    "LinkPrice":          ("linkprice",   False, 2, "AFFILIATE_ID+피드키"),
    "Digistore24":        ("digistore24", False, 1, "API_KEY (단일)"),
    "PartnerStack":       ("partnerstack", False, 1, "API_KEY"),
    "FlexOffers":         ("flexoffers",  False, 1, "API_KEY (계정 승인 대기)"),
    "Admitad":            ("admitad",     False, 3, "CLIENT_ID+SECRET+SCOPE (OAuth)"),
    "Skimlinks":          ("skimlinks",   False, 2, "PUBLISHER_ID+API_KEY"),
    "Involve":            ("involve",     False, 2, "KEY+SECRET"),
    "JVZoo":              ("jvzoo",       False, 1, "API_KEY"),
    "Sovrn":              ("sovrn",       False, 1, "API_KEY"),
}


def _match(name: str) -> tuple[str, bool, int, str] | None:
    for key, meta in NET.items():
        if key in name:
            return meta
    return None


def read_keys(xlsx_path: str) -> dict[str, list[str]]:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.worksheets[0]
    out: dict[str, list[str]] = {}
    for r in ws.iter_rows(values_only=True):
        if not r or not r[1]:
            continue
        name = str(r[1]).strip()
        vals = [str(r[i]).strip() for i in (4, 5, 6) if r[i] and str(r[i]).strip() and len(str(r[i]).strip()) > 3]
        if vals:
            out[name] = vals
    return out


def write_env(keys: dict[str, list[str]], out_path: Path) -> int:
    """로컬 .env.keys 로 저장(값 미출력). GAMDAP_<SLUG>_APIKEY_N 형식."""
    lines = ["# 제휴 API 키 — 로컬 전용, 절대 커밋/공유 금지. 자동 생성.", ""]
    n = 0
    for name, vals in keys.items():
        meta = _match(name)
        slug = (meta[0] if meta else name).upper().replace(" ", "_")
        for i, v in enumerate(vals, 1):
            lines.append(f"GAMDAP_{slug}_APIKEY_{i}={v}")
            n += 1
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return n


# ── 라이브 진단(값 미출력, 상태만) ──
def diag_digistore24(key: str) -> str:
    try:
        c = httpx.Client(timeout=20, follow_redirects=True)
        r = c.get("https://www.digistore24.com/api/call/getUserInfo/", headers={"X-DS-API-KEY": key})
        if r.status_code == 200 and r.json().get("result") == "success":
            roles = r.json().get("data", {}).get("granted_roles", "")
            mp = c.get("https://www.digistore24.com/api/call/listMarketplaceEntries/",
                       headers={"X-DS-API-KEY": key}, params={"page_size": 1}).json().get("data", {})
            return f"✅ 인증성공 (role={roles}) · 마켓카탈로그 {mp.get('count', '?')}개"
        return f"⚠️ 인증거절 ({r.status_code})"
    except Exception as e:  # noqa: BLE001
        return f"❌ 연결오류 {str(e)[:40]}"


def diag_admitad(vals: list[str]) -> str:
    import base64
    import itertools
    try:
        c = httpx.Client(timeout=20)
        for a, b, sc in itertools.permutations(vals, 3):
            t = c.post("https://api.admitad.com/token/",
                       data={"grant_type": "client_credentials", "client_id": a, "scope": sc},
                       headers={"Authorization": "Basic " + base64.b64encode(f"{a}:{b}".encode()).decode()})
            if t.status_code == 200 and "access_token" in t.json():
                return "✅ OAuth 인증성공"
        return "⚠️ OAuth 실패 (스코프/계정 활성화 필요)"
    except Exception as e:  # noqa: BLE001
        return f"❌ 연결오류 {str(e)[:40]}"


def main() -> int:
    if len(sys.argv) < 2:
        print("사용: python scripts/apply_affiliate_keys.py <xlsx경로>")
        return 1
    xlsx = sys.argv[1]
    keys = read_keys(xlsx)
    root = Path(__file__).resolve().parents[1]
    n = write_env(keys, root / ".env.keys")
    print(f"■ 키 적용: {len(keys)}개 네트워크 · {n}개 값 → .env.keys (로컬 전용, 값 미출력)\n")

    print(f"{'네트워크':22} {'커넥터':6} {'자격증명':10} {'라이브 진단'}")
    print("─" * 90)
    for name, vals in keys.items():
        meta = _match(name)
        if not meta:
            continue
        _slug, connector, need, req = meta
        have = len(vals)
        complete = "완전" if have >= need else f"부족({have}/{need})"
        conn = "있음" if connector else "없음"
        # 라이브 진단
        if "Digistore24" in name:
            live = diag_digistore24(vals[0])
        elif "Admitad" in name:
            live = diag_admitad(vals)
        elif have >= need:
            live = "🔑 자격증명 완전 → 커넥터 연결 시 라이브"
        else:
            live = f"➖ 추가 필요: {req}"
        print(f"{name[:22]:22} {conn:6} {complete:10} {live}")
    print("\n※ 값은 저장/진단에만 사용, 어디에도 출력하지 않음. .env.keys 는 gitignore 처리됨.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
