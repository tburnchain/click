"""독창적 SEO 자동 생성 — 중복 콘텐츠 회피 엔진.

같은 유형(shopping/deal/…)의 빌더를 다수의 사용자가 만들어도 구글이 '동일 콘텐츠'로
인식해 색인에서 배제하지 않도록, **사이트 생성 시점**에 각 사이트의 고유 식별자(slug,
6자리 랜덤 해시 포함)를 시드로 결정적(deterministic)이되 사이트마다 완전히 다른
SEO 카피(타이틀·메타설명·히어로·소개·FAQ·키워드·USP)를 자동 생성한다.

- 결정적: 같은 slug → 항상 같은 카피(안정적 canonical/색인).
- 유일적: slug가 6-hex 랜덤을 포함 → 사이트마다 시드가 달라 카피가 서로 다름.
- 조합수: 각 슬롯 15~25개 × 다수 슬롯 → 사실상 무한(수십억) 조합.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any

# ── 어휘 풀(각 15~25개) ──
_ADJ = ["엄선한", "알뜰한", "트렌디한", "검증된", "특별한", "실속 있는", "인기 있는",
        "합리적인", "믿을 수 있는", "세심하게 고른", "매일 새로워지는", "감각적인",
        "가성비 좋은", "요즘 뜨는", "손이 가는", "만족도 높은", "취향 저격", "발빠른",
        "똑똑한", "프리미엄", "실용적인", "센스 있는"]
_BENEFIT = ["최저가", "오늘의 특가", "빠른 발송", "큐레이션", "실사용 후기", "한정 혜택",
            "무료배송", "즉시 할인", "적립 혜택", "베스트 아이템", "추천 상품", "인기 랭킹"]
_ANGLE = ["당신의 취향을 아는", "발품 팔 필요 없는", "시간을 아껴주는", "지갑을 지켜주는",
          "고르는 재미가 있는", "매일 들르고 싶은", "믿고 사는", "실패 없는 선택의",
          "가격 비교가 끝나는", "트렌드를 앞서가는", "합리적 소비를 위한", "덕후가 인정한"]
_AUDIENCE = ["실속파", "트렌드세터", "알뜰 쇼핑러", "바쁜 현대인", "첫 구매자", "단골 고객",
             "선물 고민러", "가성비족", "얼리어답터", "취향 뚜렷한 당신"]
_KIND_WORD = {
    "shopping": "쇼핑몰", "deal": "핫딜", "ranking": "베스트 랭킹", "boutique": "셀렉트샵",
    "search": "검색 포탈", "directory": "가격비교", "coupon": "쿠폰 혜택", "blog": "리뷰 블로그",
    "article": "매거진", "enterprise": "브랜드몰", "general": "링크 모음", "mixed": "종합 허브",
    "google_ads": "특가 랜딩",
}
_KIND_VERB = {
    "shopping": "쇼핑하세요", "deal": "지금 챙기세요", "ranking": "순위로 확인하세요",
    "boutique": "만나보세요", "search": "검색하세요", "directory": "비교하세요",
    "coupon": "받아가세요", "blog": "후기로 확인하세요", "article": "읽어보세요",
    "enterprise": "만나보세요", "general": "둘러보세요", "mixed": "탐색하세요",
    "google_ads": "지금 확인하세요",
}

_TITLE_PAT = [
    "{title} · {adj} {kw} 셀렉션",
    "{kw} 셀렉트 — {title}",
    "{title} | {adj} {kindw}",
    "{title} · {audience} 추천 {kindw}",
    "{adj} {kw} 모음, {title}",
    "{title} — {year} {kindw} 베스트",
    "{kw} 큐레이션, {title}",
    "{title}: {adj} {kw} 셀렉션",
]
_DESC_PAT = [
    "{angle} {kindw} {title}. {adj} {kw}·{kw2} 셀렉션으로 지금 {verb}. {audience} 맞춤 큐레이션.",
    "{title} — {adj} {kw}·{kw2} 셀렉션을 {audience}에게. {angle} 큐레이션, 지금 {verb}.",
    "{adj} {kw}부터 {kw2}까지 — {title}에서 {angle} 셀렉션을 경험하세요. 매일 업데이트되는 추천 아이템.",
    "{audience} 맞춤 {title}. {kw}·{kw2} 중 {angle} 상품만 골라 담았습니다. 지금 {verb}.",
    "{title} — {adj} {kindw}. {angle} 셀렉션과 {kw} 정보를 한 번에. 지금 바로 {verb}.",
]
_HERO_TITLE_PAT = [
    "{adj} {kw}, 지금 {title}에서", "{title}의 {adj} {kindw}", "오늘의 {kw}, 지금 {verb}",
    "{angle} {kindw}", "{adj} {kw} 셀렉션", "{audience}의 {kindw}", "{kw} 셀렉션은 여기서",
    "{title} {adj} 컬렉션",
]
_HERO_SUB_PAT = [
    "{angle} 셀렉션으로 실패 없이 {verb}.", "{adj} {kw}·{kw2} 셀렉션을 한곳에서.",
    "매일 새로워지는 {kindw}, {audience} 맞춤.", "{kw} · {adj} 큐레이션.",
    "발품은 그만 — {angle} 추천만 담았습니다.", "{audience}가 만족한 {adj} {kindw}.",
]
_ABOUT_PAT = [
    "{title}은(는) {angle} {kindw}입니다. {adj} {kw}·{kw2} 셀렉션을 엄선해 {audience}가 고르는 수고를 덜어드립니다. 검증된 판매처의 상품만 소개하며, 인기·신선도·가격을 함께 고려해 매일 셀렉션을 업데이트합니다.",
    "복잡한 비교는 그만. {title}은(는) {adj} {kw} 셀렉션을 {angle} 방식으로 정리한 {kindw}입니다. {audience}의 취향과 예산에 맞춘 추천으로, 클릭 한 번에 원하는 상품을 지금 {verb}.",
    "{audience} 맞춤 {title}. 수많은 {kw} 중 {angle} 상품만 선별했습니다. {adj} 큐레이션과 투명한 가격 정보로, 후회 없는 선택을 돕는 {kindw}입니다.",
]
_USP_POOL = [
    "🔎 {angle} 큐레이션", "💰 {kw} 혜택 정리", "🚚 검증된 판매처만", "⭐ 실사용 후기 반영",
    "🆕 매일 셀렉션 업데이트", "🎯 {audience} 맞춤 추천", "🛡️ 안전 결제 안내", "📊 인기·가격 종합 랭킹",
    "🎁 오늘의 한정 혜택", "🧭 발품 없는 비교",
]
_FAQ_POOL = [
    ("{title}은(는) 어떤 곳인가요?",
     "{title}은(는) {angle} {kindw}로, {adj} {kw} 셀렉션을 {audience}에게 소개합니다."),
    ("가격 정보는 최신인가요?",
     "각 판매처 데이터를 주기적으로 수집해 표시하며, 구매 전 판매처에서 최종 가격을 확인할 수 있습니다."),
    ("어떤 기준으로 상품을 고르나요?",
     "인기도·신선도·가격을 함께 고려해 {angle} 상품만 선별하고, 셀렉션을 꾸준히 업데이트합니다."),
    ("구매는 어디서 이뤄지나요?",
     "‘구매하기’ 링크로 해당 판매처에서 결제합니다. 일부 링크는 제휴 활동으로 수수료를 받을 수 있습니다."),
    ("{kw} 정보는 어디서 확인하나요?",
     "상품 상세에서 {kw}·{kw2} 정보를 확인하고, 판매처 페이지에서 적용해 구매하시면 됩니다."),
    ("모바일에서도 잘 보이나요?",
     "반응형으로 제작되어 PC·모바일 어디서든 최적화된 화면으로 {verb}."),
]


def _rng(seed: str) -> random.Random:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))


def generate_profile(seed: str, title: str, kind: str, *, year: int = 2026) -> dict[str, Any]:
    """slug 등 고유 시드로 사이트별 독창적 SEO 카피 생성(결정적)."""
    r = _rng(seed)
    adj, adj2 = r.sample(_ADJ, 2)
    kw, kw2 = r.sample(_BENEFIT, 2)
    angle = r.choice(_ANGLE)
    audience = r.choice(_AUDIENCE)
    kindw = _KIND_WORD.get(kind, "링크 포탈")
    verb = _KIND_VERB.get(kind, "둘러보세요")
    ctx = {"title": title, "adj": adj, "adj2": adj2, "kw": kw, "kw2": kw2,
           "angle": angle, "audience": audience, "kindw": kindw, "verb": verb, "year": year}

    def fmt(pat: str) -> str:
        return pat.format(**ctx)

    seo_title = fmt(r.choice(_TITLE_PAT))[:60]
    seo_desc = fmt(r.choice(_DESC_PAT))[:158]
    hero_title = fmt(r.choice(_HERO_TITLE_PAT))
    hero_sub = fmt(r.choice(_HERO_SUB_PAT))
    about = fmt(r.choice(_ABOUT_PAT))
    usps = [fmt(p) for p in r.sample(_USP_POOL, 3)]
    faq = [(fmt(q), fmt(a)) for q, a in r.sample(_FAQ_POOL, 3)]
    # 키워드: 벤치마크 어휘를 섞어 유일 조합
    kws = [title, kw, kw2, kindw, angle.replace(" ", ""), audience, adj]
    r.shuffle(kws)

    return {
        "seo_auto": "1", "seo_seed": seed,
        "seo_title": seo_title, "seo_description": seo_desc,
        "hero_title": hero_title, "hero_subtitle": hero_sub,
        "about": about, "keywords": ", ".join(dict.fromkeys(kws)),
        "usp_json": json.dumps(usps, ensure_ascii=False),
        "faq_json": json.dumps(faq, ensure_ascii=False),
    }


def merge_into_config(existing: dict | None, generated: dict) -> dict:
    """기존 config를 보존하며 자동 SEO를 병합(사용자 수정값 우선)."""
    cfg = dict(existing or {})
    for k, v in generated.items():
        if not str(cfg.get(k, "")).strip():   # 사용자가 이미 채운 값은 덮지 않음
            cfg[k] = v
    return cfg
