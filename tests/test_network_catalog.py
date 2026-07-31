"""제휴 네트워크 카탈로그 — 무결성 + 자격증명 미포함 보장."""

import json

from gamdap.members import network_catalog

REQUIRED = {"slug", "name", "emoji", "region", "category", "integration",
            "status", "homepage", "signup_url", "tracking_param", "commission",
            "approval", "payout", "cautions"}


def test_catalog_has_23_networks():
    assert len(network_catalog.AFFILIATE_NETWORKS) == 23


def test_slugs_unique_and_required_fields():
    slugs = [n["slug"] for n in network_catalog.AFFILIATE_NETWORKS]
    assert len(slugs) == len(set(slugs)), "중복 slug"
    for n in network_catalog.AFFILIATE_NETWORKS:
        assert set(n) >= REQUIRED, f"필드 누락: {n['slug']}"
        assert n["integration"] in ("api", "manual")
        assert n["status"] in ("active", "pending")
        assert n["cautions"], f"cautions 비어있음: {n['slug']}"


def test_no_credentials_leaked():
    """로그인 아이디/비밀번호/개인정보가 카탈로그에 절대 포함되지 않아야 한다."""
    blob = json.dumps(network_catalog.AFFILIATE_NETWORKS, ensure_ascii=False).lower()
    forbidden = [
        "cmj583756", "nightsudal583756", "start!@3", "!@cmj", "!@night",
        "cymonmj", "nightsudal@hanmail", "@gmail.com", "@hanmail.net", "01088270625",
    ]
    for token in forbidden:
        assert token.lower() not in blob, f"자격증명/개인정보 유출 의심: {token}"


def test_api_connectors_marked():
    api = network_catalog.list_networks(integration="api")
    codes = {n["connector_code"] for n in api}
    assert {"coupang_partners", "amazon_assoc", "clickbank", "cj_affiliate", "impact"} <= codes


def test_public_referral_links_present():
    refs = {n["slug"]: n.get("referral_url") for n in network_catalog.AFFILIATE_NETWORKS}
    assert refs["admitad"] and "ref=" in refs["admitad"]
    assert refs["adlix"] and refs["adlix"].startswith("http")


def test_summary_counts():
    s = network_catalog.catalog_summary()
    assert s["total"] == 23
    assert s["api"] == 5
    assert s["pending"] >= 4
