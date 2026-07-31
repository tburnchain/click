"""데모 리포지토리 — DB 없이 대시보드를 실제 엔진 계산으로 구동.

목적: 로컬에 Postgres가 없어도 완성된 UI/파이프라인을 시연.
수익성 점수·세그먼트는 하드코딩이 아니라 gamdap.analytics 의 실제 함수로 계산한다.
GAMDAP_DEMO=true 로 활성화(app.py).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from gamdap.analytics.classification import (
    SegmentThresholds,
    assign_segment,
    competition_index,
)
from gamdap.analytics.profitability import (
    composite_score,
    cvr_prior,
    expected_earning_per_sale,
    rank_to_demand,
    robust_quantile_norm,
)
from gamdap.api.schemas import (
    CategoryOut,
    ConnectorOut,
    HistoryPoint,
    JobOut,
    Money,
    NetworkOut,
    OfferListOut,
    OfferOut,
    OpportunityOut,
    ScoreOut,
    SummaryOut,
)

_USD_KRW = Decimal("1350")
_NOW = datetime(2026, 7, 13, 9, 0, tzinfo=UTC)


def _real_url(net_code: str, title: str) -> str:
    """데모용 실제 랜딩 URL — 상품명으로 각 네트워크의 실검색 페이지로 연결.

    운영(비데모) 모드에서는 커넥터가 실제 제휴 딥링크(쿠팡 productUrl 등)를 저장한다.
    """
    from urllib.parse import quote

    q = quote(title)
    if net_code == "coupang_partners":
        return f"https://www.coupang.com/np/search?q={q}"
    if net_code == "amazon_assoc":
        return f"https://www.amazon.com/s?k={q}"
    # ClickBank/Impact/CJ 등 애그리게이터는 데모에서 웹 검색으로 대체
    return f"https://www.google.com/search?q={q}"


def _svg_thumb(emoji: str, color: str) -> str:
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>"
        f"<rect width='40' height='40' rx='6' fill='{color}'/>"
        f"<text x='20' y='27' font-size='20' text-anchor='middle'>{emoji}</text></svg>"
    )
    import base64
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


# (network_code, network_name, title, category, price(KRW), currency, kind, rate|fixed, rank, stock, emoji, color)
_RAW = [
    ("coupang_partners", "쿠팡 파트너스", "샤오미 창문 로봇청소기 X10", "electronics.appliance",
     136660, "KRW", "percent", 0.03, 2, "in_stock", "🤖", "#dbeafe"),
    ("coupang_partners", "쿠팡 파트너스", "올스텐 에어프라이어 5.5L", "electronics.appliance",
     101470, "KRW", "percent", 0.03, 5, "in_stock", "🍟", "#fef3c7"),
    ("coupang_partners", "쿠팡 파트너스", "커피 메이커 (기획전)", "electronics.appliance",
     50000, "KRW", "percent", 0.15, 1, "in_stock", "☕", "#fee2e2"),
    ("coupang_partners", "쿠팡 파트너스", "자동 분무기 미니", "home",
     18900, "KRW", "percent", 0.03, 40, "low", "💧", "#dcfce7"),
    ("coupang_partners", "쿠팡 파트너스", "무선 블루투스 이어폰 프로", "electronics.mobile",
     89000, "KRW", "percent", 0.03, 8, "in_stock", "🎧", "#e0e7ff"),
    ("amazon_assoc", "Amazon", "Galaxy Book 3 Pro", "electronics.computer",
     1200000, "USD", "percent", 0.025, 12, "in_stock", "💻", "#e0f2fe"),
    ("amazon_assoc", "Amazon", "럭셔리 뷰티 마스크 세트", "beauty.skincare",
     30000, "USD", "percent", 0.10, 3, "in_stock", "💆", "#fce7f3"),
    ("amazon_assoc", "Amazon", "종합 건강 보조제", "health.supplement",
     20000, "USD", "percent", 0.01, 25, "in_stock", "💊", "#dcfce7"),
    ("clickbank", "ClickBank", "Java Burn 대사촉진", "health.supplement",
     53000, "USD", "fixed", 9450, 4, "digital_unlimited", "🔥", "#ffedd5"),
    ("clickbank", "ClickBank", "Genius Wave 집중력", "digital.course",
     67000, "USD", "fixed", 67500, 2, "digital_unlimited", "🧠", "#ede9fe"),
    ("clickbank", "ClickBank", "Exipure 체중관리", "health.supplement",
     94000, "USD", "fixed", 67500, 6, "digital_unlimited", "🌿", "#dcfce7"),
    ("impact", "Impact", "프리미엄 요가매트 TPE", "sports",
     45000, "USD", "percent", 0.08, 15, "in_stock", "🧘", "#cffafe"),
    ("cj_affiliate", "CJ Affiliate", "스마트 워치 밴드 정품", "electronics.mobile",
     32000, "USD", "percent", 0.06, 20, "in_stock", "⌚", "#e0e7ff"),
    ("impact", "Impact", "강아지 사료 대용량 12kg", "pet",
     58000, "USD", "percent", 0.05, 30, "in_stock", "🐕", "#fef9c3"),
    ("coupang_partners", "쿠팡 파트너스", "무선 청소기 스탠드형", "electronics.appliance",
     210000, "KRW", "percent", 0.03, 18, "in_stock", "🧹", "#dbeafe"),
]


_CATEGORY_OF: dict[int, str] = {}


def _build() -> list[OfferOut]:
    # 1) EPC 계산
    computed = []
    for i, r in enumerate(_RAW, start=1):
        (net_code, net_name, title, cat, price, cur, kind, cr, rank, stock, emoji, color) = r
        price_krw = float(price)
        fixed_krw = float(cr) if kind == "fixed" else None
        rate = float(cr) if kind == "percent" else None
        e_sale = expected_earning_per_sale(price_krw, kind, rate, fixed_krw)
        epc = e_sale * cvr_prior(price_krw, cat)
        computed.append(dict(idx=i, r=r, cat=cat, price_krw=price_krw, e_sale=e_sale,
                             epc=epc, rank=rank, kind=kind, rate=rate, fixed_krw=fixed_krw))

    all_epcs = [c["epc"] for c in computed]
    all_ranks = [c["rank"] for c in computed]
    # 카테고리별 경쟁지수(공급 밀도 기반)
    from collections import Counter
    cat_counts = Counter(c["cat"] for c in computed)
    max_cat = max(cat_counts.values())

    offers: list[OfferOut] = []
    pis, demands = [], []
    for c in computed:
        pis.append(robust_quantile_norm(c["epc"], all_epcs))
        demands.append(rank_to_demand(c["rank"], all_ranks))
    th = SegmentThresholds(
        pi_hi=sorted(pis)[int(len(pis) * 0.7)], pi_lo=sorted(pis)[int(len(pis) * 0.3)],
        d_hi=sorted(demands)[int(len(demands) * 0.7)], d_lo=sorted(demands)[int(len(demands) * 0.3)],
        k_hi=0.6, k_lo=0.35,
    )

    for c, pi, demand in zip(computed, pis, demands, strict=True):
        (net_code, net_name, title, cat, price, cur, kind, cr, rank, stock, emoji, color) = c["r"]
        k = competition_index(cat_counts[cat] / max_cat, 0.4, 0.5)
        score = composite_score(pi, demand, k, freshness=1.0)
        seg = assign_segment(pi, demand, k, th)
        _CATEGORY_OF[c["idx"]] = cat
        price_krw = c["price_krw"]
        price_usd = (Decimal(str(price)) / _USD_KRW) if cur == "USD" else Decimal(str(price)) / _USD_KRW
        offers.append(OfferOut(
            id=c["idx"], product_id=c["idx"], network_code=net_code, network_name=net_name, title=title,
            thumbnail_url=_svg_thumb(emoji, color), landing_url=_real_url(net_code, title),
            price=Money(amount=Decimal(str(price)), currency="KRW" if cur == "KRW" else "KRW",
                        krw=Decimal(str(price)), usd=price_usd.quantize(Decimal("0.01"))),
            billing_type="CPS", commission_kind=kind,
            commission_rate=Decimal(str(c["rate"])) if c["rate"] is not None else None,
            commission_fixed=Money(amount=Decimal(str(c["fixed_krw"])), currency="KRW")
            if c["fixed_krw"] is not None else None,
            stock_status=stock, native_rank=rank, data_source="official_api",
            fetched_at=_NOW - timedelta(hours=(c["idx"] % 6)),
            score=ScoreOut(profitability=score, epc=round(c["epc"], 1), demand=round(demand, 3),
                           competition=round(k, 3), segment=seg),
        ))
    offers.sort(key=lambda o: o.score.profitability or 0, reverse=True)
    return offers


_OFFERS = _build()

_OPPORTUNITIES = [
    OpportunityOut(id=1, offer_id=3, title="커피 메이커 (기획전)", network_name="쿠팡 파트너스",
                   kind="commission_up", severity="high",
                   detail={"from": 0.03, "to": 0.15, "delta": 0.12}, detected_at=_NOW),
    OpportunityOut(id=2, offer_id=1, title="샤오미 창문 로봇청소기 X10", network_name="쿠팡 파트너스",
                   kind="price_drop", severity="warn",
                   detail={"from": 152000, "to": 136660, "pct": -0.101}, detected_at=_NOW - timedelta(hours=2)),
    OpportunityOut(id=3, offer_id=4, title="자동 분무기 미니", network_name="쿠팡 파트너스",
                   kind="stock_low", severity="warn",
                   detail={"from": "in_stock", "to": "low"}, detected_at=_NOW - timedelta(hours=5)),
    OpportunityOut(id=4, offer_id=7, title="럭셔리 뷰티 마스크 세트", network_name="Amazon",
                   kind="price_drop", severity="high",
                   detail={"from": 42000, "to": 30000, "pct": -0.285}, detected_at=_NOW - timedelta(hours=8)),
]


class DemoRepo:
    def list_offers(self, f) -> OfferListOut:  # noqa: ANN001
        from gamdap.api.schemas import Facet

        data = list(_OFFERS)
        if f.network:
            data = [o for o in data if o.network_code == f.network]
        if f.billing_type:
            data = [o for o in data if o.billing_type == f.billing_type]
        if f.category:
            data = [o for o in data if _CATEGORY_OF.get(o.id, "").startswith(f.category)]
        if f.segment:
            data = [o for o in data if o.score.segment == f.segment]

        relevance: dict[int, int] = {}
        if f.q:
            toks = [t for t in f.q.lower().split() if t]
            scored = []
            for o in data:
                title = o.title.lower()
                hits = sum(1 for t in toks if t in title)
                if hits or f.q.lower() in title:
                    relevance[o.id] = hits
                    scored.append(o)
            data = scored

        keymap = {
            "score": lambda o: o.score.profitability or 0,
            "epc": lambda o: o.score.epc or 0,
            "commission": lambda o: float(o.commission_rate or 0),
            "price": lambda o: float(o.price.krw or 0),
            "freshness": lambda o: o.fetched_at.timestamp(),
            "relevance": lambda o: (relevance.get(o.id, 0), o.score.profitability or 0),
        }
        sort_key = keymap.get("relevance" if f.q and f.sort in ("relevance", "score") else f.sort,
                              keymap["score"])
        data.sort(key=sort_key, reverse=True)

        total = len(data)
        start = (f.page - 1) * f.size
        # 패싯(네트워크·세그먼트 카운트)
        from collections import Counter
        net_c = Counter(o.network_code for o in data)
        seg_c = Counter(o.score.segment for o in data if o.score.segment)
        facets = {
            "network": [Facet(key=k, count=v) for k, v in net_c.most_common()],
            "segment": [Facet(key=k, count=v) for k, v in seg_c.most_common()],
        }
        return OfferListOut(data=data[start:start + f.size], page=f.page, size=f.size,
                            total=total, facets=facets)

    def get_offer(self, offer_id: int):
        return next((o for o in _OFFERS if o.id == offer_id), None)

    def rankings(self, category, country, limit):  # noqa: ANN001
        return sorted(_OFFERS, key=lambda o: o.score.profitability or 0, reverse=True)[:limit]

    def product_offers(self, product_id):  # noqa: ANN001
        return _OFFERS[:3]

    def summary(self) -> SummaryOut:
        epcs = [o.score.epc for o in _OFFERS if o.score.epc]
        return SummaryOut(
            total_offers=len(_OFFERS), active_networks=len({o.network_code for o in _OFFERS}),
            avg_epc=round(sum(epcs) / len(epcs), 1) if epcs else None,
            opportunities=len(_OPPORTUNITIES), last_ingest_at=_NOW)

    def networks(self) -> list[NetworkOut]:
        seen = {}
        for o in _OFFERS:
            seen.setdefault(o.network_code, o.network_name)
        return [NetworkOut(code=c, display_name=n, country=None, is_active=True)
                for c, n in seen.items()]

    def categories(self) -> list[CategoryOut]:
        return [
            CategoryOut(slug="electronics.appliance", name_ko="주방·생활가전", name_en="Appliances"),
            CategoryOut(slug="electronics.mobile", name_ko="휴대폰·태블릿", name_en="Mobile"),
            CategoryOut(slug="beauty.skincare", name_ko="스킨케어", name_en="Skincare"),
            CategoryOut(slug="health.supplement", name_ko="영양제·보충제", name_en="Supplements"),
            CategoryOut(slug="digital.course", name_ko="온라인 강의", name_en="Course"),
            CategoryOut(slug="sports", name_ko="스포츠·레저", name_en="Sports"),
            CategoryOut(slug="pet", name_ko="반려동물", name_en="Pet"),
        ]

    def opportunities(self, limit) -> list[OpportunityOut]:  # noqa: ANN001
        return _OPPORTUNITIES[:limit]

    def offer_history(self, offer_id, limit):  # noqa: ANN001
        base = 150000
        return [HistoryPoint(observed_at=_NOW - timedelta(days=d),
                             price_amount=Decimal(str(base - d * 2000)), stock_status="in_stock")
                for d in range(7, 0, -1)]

    def connectors(self) -> list[ConnectorOut]:
        net_count = {}
        for o in _OFFERS:
            net_count[o.network_code] = net_count.get(o.network_code, 0) + 1
        specs = [
            ("opendata", "공개데이터(샌드박스)", "opendata", "feed", True, True),
            ("coupang_partners", "쿠팡 파트너스", "coupang", "official_api", False, False),
            ("amazon_assoc", "Amazon", "amazon", "official_api", False, False),
            ("clickbank", "ClickBank", "clickbank", "official_api", False, False),
            ("cj_affiliate", "CJ Affiliate", "cj", "aggregator_api", False, False),
            ("impact", "Impact", "impact", "aggregator_api", False, False),
        ]
        return [
            ConnectorOut(code=c, display_name=n, adapter=a, data_source=ds,
                         healthy=h, configured=cfg, offer_count=net_count.get(c, 0),
                         last_ingest_at=_NOW if net_count.get(c) else None)
            for (c, n, a, ds, h, cfg) in specs
        ]

    def jobs(self, limit) -> list[JobOut]:  # noqa: ANN001
        return list(reversed(_DEMO_JOBS))[:limit]

    def trigger_ingest(self, network: str, keyword, limit) -> JobOut:  # noqa: ANN001
        """데모: opendata는 실제 라이브 수집(dummyjson), 나머지는 키 필요 안내."""
        global _JOB_SEQ
        _JOB_SEQ += 1
        started = datetime.now(UTC)
        if network == "opendata":
            from gamdap.connectors.opendata import OpenDataConnector
            try:
                res = next(OpenDataConnector().fetch_offers(keyword=keyword, limit=limit))
                job = JobOut(id=_JOB_SEQ, network_code=network, job_type="manual",
                             status="success", keyword=keyword,
                             rows_upserted=len(res.offers), rows_changed=len(res.offers),
                             fetched=len(res.offers), started_at=started,
                             finished_at=datetime.now(UTC))
            except Exception as exc:  # noqa: BLE001
                job = JobOut(id=_JOB_SEQ, network_code=network, job_type="manual",
                             status="failed", keyword=keyword, started_at=started,
                             finished_at=datetime.now(UTC), error=str(exc))
        else:
            job = JobOut(id=_JOB_SEQ, network_code=network, job_type="manual",
                         status="failed", keyword=keyword, started_at=started,
                         finished_at=datetime.now(UTC),
                         error="API 키 미설정 — .env 에 자격증명 등록 후 실행하세요")
        _DEMO_JOBS.append(job)
        return job


_JOB_SEQ = 100
_DEMO_JOBS: list[JobOut] = [
    JobOut(id=100, network_code="opendata", job_type="incremental", status="success",
           keyword="laptop", rows_upserted=30, rows_changed=12, fetched=30,
           started_at=_NOW - timedelta(hours=2), finished_at=_NOW - timedelta(hours=2)),
    JobOut(id=99, network_code="coupang_partners", job_type="incremental", status="success",
           keyword="에어프라이어", rows_upserted=28, rows_changed=5, fetched=30,
           started_at=_NOW - timedelta(hours=6), finished_at=_NOW - timedelta(hours=6)),
]
