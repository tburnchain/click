"""구글광고(Google Ads) 추적 스니펫 검증."""

from gamdap.members import gads, seo_export

CFG = {"ga4_id": "G-ABC123", "ads_conversion_id": "AW-999888", "ads_conversion_label": "aB_cDeF"}


def test_has_gads():
    assert gads.has_gads(CFG)
    assert not gads.has_gads({})
    assert not gads.has_gads(None)
    assert gads.has_gads({"ga4_id": "G-X"})


def test_gtag_head_loads_both_ids():
    h = gads.gtag_head(CFG)
    assert "googletagmanager.com/gtag/js?id=G-ABC123" in h
    assert "gtag('config','G-ABC123')" in h
    assert "gtag('config','AW-999888')" in h
    assert gads.gtag_head({}) == ""


def test_tracking_js_has_conversion_and_capture():
    js = gads.tracking_js(CFG)
    assert "AW-999888/aB_cDeF" in js            # 전환 send_to
    assert "gclid" in js and "utm_source" in js  # 캡처 키
    assert "sessionStorage" in js and "conversion" in js and "select_content" in js
    assert gads.tracking_js({}) == ""


def test_report():
    r = gads.gads_report(CFG)
    assert r["enabled"] and r["ga4"] and r["google_ads_conversion"]
    assert r["conversion_label"] and r["remarketing"] and r["utm_gclid_capture"]
    assert "conversion" in r["events"]
    assert gads.gads_report({})["enabled"] is False


def test_export_injects_gtag_when_config_present():
    data = {
        "slug": "gads-shop", "title": "광고샵", "kind": "google_ads", "builder_name": "구글광고 전용 랜딩",
        "status": "active", "site_config": CFG, "owner_info": {}, "owner_ref": None,
        "affiliate_applied": True, "product_count": 1,
        "products": [{"id": 5, "title": "상품", "thumbnail_url": None,
                      "url": "https://x.com/p?subId=A", "network": "n", "price_krw": 10000,
                      "price_amount": None, "currency": "KRW", "segment": None, "brand": None, "category": "c"}],
    }
    h = seo_export.build_site_html(data, base_url="https://e.com", slug="gads-shop")
    assert "gtag/js?id=G-ABC123" in h                       # 헤드 주입
    assert "AW-999888/aB_cDeF" in h                          # 전환 추적
    pp = seo_export.build_product_html(data["products"][0], data, base_url="https://e.com",
                                       slug="gads-shop", related=[])
    assert "data-buy" in pp and 'data-id="5"' in pp          # 전환 클릭 대상
    assert "gtag/js?id=G-ABC123" in pp
    rep = seo_export.seo_report(data)
    assert rep["google_ads"]["enabled"] and rep["google_ads"]["conversion_label"]


def test_adsense_helpers():
    cfg = {"adsense_client": "ca-pub-1234567890", "adsense_slot": "9988776655"}
    assert gads.has_adsense(cfg) and not gads.has_adsense({})
    ld = gads.adsense_loader(cfg)
    assert "adsbygoogle.js?client=ca-pub-1234567890" in ld
    unit = gads.adsense_unit(cfg)
    assert 'class="adsbygoogle"' in unit and 'data-ad-client="ca-pub-1234567890"' in unit
    assert 'data-ad-slot="9988776655"' in unit and "adsbygoogle=window.adsbygoogle" in unit
    assert gads.adsense_loader({}) == "" and gads.adsense_unit({}) == ""


def test_adsense_report_positions():
    r = gads.gads_report({"adsense_client": "ca-pub-1"})
    assert r["adsense"] and r["adsense_positions"] == ["좌측", "우측", "중앙", "하단"]
    assert gads.gads_report({})["adsense"] is False


def test_export_injects_adsense():
    data = {"slug": "ad-shop", "title": "광고샵", "kind": "google_ads", "builder_name": "b",
            "status": "active", "site_config": {"adsense_client": "ca-pub-77"},
            "owner_info": {}, "owner_ref": None, "affiliate_applied": True, "product_count": 1,
            "products": [{"id": 1, "title": "p", "thumbnail_url": None, "url": "https://x/p",
                          "network": "n", "price_krw": 1000, "price_amount": None, "currency": "KRW",
                          "segment": None, "brand": None, "category": "c"}]}
    h = seo_export.build_site_html(data, base_url="https://e.com", slug="ad-shop")
    assert "adsbygoogle.js?client=ca-pub-77" in h        # 로더
    assert h.count('class="adsbygoogle"') >= 2           # 중앙 + 하단
    assert seo_export.seo_report(data)["google_ads"]["adsense"] is True


def test_export_no_gtag_when_absent():
    data = {"slug": "s", "title": "t", "kind": "shopping", "builder_name": "b", "status": "active",
            "site_config": {}, "owner_info": {}, "owner_ref": None, "affiliate_applied": False,
            "product_count": 0, "products": []}
    h = seo_export.build_site_html(data, base_url="https://e.com", slug="s")
    assert "gtag/js" not in h
    assert seo_export.seo_report(data)["google_ads"]["enabled"] is False
