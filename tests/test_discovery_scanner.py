"""발견 스캐너 평가 로직 테스트(§16, M9)."""

from gamdap.discovery.scanner import CandidateProbe, evaluate_candidate


def _probe(**kw) -> CandidateProbe:
    base = dict(name="TestNet", has_official_api=True, has_product_feed=False,
                terms_scrape_allowed=False, category_fit=0.8,
                commission_viability=0.7, country_priority=0.6)
    base.update(kw)
    return CandidateProbe(**base)


def test_evaluate_official_api_positive():
    assert evaluate_candidate(_probe(), source_trust=0.95) > 0


def test_evaluate_no_origin_zero():
    # 공식 API·피드 모두 없음 → 곱셈 게이트 0
    assert evaluate_candidate(
        _probe(has_official_api=False, has_product_feed=False), source_trust=0.9) == 0.0


def test_evaluate_terms_violation_zero():
    # 스크래핑 불가 + 공식 API 없음(피드만) → 약관 게이트 0
    assert evaluate_candidate(
        _probe(has_official_api=False, has_product_feed=True, terms_scrape_allowed=False),
        source_trust=0.9) == 0.0


def test_evaluate_feed_with_scrape_ok():
    assert evaluate_candidate(
        _probe(has_official_api=False, has_product_feed=True, terms_scrape_allowed=True),
        source_trust=0.9) > 0


def test_higher_source_trust_higher_score():
    hi = evaluate_candidate(_probe(), source_trust=0.95)
    lo = evaluate_candidate(_probe(), source_trust=0.4)
    assert hi > lo
