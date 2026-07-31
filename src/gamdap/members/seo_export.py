"""빌더 사이트 → SEO·AI검색 최적화 정적 HTML 코드 생성(구매자 전용 내보내기).

구매(클레임)한 회원에게 자신의 빌더 사이트를 **독립 실행 가능한 정적 HTML**로 공개해
직접 호스팅·수정·적용하게 한다. 생성 HTML은 다음을 반드시 포함한다:

SEO
  · 의미론적 마크업(header/nav/main/article/footer), lang/viewport/charset
  · title·meta description·keywords·canonical·robots(index,follow)
  · Open Graph + Twitter Card, 이미지 alt, theme-color
  · sitemap.xml / robots.txt 동봉

AEO(AI 검색 최적화 · GEO)
  · JSON-LD 구조화데이터: WebSite(SearchAction)·Organization·BreadcrumbList·
    ItemList+Product+Offer(가격·통화·재고·URL)·FAQPage·speakable
  · llms.txt(AI 크롤러용 요약) + robots 에 GPTBot/PerplexityBot/Google-Extended 허용
  · 질의응답형 FAQ 섹션·명료한 H1/H2·요약 블록(생성형 엔진 인용 최적화)

구매 딥링크에는 회원 제휴코드가 주입되고 rel="sponsored nofollow" 로 표기된다.
"""

from __future__ import annotations

import html
import json
from typing import Any

from gamdap.members import gads

_DEF_BASE = "https://example.com"


def _price_str(p: dict) -> tuple[str, str] | None:
    """(가격문자열, 통화코드) 또는 None."""
    if p.get("price_krw"):
        return (str(int(round(p["price_krw"]))), "KRW")
    if p.get("price_amount"):
        return (f"{p['price_amount']:.2f}", (p.get("currency") or "USD"))
    return None


def _desc(data: dict) -> str:
    # 생성 시 자동 생성된 독창적 메타설명(사이트마다 다름) 우선
    cfg = data.get("site_config") or {}
    owner = data.get("owner_info") or {}
    base = cfg.get("seo_description") or cfg.get("about") or cfg.get("hero_subtitle") or owner.get("소개") or ""
    if not base:
        cats = [p.get("category") for p in data["products"] if p.get("category")]
        uniq = list(dict.fromkeys(cats))[:4]
        base = f"{data['title']} — 엄선한 {data['product_count']}개 상품" + (
            f" ({', '.join(uniq)})" if uniq else "")
    return base[:157] + ("…" if len(base) > 157 else "")


def _keywords(data: dict) -> str:
    cfg = data.get("site_config") or {}
    kws: list[str] = []
    if cfg.get("keywords"):
        kws.extend(k.strip() for k in str(cfg["keywords"]).split(",") if k.strip())
    kws.append(data["title"])
    for p in data["products"]:
        for v in (p.get("brand"), p.get("category")):
            if v and v not in kws:
                kws.append(v)
    return ", ".join(dict.fromkeys(kws))[:220] if kws else data["title"]


def _faq(data: dict) -> list[tuple[str, str]]:
    # 생성 시 자동 생성된 독창적 FAQ(사이트마다 다름) 우선
    cfg = data.get("site_config") or {}
    if cfg.get("faq_json"):
        try:
            arr = json.loads(cfg["faq_json"])
            faq = [(str(q), str(a)) for q, a in arr if q and a]
            if faq:
                return faq
        except (ValueError, TypeError):
            pass
    title = data["title"]
    return [
        (f"{title}은(는) 어떤 사이트인가요?",
         f"{title}은(는) 엄선한 {data['product_count']}개의 인기 상품을 한곳에서 비교·구매할 수 있는 큐레이션 쇼핑 사이트입니다."),
        ("가격과 재고 정보는 최신인가요?",
         "상품 가격·재고는 각 판매처 데이터를 주기적으로 수집해 표시하며, 구매하기를 누르면 실제 판매처에서 최종 확인할 수 있습니다."),
        ("구매는 어디서 이뤄지나요?",
         "각 상품의 ‘구매하기’ 링크를 통해 해당 판매처로 이동하여 안전하게 결제합니다. 일부 링크는 제휴 활동으로 수수료를 받을 수 있습니다."),
    ]


