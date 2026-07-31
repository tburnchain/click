"""SEO·AI검색 최적화 HTML 내보내기 검증."""

import json
import re

from gamdap.members import seo_export

DATA = {
    "slug": "my-shop-abc", "title": "베스트샵", "kind": "shopping",
    "builder_name": "쇼핑형 그리드몰", "status": "active",
    "site_config": {"hero_title": "이번 주 특가", "hero_subtitle": "최대 50% 할인",
                    "primary_color": "#2b6cb0"},
    "owner_info": {"상호": "김대표 스토어", "소개": "엄선 셀렉트샵"},
    "owner_ref": "REF123", "affiliate_applied": True, "product_count": 2,
    "products": [
        {"id": 1, "title": "무선 이어폰", "thumbnail_url": "https://cdn/a.jpg",
         "url": "https://shop.com/p/1?subId=REF123", "network": "쿠팡",
         "price_krw": 39000, "price_amount": None, "currency": "KRW",
         "segment": "goldmine", "brand": "소니", "category": "디지털"},
        {"id": 2, "title": "USB 케이블", "thumbnail_url": None,
         "url": "https://shop.com/p/2?subId=REF123", "network": "Amazon",
         "price_krw": None, "price_amount": 9.99, "currency": "USD",
         "segment": "cashcow", "brand": None, "category": "가전"},
    ],
}
BASE = "https://gamdap.example"


def test_html_has_core_seo_head():
    h = seo_export.build_site_html(DATA, base_url=BASE, slug=DATA["slug"])
    assert h.startswith("<!doctype html>")
    assert '<html lang="ko">' in h
    assert "<title>" in h and "베스트샵" in h
    assert '<meta name="description"' in h
    assert '<link rel="canonical" href="https://gamdap.example/site/my-shop-abc">' in h
    assert '<meta name="robots" content="index, follow' in h
    assert 'property="og:title"' in h and 'name="twitter:card"' in h


def test_jsonld_structured_data_valid():
    h = seo_export.build_site_html(DATA, base_url=BASE, slug=DATA["slug"])
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)
    assert m, "JSON-LD 블록 없음"
    graph = json.loads(m.group(1))["@graph"]
    types = {g["@type"] for g in graph}
    assert {"WebSite", "Organization", "BreadcrumbList", "ItemList", "FAQPage"} <= types
    website = next(g for g in graph if g["@type"] == "WebSite")
    assert website["potentialAction"]["@type"] == "SearchAction"       # AI/검색 최적화
    itemlist = next(g for g in graph if g["@type"] == "ItemList")
    prod = itemlist["itemListElement"][0]["item"]
    assert prod["@type"] == "Product"
    assert prod["offers"]["price"] == "39000" and prod["offers"]["priceCurrency"] == "KRW"
    assert prod["offers"]["url"].endswith("subId=REF123")             # 제휴코드 주입 링크


def test_index_cards_link_to_detail_and_carry_affiliate():
    h = seo_export.build_site_html(DATA, base_url=BASE, slug=DATA["slug"])
    assert 'href="product/1.html"' in h        # 다중 페이지: 카드→상세
    assert "subId=REF123" in h                 # 제휴코드는 JSON-LD/meta 에 유지


def test_product_detail_page_seo_and_sponsored():
    p = DATA["products"][0]
    related = DATA["products"][1:]
    h = seo_export.build_product_html(p, DATA, base_url=BASE, slug=DATA["slug"], related=related)
    assert h.startswith("<!doctype html>") and '<html lang="ko">' in h
    assert "무선 이어폰" in h
    assert 'rel="sponsored nofollow noopener"' in h     # 상세의 구매 버튼
    assert "subId=REF123" in h
    assert 'href="../index.html"' in h                  # 홈 상대 링크
    g = json.loads(re.search(r'ld\+json">(.*?)</script>', h, re.S).group(1))["@graph"]
    types = {x["@type"] for x in g}
    assert {"Product", "BreadcrumbList", "WebPage"} <= types
    prod = next(x for x in g if x["@type"] == "Product")
    assert prod["offers"]["price"] == "39000"


def test_bundle_is_multipage_with_deploy_configs():
    files = seo_export.build_bundle(DATA, base_url=BASE, slug=DATA["slug"], site_url="https://myshop.com")
    assert "index.html" in files
    assert "product/1.html" in files and "product/2.html" in files   # 상품 상세 다중 페이지
    for cfg in ("netlify.toml", "vercel.json", ".nojekyll", "README.md", "robots.txt",
                "sitemap.xml", "llms.txt"):
        assert cfg in files, f"{cfg} 누락"
    # 배포 도메인이 canonical/sitemap 에 반영
    assert "https://myshop.com/" in files["sitemap.xml"]
    assert "https://myshop.com/product/1.html" in files["sitemap.xml"]
    assert "https://myshop.com" in files["index.html"]


def test_zip_bytes_contain_all_files():
    import io
    import zipfile

    files = seo_export.build_bundle(DATA, base_url=BASE, slug=DATA["slug"], site_url="https://myshop.com")
    blob = seo_export.build_zip(files)
    assert blob[:2] == b"PK"  # zip 매직
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = set(zf.namelist())
    assert {"index.html", "product/1.html", "product/2.html", "README.md"} <= names


def test_robots_allows_ai_bots_and_sitemap():
    r = seo_export.build_robots(BASE, DATA["slug"])
    for bot in ("GPTBot", "PerplexityBot", "Google-Extended", "ClaudeBot", "OAI-SearchBot"):
        assert bot in r
    assert "Sitemap: https://gamdap.example/sitemap.xml" in r


def test_sitemap_and_llms():
    sm = seo_export.build_sitemap(BASE, DATA["slug"])
    assert "<urlset" in sm and "/site/my-shop-abc" in sm
    llms = seo_export.build_llms_txt(DATA, BASE, DATA["slug"])
    assert llms.startswith("# 베스트샵")
    assert "무선 이어폰" in llms and "₩39,000" in llms


def test_seo_report_checklist():
    rep = seo_export.seo_report(DATA)
    assert rep["jsonld_itemlist_product_offer"] and rep["llms_txt"] and rep["robots_txt_ai_bots"]
    assert rep["products_with_price"] == 2
    assert "GPTBot" in rep["ai_crawlers_allowed"]
