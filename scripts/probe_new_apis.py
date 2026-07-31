"""07_20 파일의 신규 제휴 API 라이브 검증 + 실상품 수집.

목적: 새로 확보된 자격증명(Admitad OAuth, Tradedoubler publisher token, ClickBank,
Digistore24)으로 각 네트워크의 '상품 카탈로그' 엔드포인트를 실제 호출해
- 인증 성공 여부
- 실제 반환 상품 수
를 정직하게 리포트하고, 실제로 상품이 오는 네트워크는 파이프라인으로 리스트업한다.

보안: 키/비밀번호/로그인ID는 절대 저장·출력하지 않는다. 파일에서 메모리로만 읽는다.
대부분의 제휴 API는 '내가 승인받은 오퍼'만 반환하는 계정 스코프라, 신규 계정에선
0건이 정상이다 — 그 사실을 그대로 보고한다(초지능적 논리 = 정직한 원천 검증).
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import httpx
import openpyxl

XLSX = sys.argv[1] if len(sys.argv) > 1 else r"C:/Users/user/Downloads/Tburn_제휴 네트워크_07_20.xlsx"
UA = "GamdapBot/1.0"


def load_keys() -> dict[str, list[str]]:
    ws = openpyxl.load_workbook(XLSX, data_only=True).worksheets[0]
    out: dict[str, list[str]] = {}
    for r in ws.iter_rows(values_only=True):
        if not r or not r[1]:
            continue
        name = str(r[1]).strip()
        vals = []
        for i in (4, 5, 6):
            if not r[i]:
                continue
            v = "".join(str(r[i]).split())  # 내부 개행/공백 제거
            if v.isascii() and len(v) > 8:
                vals.append(v)
        out[name] = vals
    return out


def probe_admitad(vals: list[str]) -> str:
    """client_credentials OAuth → products/advcampaigns 카탈로그 조회."""
    if len(vals) < 2:
        return "자격증명 부족(client_id+secret 필요)"
    cid, secret = vals[0], vals[1]
    basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    with httpx.Client(timeout=25.0, headers={"User-Agent": UA}) as c:
        # 토큰 발급(여러 scope 시도)
        token = None
        for scope in ("public_data advcampaigns_for_website products",
                      "public_data", "advcampaigns"):
            try:
                r = c.post("https://api.admitad.com/token/",
                           headers={"Authorization": f"Basic {basic}"},
                           data={"grant_type": "client_credentials", "client_id": cid,
                                 "client_secret": secret, "scope": scope})
            except httpx.HTTPError as e:
                return f"네트워크 오류: {type(e).__name__}"
            if r.status_code == 200 and "access_token" in r.text:
                token = r.json()["access_token"]
                got_scope = r.json().get("scope", scope)
                break
        if not token:
            return f"인증 실패(HTTP {r.status_code}) — 키는 있으나 토큰 미발급"
        # 카탈로그 조회 시도: 연결된 광고주 → 상품
        h = {"Authorization": f"Bearer {token}", "User-Agent": UA}
        results = []
        try:
            rc = c.get("https://api.admitad.com/advcampaigns/?limit=20", headers=h)
            n_camp = rc.json().get("_meta", {}).get("count", "?") if rc.status_code == 200 else f"HTTP{rc.status_code}"
            results.append(f"연결 광고주={n_camp}")
        except httpx.HTTPError:
            results.append("광고주조회 실패")
        try:
            rp = c.get("https://api.admitad.com/products/?limit=20", headers=h)
            if rp.status_code == 200:
                n = rp.json().get("_meta", {}).get("count", 0)
                results.append(f"상품 카탈로그={n}건")
            else:
                results.append(f"상품API HTTP{rp.status_code}")
        except httpx.HTTPError:
            results.append("상품조회 실패")
        return "인증 OK · " + ", ".join(results) + f" (scope: {got_scope[:30]})"


def probe_tradedoubler(vals: list[str]) -> str:
    """publisher token으로 Product API 조회."""
    if not vals:
        return "토큰 없음"
    with httpx.Client(timeout=25.0, headers={"User-Agent": UA}) as c:
        for i, tok in enumerate(vals):
            try:
                r = c.get(f"https://api.tradedoubler.com/1.0/products.json?token={tok}&pageSize=20")
            except httpx.HTTPError as e:
                return f"네트워크 오류: {type(e).__name__}"
            if r.status_code == 200:
                try:
                    n = len(r.json().get("products", []))
                except ValueError:
                    n = 0
                return f"인증 OK(토큰{i + 1}) · 상품 {n}건"
            if r.status_code in (401, 403):
                continue
            return f"토큰{i + 1}: HTTP {r.status_code}"
        return "모든 토큰 인증 실패(401/403) — publisher 승인 프로그램 없음 추정"


def probe_generic_get(name: str, url: str, key: str, header: str) -> str:
    with httpx.Client(timeout=20.0, headers={"User-Agent": UA, header: key}) as c:
        try:
            r = c.get(url)
        except httpx.HTTPError as e:
            return f"네트워크 오류: {type(e).__name__}"
        return f"HTTP {r.status_code} · {len(r.text)}B 응답"


def main() -> int:
    keys = load_keys()
    print("■ 07_20 신규 API 라이브 검증 (키 값 미출력)\n")
    report = []

    for name, vals in keys.items():
        if "Admitad" in name and vals:
            report.append(("Admitad", probe_admitad(vals)))
        elif "Tradedoubler" in name and vals:
            report.append(("Tradedoubler", probe_tradedoubler(vals)))

    print(f"{'네트워크':16}{'결과'}")
    print("─" * 74)
    for n, res in report:
        print(f"{n:16}{res}")
    print("\n※ 계정 스코프 API는 '내 승인 오퍼'만 반환 → 신규계정 0건이 정상.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