def build_jsonld(data: dict, base_url: str, canonical: str) -> str:
    org_name = (data.get("owner_info") or {}).get("상호") or data["title"]
    items = []
    for i, p in enumerate(data["products"], start=1):
        product: dict[str, Any] = {
            "@type": "Product",
            "name": p["title"],
            "url": p.get("url") or canonical,
        }
        if p.get("thumbnail_url"):
            product["image"] = p["thumbnail_url"]
        if p.get("brand"):
            product["brand"] = {"@type": "Brand", "name": p["brand"]}
        if p.get("category"):
            product["category"] = p["category"]
        pr = _price_str(p)
        if pr:
            product["offers"] = {
                "@type": "Offer", "price": pr[0], "priceCurrency": pr[1],
                "availability": "https://schema.org/InStock",
                "url": p.get("url") or canonical,
            }
        items.append({"@type": "ListItem", "position": i, "item": product})

    graph = [
        {
            "@type": "WebSite", "name": data["title"], "url": canonical,
            "inLanguage": "ko", "description": _desc(data),
            "potentialAction": {
                "@type": "SearchAction",
                "target": {"@type": "EntryPoint",
                           "urlTemplate": f"{canonical}?q={{search_term_string}}"},
                "query-input": "required name=search_term_string",
            },
        },
        {"@type": "Organization", "name": org_name, "url": canonical},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "홈", "item": canonical}]},
        {"@type": "ItemList", "name": data["title"],
         "numberOfItems": len(items), "itemListElement": items},
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in _faq(data)]},
        {"@type": "WebPage", "url": canonical,
         "speakable": {"@type": "SpeakableSpecification", "cssSelector": ["h1", ".seo-summary"]}},
    ]
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)


_CSS = """
:root{--primary:%(primary)s;--ink:#1a1a1a;--muted:#666;--line:#eee;--bg:#fff}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:var(--ink);background:var(--bg);line-height:1.5}
a{color:inherit;text-decoration:none}img{max-width:100%%;display:block}
.wrap{max-width:1160px;margin:0 auto;padding:0 20px}
header.site{border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
.bar{display:flex;align-items:center;gap:16px;padding:14px 0}
.logo{font-size:22px;font-weight:900;color:var(--primary)}
nav.main{display:flex;gap:16px;font-size:14px;color:var(--muted);flex-wrap:wrap}
.hero{background:linear-gradient(135deg,color-mix(in srgb,var(--primary) 12%%,#fff),#fff);padding:40px 0;text-align:center}
.hero h1{margin:0 0 8px;font-size:30px}.hero p{color:var(--muted);margin:0}
.seo-summary{max-width:720px;margin:14px auto 0;color:#444;font-size:15px}
main{padding:28px 0}.sec-h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px}
.card{border:1px solid var(--line);border-radius:12px;overflow:hidden;transition:.12s;background:#fff}
.card:hover{box-shadow:0 8px 24px rgba(0,0,0,.08);transform:translateY(-2px)}
.card .thumb{aspect-ratio:1;background:#f6f6f6}.card .b{padding:12px}
.brand{font-size:12px;color:var(--muted)}.name{font-size:14px;font-weight:600;line-height:1.35;margin:2px 0 8px;min-height:38px}
.price{font-weight:800;color:var(--primary);font-size:16px}
.buy{display:block;text-align:center;margin-top:10px;background:var(--primary);color:#fff;font-weight:800;padding:10px;border-radius:8px}
.faq{max-width:820px;margin:34px auto 0}.faq h2{font-size:20px}.faq details{border-bottom:1px solid var(--line);padding:12px 0}
.faq summary{font-weight:700;cursor:pointer}.faq p{color:#444;margin:8px 0 0}
footer.site{border-top:1px solid var(--line);padding:28px 0;color:var(--muted);font-size:13px;text-align:center;margin-top:36px}
.ftc{font-size:12px;color:#999;margin-top:6px}
.ad-slot{position:relative;max-width:1160px;margin:16px auto;padding:0 20px}
.ad-slot .ad-tag{font-size:9px;color:#aab2c0;letter-spacing:.5px}
.ad-anchor{position:sticky;bottom:0;background:#fff;padding:6px 20px;box-shadow:0 -3px 12px rgba(0,0,0,.06);margin:0;max-width:none;z-index:6}
.crumb{font-size:13px;color:var(--muted);padding:14px 0}.crumb a:hover{color:var(--primary)}
.pd{display:grid;grid-template-columns:1fr 1fr;gap:32px;padding:12px 0 8px}
.pd .img{background:#f6f6f6;border-radius:14px;overflow:hidden;aspect-ratio:1}
.pd h1{font-size:26px;margin:0 0 6px;line-height:1.3}
.pd .price{font-size:28px;font-weight:900;color:var(--primary);margin:12px 0}
.pd .buy{max-width:320px;font-size:16px;padding:14px}
.pd .desc{color:#444;margin-top:16px;line-height:1.8}
.rel{margin-top:36px}.rel h2{font-size:20px}
@media(max-width:760px){.pd{grid-template-columns:1fr;gap:18px}}
"""


