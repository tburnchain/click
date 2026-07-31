"""네트워크별 대표 오퍼 생성 + core.networks 시딩.

제휴 네트워크는 물리 상품만이 아니라 디지털·앱설치·구독·서비스·리드·쿠폰을 광고한다.
API 키가 연결되기 전(데모)에도 각 네트워크의 '실제 취급 유형'을 반영한 대표 오퍼를
생성해 파이프라인(정규화→점수→분류→표시) 전 구간이 다양한 오퍼 유형을 다루도록 한다.
생성분은 native_metric.sample=true 로 표시되어 실 API 수집분과 구분된다.

실제 라이브 오퍼는 회원이 각 네트워크 API 키를 연결하면 동일 파이프라인으로 대체·병행된다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from psycopg import Connection

from gamdap.domain.enums import BillingType, CommissionKind, DataSource, OfferType, StockStatus
from gamdap.domain.schemas import RawOffer
from gamdap.members import network_catalog

# 유형별 대표 오퍼 템플릿(현실적 커미션·과금 구조 반영). 값은 결정적(인덱스 기반).
_T: dict[str, dict[str, Any]] = {
    "digital_product": {
        "titles": ["30일 마케팅 마스터 강의", "전자책 베스트 번들", "프리미엄 프리셋 팩",
                   "드롭쉬핑 완전정복 코스", "AI 카피라이팅 툴킷", "노션 생산성 템플릿"],
        "price_usd": [27, 47, 97, 147, 197, 67], "billing": BillingType.CPS,
        "kind": CommissionKind.PERCENT, "rate": [0.50, 0.60, 0.70, 0.75, 0.55, 0.65],
        "stock": StockStatus.DIGITAL_UNLIMITED, "cat": "디지털/교육",
    },
    "app_install": {
        "titles": ["리워드 걷기앱 설치", "가계부 앱 첫 실행", "모바일 신작 게임",
                   "캐시백 쇼핑앱", "웹툰 앱 설치", "배달 신규앱 설치"],
        "billing": BillingType.CPI, "kind": CommissionKind.FIXED,
        "fixed_krw": [800, 1200, 2500, 1500, 900, 3000],
        "stock": StockStatus.UNKNOWN, "cat": "앱/모바일",
    },
    "subscription": {
        "titles": ["OTT 30일 무료체험", "클라우드 스토리지 구독", "디자인 SaaS 구독",
                   "VPN 연간 플랜", "AI 어시스턴트 Pro", "뉴스레터 프리미엄"],
        "price_usd": [9, 12, 19, 6, 20, 8], "billing": BillingType.RECURRING,
        "kind": CommissionKind.FIXED, "fixed_krw": [9000, 12000, 25000, 18000, 24000, 11000],
        "stock": StockStatus.DIGITAL_UNLIMITED, "cat": "구독/SaaS",
    },
    "service": {
        "titles": ["신용카드 발급 신청", "알뜰폰 요금제 가입", "인터넷 개통 신청",
                   "무료 보험상담", "해외주식 계좌개설", "대출 한도조회"],
        "billing": BillingType.CPA, "kind": CommissionKind.FIXED,
        "fixed_krw": [15000, 8000, 20000, 10000, 30000, 12000],
        "stock": StockStatus.UNKNOWN, "cat": "서비스/금융",
    },
    "lead": {
        "titles": ["무료 견적 신청", "뉴스레터 구독", "체험단 신청",
                   "회원가입 이벤트", "설문 참여 리워드", "상담 예약"],
        "billing": BillingType.CPL, "kind": CommissionKind.FIXED,
        "fixed_krw": [3000, 1500, 5000, 2000, 1000, 7000],
        "stock": StockStatus.UNKNOWN, "cat": "리드/가입",
    },
    "coupon": {
        "titles": ["최대 30% 할인쿠폰", "무료배송 쿠폰", "신규가입 특가",
                   "브랜드데이 프로모", "시즌오프 세일", "첫구매 10% 쿠폰"],
        "price_usd": [59, 29, 39, 49, 79, 25], "billing": BillingType.CPS,
        "kind": CommissionKind.PERCENT, "rate": [0.04, 0.03, 0.05, 0.04, 0.06, 0.03],
        "stock": StockStatus.IN_STOCK, "cat": "쿠폰/프로모",
    },
    "physical_product": {
        "titles": ["대표 추천 상품", "베스트셀러 픽", "이달의 인기템"],
        "price_usd": [39, 129, 259], "billing": BillingType.CPS,
        "kind": CommissionKind.PERCENT, "rate": [0.05, 0.04, 0.06],
        "stock": StockStatus.IN_STOCK, "cat": "대표상품",
    },
}
_PER_TYPE = 4  # 유형별 생성 개수 상한


def build_offers_for(slug: str, network_name: str, fetched_at: datetime | None = None
                     ) -> list[RawOffer]:
    """네트워크 하나의 대표 오퍼 리스트(취급 유형 전체)."""
    at = fetched_at or datetime.now(UTC)
    offers: list[RawOffer] = []
    for otype in network_catalog.offer_types_for(slug):
        t = _T[otype]
        titles = t["titles"]
        count = min(_PER_TYPE, len(titles))
        for i in range(count):
            title = f"{titles[i]} · {network_name}"
            price = t.get("price_usd", [None] * 6)[i] if "price_usd" in t else None
            rate = t.get("rate", [None] * 6)[i] if "rate" in t else None
            fixed = t.get("fixed_krw", [None] * 6)[i] if "fixed_krw" in t else None
            offers.append(RawOffer(
                network_code=slug,
                external_product_id=f"{slug}-{otype}-{i}",
                title=title,
                landing_url=f"https://www.google.com/search?q={otype}",
                thumbnail_url=None,
                offer_type=OfferType(otype),
                price_amount=Decimal(str(price)) if price else None,
                price_currency="USD" if price else None,
                billing_type=t["billing"],
                commission_kind=t["kind"],
                commission_rate=Decimal(str(rate)) if rate is not None else None,
                commission_fixed_amount=Decimal(str(fixed)) if fixed is not None else None,
                commission_currency="KRW" if fixed is not None else ("USD" if rate is not None else None),
                stock_status=t["stock"],
                native_rank=i + 1,
                native_metric={"sample": True, "network_name": network_name,
                               "payout_krw": fixed, "offer_type": otype},
                raw_category=t["cat"],
                data_source=DataSource.FEED,
                fetched_at=at,
            ))
    return offers


def seed_networks(conn: Connection) -> int:
    """카탈로그 23개 네트워크를 core.networks 에 upsert(대표 오퍼 귀속용)."""
    n = 0
    for net in network_catalog.list_networks():
        ds = "official_api" if net["integration"] == "api" else "aggregator_api"
        meta = {"region": net["region"], "category": net["category"],
                "status": net["status"], "integration": net["integration"]}
        row = conn.execute("SELECT id FROM core.networks WHERE code=%s", (net["slug"],)).fetchone()
        if row:
            conn.execute(
                "UPDATE core.networks SET display_name=%s, tracking_param=%s, is_active=true, "
                "meta=%s::jsonb, updated_at=now() WHERE code=%s",
                (net["name"], net["tracking_param"],
                 json.dumps(meta, ensure_ascii=False), net["slug"]),
            )
        else:
            conn.execute(
                "INSERT INTO core.networks (code, display_name, data_source, adapter, "
                "tracking_param, is_active, meta) VALUES (%s,%s,%s,%s,%s,true,%s::jsonb)",
                (net["slug"], net["name"], ds, net.get("connector_code"),
                 net["tracking_param"], json.dumps(meta, ensure_ascii=False)),
            )
            n += 1
    return n
