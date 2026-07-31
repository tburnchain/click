"""독창적 SEO 자동 생성 — 중복 콘텐츠 회피 검증."""

import json

from gamdap.members import seo_export, seo_unique


def test_deterministic_same_seed():
    a = seo_unique.generate_profile("shop-abc123", "베스트샵", "shopping")
    b = seo_unique.generate_profile("shop-abc123", "베스트샵", "shopping")
    assert a == b  # 같은 slug → 항상 동일(안정적 색인)


def test_unique_across_sites_same_type_and_title():
    """핵심: 같은 유형·같은 제목이라도 slug가 다르면 SEO가 서로 달라야 한다."""
    profiles = [seo_unique.generate_profile(f"베스트샵-{h}", "베스트샵", "shopping")
                for h in ("a1b2c3", "d4e5f6", "778899", "aabbcc", "112233")]
    for field in ("seo_title", "seo_description", "hero_title", "about"):
        vals = [p[field] for p in profiles]
        # 5개 중 최소 4개는 서로 달라야(중복 콘텐츠 아님)
        assert len(set(vals)) >= 4, f"{field} 다양성 부족: {vals}"
    # 메타설명은 5개 모두 유니크가 이상적
    assert len({p["seo_description"] for p in profiles}) >= 4


def test_profile_has_all_seo_fields():
    p = seo_unique.generate_profile("deal-xyz", "오늘핫딜", "deal")
    for k in ("seo_title", "seo_description", "hero_title", "hero_subtitle",
              "about", "keywords", "faq_json", "usp_json", "seo_seed", "seo_auto"):
        assert p.get(k), f"{k} 누락"
    assert len(p["seo_title"]) <= 60
    assert len(p["seo_description"]) <= 158
    faq = json.loads(p["faq_json"])
    assert len(faq) == 3 and all(len(x) == 2 for x in faq)


def test_merge_preserves_user_values():
    gen = seo_unique.generate_profile("s-1", "샵", "shopping")
    merged = seo_unique.merge_into_config({"hero_title": "내가 직접 쓴 제목", "primary_color": "#000"}, gen)
    assert merged["hero_title"] == "내가 직접 쓴 제목"   # 사용자 값 보존
    assert merged["primary_color"] == "#000"
    assert merged["seo_description"] == gen["seo_description"]  # 빈 값은 자동 채움


def test_export_uses_unique_seo():
    """익스포트가 사이트별 독창적 title/description/faq 를 반영하는지."""
    def mk(slug):
        cfg = seo_unique.generate_profile(slug, "베스트샵", "shopping")
        return {"slug": slug, "title": "베스트샵", "kind": "shopping", "builder_name": "b",
                "status": "active", "site_config": cfg, "owner_info": {}, "owner_ref": None,
                "affiliate_applied": False, "product_count": 1,
                "products": [{"id": 1, "title": "상품", "thumbnail_url": None, "url": "https://x/p",
                              "network": "n", "price_krw": 1000, "price_amount": None,
                              "currency": "KRW", "segment": None, "brand": None, "category": "c"}]}
    h1 = seo_export.build_site_html(mk("베스트샵-aaa111"), base_url="https://e.com", slug="베스트샵-aaa111")
    h2 = seo_export.build_site_html(mk("베스트샵-bbb222"), base_url="https://e.com", slug="베스트샵-bbb222")
    import re
    t1 = re.search(r"<title>(.*?)</title>", h1).group(1)
    t2 = re.search(r"<title>(.*?)</title>", h2).group(1)
    d1 = re.search(r'name="description" content="(.*?)"', h1).group(1)
    d2 = re.search(r'name="description" content="(.*?)"', h2).group(1)
    assert t1 != t2, "두 사이트 타이틀이 동일(중복 콘텐츠 위험)"
    assert d1 != d2, "두 사이트 메타설명이 동일(중복 콘텐츠 위험)"