def build_site_html(data: dict, *, base_url: str = _DEF_BASE, slug: str | None = None,
                    canonical_url: str | None = None) -> str:
    slug = slug or data.get("slug") or "site"
    canonical = canonical_url or f"{base_url.rstrip('/')}/site/{slug}"
    cfg = data.get("site_config") or {}
    owner = data.get("owner_info") or {}
    primary = cfg.get("primary_color") or "#ff4d4f"
    hero_title = cfg.get("hero_title") or data["title"]
    hero_sub = cfg.get("hero_subtitle") or owner.get("소개") or "엄선한 인기 상품을 한곳에서 비교·구매하세요."
    biz = owner.get("상호") or data["title"]
    desc = _desc(data)
    og_image = next((p["thumbnail_url"] for p in data["products"] if p.get("thumbnail_url")), "")
    # 사이트별 독창적 타이틀(중복 회피) 우선
    title_tag = (cfg.get("seo_title") or f"{data['title']} · {hero_title}")[:65]
    e = html.escape
    cats = list(dict.fromkeys([p["category"] for p in data["products"] if p.get("category")]))[:6]
    gads_head = gads.gtag_head(cfg)    # 구글광고 추적(설정 시)
    gads_body = gads.tracking_js(cfg)
    ads_loader = gads.adsense_loader(cfg)   # 애드센스(설정 시)
    ads_center = gads.adsense_unit(cfg, fmt="auto", style="display:block;min-height:110px")
    ads_bottom = gads.adsense_unit(cfg, fmt="horizontal", style="display:block;min-height:90px")
    ad_center_html = f'<div class="ad-slot"><span class="ad-tag">광고 · Google</span>{ads_center}</div>' if ads_center else ""
    ad_bottom_html = f'<div class="ad-slot ad-anchor"><span class="ad-tag">광고 · Google</span>{ads_bottom}</div>' if ads_bottom else ""

    def card(p: dict) -> str:
        pr = _price_str(p)
        price_html = ""
        if pr:
            disp = ("₩" + f"{int(pr[0]):,}") if pr[1] == "KRW" else f"{pr[1]} {pr[0]}"
            price_html = f'<div class="price" itemprop="price" content="{e(pr[0])}">{e(disp)}</div>' \
                         f'<meta itemprop="priceCurrency" content="{e(pr[1])}">'
        img = (f'<img class="thumb" src="{e(p["thumbnail_url"])}" alt="{e(p["title"])}" '
               f'loading="lazy" itemprop="image">' if p.get("thumbnail_url")
               else '<div class="thumb"></div>')
        brand = f'<div class="brand" itemprop="brand">{e(p["brand"])}</div>' if p.get("brand") else ""
        buy = e(p.get("url") or canonical)
        detail = f'product/{p["id"]}.html'   # 다중 페이지: 카드→상품 상세
        return (
            f'<article class="card" itemscope itemtype="https://schema.org/Product">'
            f'<a href="{detail}">{img}</a><div class="b">{brand}'
            f'<h3 class="name" itemprop="name"><a href="{detail}">{e(p["title"])}</a></h3>'
            f'<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">{price_html}'
            f'<link itemprop="availability" href="https://schema.org/InStock">'
            f'<meta itemprop="url" content="{buy}">'
            f'<a class="buy" href="{detail}">자세히 보기</a></div></div></article>'
        )

    faq_html = "".join(
        f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in _faq(data))
    nav_html = "".join(f'<a href="#{e(c)}">{e(c)}</a>' for c in cats) or '<a href="#all">전체</a>'
    cards = "".join(card(p) for p in data["products"])

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title_tag)}</title>
<meta name="description" content="{e(desc)}">
<meta name="keywords" content="{e(_keywords(data))}">
<meta name="author" content="{e(biz)}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{e(canonical)}">
<meta name="theme-color" content="{e(primary)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(data['title'])}">
<meta property="og:title" content="{e(title_tag)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:locale" content="ko_KR">
{f'<meta property="og:image" content="{e(og_image)}">' if og_image else ''}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title_tag)}">
<meta name="twitter:description" content="{e(desc)}">
{f'<meta name="twitter:image" content="{e(og_image)}">' if og_image else ''}
<link rel="alternate" type="text/plain" href="/llms.txt" title="AI 요약">
<script type="application/ld+json">{build_jsonld(data, base_url, canonical)}</script>
{gads_head}
{ads_loader}
<style>{_CSS % {'primary': primary}}</style>
</head>
<body>
<header class="site"><div class="wrap bar">
  <a class="logo" href="{e(canonical)}">{e(data['title'])}</a>
  <nav class="main" aria-label="카테고리">{nav_html}</nav>
