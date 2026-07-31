"""도메인 열거형 — DB CHECK 제약과 1:1 정합."""

from __future__ import annotations

from enum import StrEnum


class BillingType(StrEnum):
    CPS = "CPS"      # 판매당
    CPC = "CPC"      # 클릭당
    CPM = "CPM"      # 노출당
    CPA = "CPA"      # 행동당(설치·가입)
    CPL = "CPL"      # 리드당
    CPI = "CPI"      # 설치당
    RECURRING = "RECURRING"  # 구독 반복


class OfferType(StrEnum):
    """제휴 네트워크가 광고하는 오퍼의 종류(제품만이 아님)."""

    PHYSICAL = "physical_product"   # 물리 상품 → 구매
    DIGITAL = "digital_product"     # 디지털(강의·이북·툴) → 구매/다운로드
    APP = "app_install"             # 앱 설치 → 설치(CPI/CPA)
    SUBSCRIPTION = "subscription"   # SaaS·정기결제 → 무료체험/구독(recurring)
    SERVICE = "service"             # 서비스 신청(금융·통신 등) → 신청
    LEAD = "lead"                   # 리드/회원가입 → 신청(CPL)
    COUPON = "coupon"               # 쿠폰·프로모 → 쿠폰받기


class CommissionKind(StrEnum):
    PERCENT = "percent"
    FIXED = "fixed"


class StockStatus(StrEnum):
    IN_STOCK = "in_stock"
    LOW = "low"
    OUT_OF_STOCK = "out_of_stock"
    DIGITAL_UNLIMITED = "digital_unlimited"
    UNKNOWN = "unknown"


class DataSource(StrEnum):
    OFFICIAL_API = "official_api"
    AGGREGATOR_API = "aggregator_api"
    FEED = "feed"


class Segment(StrEnum):
    GOLDMINE = "goldmine"
    RISING = "rising"
    CASHCOW = "cashcow"
    SATURATED = "saturated"
    AVOID = "avoid"