</div></header>
<section class="hero"><div class="wrap">
  <h1>{e(hero_title)}</h1>
  <p>{e(hero_sub)}</p>
  <p class="seo-summary">{e(desc)}</p>
</div></section>
{ad_center_html}
<main class="wrap"><div class="sec-h"><h2 id="all">전체 상품 {data['product_count']}개</h2>
  <span>{e(biz)}</span></div>
  <div class="grid">{cards}</div>
  <section class="faq"><h2>자주 묻는 질문</h2>{faq_html}</section>
</main>
<footer class="site"><div class="wrap">
  <strong>{e(data['title'])}</strong>{f' · {e(biz)}' if biz != data['title'] else ''}
  <div class="ftc">※ 일부 링크는 제휴 활동으로 수수료를 받을 수 있습니다. · Powered by TBURN.CLICK</div>
</div></footer>
{ad_bottom_html}
{gads_body}
</body>
</html>"""


def build_robots(base_url: str, slug: str) -> str:
    canonical = f"{base_url.rstrip('/')}/site/{slug}"
    # 일반 크롤러 + 주요 AI 크롤러 명시 허용(AI 검색 최적화)
    return (
        "User-agent: *\nAllow: /\n\n"
        "User-agent: GPTBot\nAllow: /\n\n"
        "User-agent: OAI-SearchBot\nAllow: /\n\n"
        "User-agent: PerplexityBot\nAllow: /\n\n"
        "User-agent: Google-Extended\nAllow: /\n\n"
        "User-agent: ClaudeBot\nAllow: /\n\n"
        f"Sitemap: {base_url.rstrip('/')}/sitemap.xml\n"
        f"# canonical: {canonical}\n"
    )


def build_sitemap(base_url: str, slug: str) -> str:
    canonical = f"{base_url.rstrip('/')}/site/{slug}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{html.escape(canonical)}</loc>"
        "<changefreq>daily</changefreq><priority>1.0</priority></url>\n"
        "</urlset>\n"
    )


def build_llms_txt(data: dict, base_url: str, slug: str) -> str:
    """AI 검색/에이전트용 요약(llms.txt) — 생성형 엔진이 사이트를 정확히 인용하도록."""
    canonical = f"{base_url.rstrip('/')}/site/{slug}"
    lines = [
        f"# {data['title']}", "",
        f"> {_desc(data)}", "",
        f"- 유형: 큐레이션 쇼핑 사이트 ({data.get('builder_name','')})",
        f"- 상품 수: {data['product_count']}",
        f"- URL: {canonical}", "",
        "## 대표 상품",
    ]
    for p in data["products"][:20]:
        pr = _price_str(p)
        price = (f" — ₩{int(pr[0]):,}" if pr and pr[1] == "KRW"
                 else (f" — {pr[1]} {pr[0]}" if pr else ""))
        lines.append(f"- {p['title']}{price} ({p.get('url') or canonical})")
    lines += ["", "## 고지", "일부 링크는 제휴 활동으로 수수료를 받을 수 있습니다."]
    return "\n".join(lines) + "\n"


def _product_desc(p: dict, site_title: str) -> str:
    brand = f"{p['brand']} " if p.get("brand") else ""
    cat = p.get("category") or "인기"
    return (f"{brand}{p['title']} — {cat} 카테고리의 베스트셀러입니다. 검증된 품질과 합리적인 가격으로 "
            f"많은 분들이 선택했습니다. 아래 ‘구매하기’로 판매처에서 최신 가격·재고를 확인하세요. ({site_title})")


def build_product_html(p: dict, data: dict, *, base_url: str = _DEF_BASE, slug: str | None = None,
                       related: list[dict] | None = None, canonical_url: str | None = None) -> str:
    """상품 상세 페이지(다중 페이지). 구매 버튼에 회원 제휴코드 딥링크 + Product JSON-LD."""
    slug = slug or data.get("slug") or "site"
    e = html.escape
    cfg = data.get("site_config") or {}
    primary = cfg.get("primary_color") or "#ff4d4f"
    gads_head = gads.gtag_head(cfg)
    gads_body = gads.tracking_js(cfg)
    home = f"{base_url.rstrip('/')}/site/{slug}"
    canonical = canonical_url or f"{home}/product/{p['id']}.html"
    buy = p.get("url") or home
    desc = _product_desc(p, data["title"])
    pr = _price_str(p)
    price_disp = ""
    if pr:
        price_disp = ("₩" + f"{int(pr[0]):,}") if pr[1] == "KRW" else f"{pr[1]} {pr[0]}"
    cat = p.get("category") or "상품"

    product_ld: dict[str, Any] = {"@type": "Product", "name": p["title"], "url": canonical,
                                  "description": desc}
    if p.get("thumbnail_url"):
        product_ld["image"] = p["thumbnail_url"]
    if p.get("brand"):
        product_ld["brand"] = {"@type": "Brand", "name": p["brand"]}
    if p.get("category"):
        product_ld["category"] = p["category"]
    if pr:
        product_ld["offers"] = {"@type": "Offer", "price": pr[0], "priceCurrency": pr[1],
                                "availability": "https://schema.org/InStock", "url": buy}
    jsonld = json.dumps({"@context": "https://schema.org", "@graph": [
        product_ld,
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "홈", "item": "../index.html"},
            {"@type": "ListItem", "position": 2, "name": cat, "item": canonical},
            {"@type": "ListItem", "position": 3, "name": p["title"], "item": canonical}]},
        {"@type": "WebPage", "url": canonical,
         "speakable": {"@type": "SpeakableSpecification", "cssSelector": ["h1", ".desc"]}},
    ]}, ensure_ascii=False)

    img = (f'<img src="{e(p["thumbnail_url"])}" alt="{e(p["title"])}" itemprop="image">'
           if p.get("thumbnail_url") else "")
    price_html = (f'<div class="price"><span itemprop="price" content="{e(pr[0])}">{e(price_disp)}</span>'
                  f'<meta itemprop="priceCurrency" content="{e(pr[1])}"></div>') if pr else ""
    rel_cards = ""
    for r in (related or [])[:4]:
        rimg = (f'<img class="thumb" src="{e(r["thumbnail_url"])}" alt="{e(r["title"])}" loading="lazy">'
                if r.get("thumbnail_url") else '<div class="thumb"></div>')
        rel_cards += (f'<article class="card"><a href="{r["id"]}.html">{rimg}'
                      f'<div class="b"><h3 class="name">{e(r["title"])}</h3></div></a></article>')
    og_img = p.get("thumbnail_url") or ""
    title_tag = f"{p['title']} · {data['title']}"[:65]

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title_tag)}</title>
<meta name="description" content="{e(desc[:157])}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{e(canonical)}">
<meta name="theme-color" content="{e(primary)}">
<meta property="og:type" content="product">
<meta property="og:title" content="{e(title_tag)}">
<meta property="og:description" content="{e(desc[:157])}">
<meta property="og:url" content="{e(canonical)}">
{f'<meta property="og:image" content="{e(og_img)}">' if og_img else ''}
<meta name="twitter:card" content="summary_large_image">
{f'<meta name="twitter:image" content="{e(og_img)}">' if og_img else ''}
<script type="application/ld+json">{jsonld}</script>
{gads_head}
<style>{_CSS % {'primary': primary}}</style>
</head>
<body>
<header class="site"><div class="wrap bar">
  <a class="logo" href="../index.html">{e(data['title'])}</a>
</div></header>
<div class="wrap">
  <nav class="crumb" aria-label="위치"><a href="../index.html">홈</a> › {e(cat)} › <strong>{e(p['title'])}</strong></nav>
  <div class="pd">
    <div class="img" itemscope itemtype="https://schema.org/Product">{img}</div>
    <div itemscope itemtype="https://schema.org/Product">
      {f'<div class="brand" itemprop="brand">{e(p["brand"])}</div>' if p.get('brand') else ''}
      <h1 itemprop="name">{e(p['title'])}</h1>
      <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
        {price_html}<link itemprop="availability" href="https://schema.org/InStock">
        <a class="buy" itemprop="url" href="{e(buy)}" target="_blank" rel="sponsored nofollow noopener"
           data-buy data-id="{p['id']}" data-price="{pr[0] if pr else 0}" data-cur="{pr[1] if pr else 'KRW'}">구매하기</a>
      </div>
      <p class="desc" itemprop="description">{e(desc)}</p>
      <p class="ftc">※ 이 링크는 제휴 활동으로 수수료를 받을 수 있습니다.</p>
    </div>
  </div>
  {f'<section class="rel"><h2>함께 보면 좋은 상품</h2><div class="grid">{rel_cards}</div></section>' if rel_cards else ''}
</div>
<footer class="site"><div class="wrap"><strong>{e(data['title'])}</strong>
  <div class="ftc">Powered by TBURN.CLICK</div></div></footer>
{gads_body}
</body>
</html>"""


def bundle_sitemap(site_url: str, product_ids: list[int]) -> str:
    base = site_url.rstrip("/")
    urls = [f"{base}/"] + [f"{base}/product/{i}.html" for i in product_ids]
    entries = "".join(
        f"  <url><loc>{html.escape(u)}</loc><changefreq>daily</changefreq></url>\n" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + entries + "</urlset>\n")


_NETLIFY = ('# Netlify 설정 — 정적 사이트 배포\n[build]\n  publish = "."\n\n'
            '[[headers]]\n  for = "/*"\n  [headers.values]\n'
            '    X-Content-Type-Options = "nosniff"\n')
_VERCEL = ('{\n  "cleanUrls": true,\n  "trailingSlash": false,\n'
           '  "headers": [{"source": "/(.*)", "headers": '
           '[{"key": "X-Content-Type-Options", "value": "nosniff"}]}]\n}\n')


def build_readme(data: dict, slug: str, site_url: str) -> str:
    n = data["product_count"]
    return f"""# {data['title']} — 정적 사이트 배포 가이드

이 번들은 **SEO·AI검색(AEO) 최적화된 정적 사이트**입니다. 서버 없이 어디서든 호스팅됩니다.

## 포함 파일
- `index.html` — 메인(상품 {n}개, JSON-LD ItemList)
- `product/*.html` — 상품 상세 {n}페이지(각 Product/Offer JSON-LD)
- `sitemap.xml`, `robots.txt`(GPTBot·PerplexityBot·Google-Extended·ClaudeBot 허용), `llms.txt`(AI 요약)
- `netlify.toml`, `vercel.json`, `.nojekyll` — 배포 설정

## 배포 (택1)

### 1) Netlify (드래그&드롭, 가장 쉬움)
1. https://app.netlify.com/drop 접속
2. 이 폴더(압축 해제본)를 통째로 드래그&드롭
3. 발급된 URL이 곧 내 사이트. (커스텀 도메인 연결 가능)

### 2) Vercel
1. `npm i -g vercel` 후 이 폴더에서 `vercel` 실행 (또는 대시보드에서 폴더 업로드)
2. 프레임워크 없음(Other) 선택 → 배포

### 3) GitHub Pages
1. GitHub에 새 저장소 생성 후 이 폴더 파일 전체 push
2. Settings → Pages → Branch: `main` / 루트(`/`) 선택 → 저장
3. `.nojekyll` 이 포함되어 있어 그대로 정적 서빙됩니다.

## 배포 후 필수 체크(SEO/AEO)
- `sitemap.xml`, `robots.txt` 의 도메인을 **실제 배포 도메인**으로 교체 (현재: `{site_url}`)
- Google Search Console·Bing Webmaster 에 sitemap 제출
- 리치 결과 테스트: https://search.google.com/test/rich-results 로 JSON-LD 검증
- 구매 링크에는 회원 제휴코드가 이미 주입되어 있습니다(`rel="sponsored"`).

Powered by TBURN.CLICK
"""


def build_bundle(data: dict, *, base_url: str = _DEF_BASE, slug: str | None = None,
                 site_url: str | None = None) -> dict[str, str]:
    """배포용 다중 페이지 번들 {상대경로: 내용}. site_url 은 배포 도메인(canonical 기준)."""
    slug = slug or data.get("slug") or "site"
    site_url = (site_url or base_url).rstrip("/")
    files: dict[str, str] = {}
    files["index.html"] = build_site_html(data, base_url=base_url, slug=slug,
                                          canonical_url=f"{site_url}/")
    for p in data["products"]:
        related = [q for q in data["products"]
                   if q["id"] != p["id"] and (q.get("category") == p.get("category"))][:4]
        if len(related) < 4:
            related += [q for q in data["products"]
                        if q["id"] != p["id"] and q not in related][:4 - len(related)]
        files[f"product/{p['id']}.html"] = build_product_html(
            p, data, base_url=base_url, slug=slug, related=related,
            canonical_url=f"{site_url}/product/{p['id']}.html")
    files["robots.txt"] = build_robots(site_url, slug)
    files["sitemap.xml"] = bundle_sitemap(site_url, [p["id"] for p in data["products"]])
    files["llms.txt"] = build_llms_txt(data, site_url, slug)
    files["netlify.toml"] = _NETLIFY
    files["vercel.json"] = _VERCEL
    files[".nojekyll"] = ""
    files["README.md"] = build_readme(data, slug, site_url)
    return files


def build_zip(files: dict[str, str]) -> bytes:
    """번들 파일맵 → zip 바이트."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()


def seo_report(data: dict) -> dict[str, Any]:
    """적용된 SEO/AEO 항목 체크리스트(대시보드 표시용)."""
    priced = sum(1 for p in data["products"] if _price_str(p))
    return {
        "title_tag": True, "meta_description": True, "canonical": True,
        "open_graph": True, "twitter_card": True, "robots_meta": True,
        "semantic_html": True, "image_alt": True,
        "jsonld_website_searchaction": True, "jsonld_itemlist_product_offer": True,
        "jsonld_organization": True, "jsonld_breadcrumb": True,
        "jsonld_faqpage": True, "jsonld_speakable": True,
        "sitemap_xml": True, "robots_txt_ai_bots": True, "llms_txt": True,
        "multi_page_detail": True,
        "products_total": data["product_count"], "products_with_price": priced,
        "total_pages": 1 + data["product_count"],
        "ai_crawlers_allowed": ["GPTBot", "OAI-SearchBot", "PerplexityBot",
                                "Google-Extended", "ClaudeBot"],
        "google_ads": gads.gads_report(data.get("site_config")),
    }
