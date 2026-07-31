"""위탁 확장 엔진의 수학적 정확성 검증.

가장 중요한 것은 **불변식**이다: 정산에서 1원도 생성·증발하면 안 된다.
어트리뷰션 가중치 합은 정확히 1이어야 하고, 배분 금액 합은 원금과 같아야 한다.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from gamdap.growth import attribution as at
from gamdap.growth import fraud as fr
from gamdap.growth import scoring as sc
from gamdap.growth import settlement as st

BASE = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def _touches(n: int, *, days_apart: float = 1.0) -> list[at.Touch]:
    return [at.Touch(touchpoint_id=i + 1, partner_id=100 + i,
                     occurred_at=BASE + timedelta(days=i * days_apart),
                     channel=f"ch{i % 3}") for i in range(n)]


# ── 어트리뷰션: 가중치 합 = 1 ──
def test_all_models_sum_to_one():
    touches = _touches(5)
    for model in ("last_click", "time_decay", "position"):
        w = at.attribute(touches, model=model, conversion_at=touches[-1].occurred_at)
        assert abs(sum(w) - 1.0) < 1e-12, f"{model} 가중치 합이 1이 아님: {sum(w)}"
        assert all(x >= 0 for x in w)


def test_last_click_gives_all_to_final():
    w = at.attribute(_touches(4), model="last_click")
    assert w[-1] == 1.0 and sum(w[:-1]) == 0.0


def test_time_decay_is_monotonic():
    """전환에 가까운 터치일수록 가중치가 크다."""
    w = at.attribute(_touches(5), model="time_decay")
    assert all(w[i] <= w[i + 1] for i in range(len(w) - 1)), w


def test_time_decay_half_life():
    """반감기만큼 떨어진 터치는 정확히 절반 가중(정규화 전 비율)."""
    t = [at.Touch(1, 10, BASE), at.Touch(2, 11, BASE + timedelta(days=7))]
    w = at.time_decay(t, half_life_days=7.0)
    assert abs(w[0] / w[1] - 0.5) < 1e-9


def test_position_based_u_shape():
    w = at.attribute(_touches(5), model="position")
    assert w[0] > w[2] and w[-1] > w[2]        # 첫·마지막이 중간보다 큼
    assert abs(w[0] - w[-1]) < 1e-9            # 대칭


def test_lookback_excludes_old_touches():
    """쿠키 윈도 밖 터치는 기여 0."""
    old = at.Touch(1, 10, BASE)
    new = at.Touch(2, 11, BASE + timedelta(days=40))
    w = at.attribute([old, new], model="time_decay", lookback_days=30,
                     conversion_at=BASE + timedelta(days=40))
    assert w[0] == 0.0 and abs(w[1] - 1.0) < 1e-12


# ── 마르코프 제거효과 ──
def test_markov_removal_detects_essential_channel():
    """모든 전환 경로에 등장하는 채널이 최대 기여를 받는다."""
    paths = [(["seo", "social"], True), (["seo"], True), (["seo", "email"], True),
             (["social"], False), (["email"], False)]
    eff = at.markov_removal(paths, ["seo", "social", "email"])
    assert abs(sum(eff.values()) - 1.0) < 1e-9
    assert eff["seo"] == max(eff.values())


# ── Shapley: 효율성·대칭성 ──
def test_shapley_sums_to_one_and_symmetric():
    paths = [(["a", "b"], True), (["a"], True), (["b"], True), (["a", "b"], False)]
    val = at.shapley(paths, ["a", "b"])
    assert abs(sum(val.values()) - 1.0) < 1e-9
    assert abs(val["a"] - val["b"]) < 1e-6      # 대칭 채널은 동일 배분


# ── 금액 배분 불변식 ──
def test_credit_amounts_exact_sum():
    """3등분처럼 나누어떨어지지 않아도 합계가 원금과 정확히 같다."""
    amount = Decimal("10000.0000")
    weights = [1 / 3, 1 / 3, 1 / 3]
    parts = at.credit_amounts(weights, amount)
    assert sum(parts) == amount, f"{sum(parts)} != {amount}"


def test_allocate_exact_no_leak():
    for total in ("1.0001", "999.9999", "12345.6789"):
        amount = Decimal(total)
        parts = st.allocate_exact(amount, [Decimal("1"), Decimal("1"), Decimal("1")])
        assert sum(parts) == amount


# ── 스코어링: 소표본 왜곡 제거 ──
def test_wilson_penalizes_small_samples():
    """1/3(33%) 보다 100/300(33%) 이 더 높게 평가돼야 한다."""
    small = sc.wilson_lower_bound(1, 3)
    large = sc.wilson_lower_bound(100, 300)
    assert large > small


def test_wilson_bounds():
    assert sc.wilson_lower_bound(0, 0) == 0.0
    assert 0.0 <= sc.wilson_lower_bound(5, 10) <= 0.5


def test_empirical_bayes_shrinks_toward_prior():
    """표본이 적을수록 사전평균 쪽으로 강하게 수축하고, 커질수록 관측값에 접근한다."""
    obs = [(10, 100), (12, 100), (9, 100), (11, 100)]     # 모집단 CVR ≈ 10%
    alpha, beta = sc.empirical_bayes_prior(obs)
    prior_mean = alpha / (alpha + beta)
    assert 0.05 < prior_mean < 0.15

    # 관측비율 50%를 유지한 채 표본만 키우면, 추정치는 단조증가하며 50%로 접근한다.
    seq = [sc.shrink_rate(n // 2, n, alpha, beta) for n in (2, 20, 200, 2000, 200_000)]
    assert all(seq[i] < seq[i + 1] for i in range(len(seq) - 1)), seq
    assert seq[0] < 0.2                    # 소표본은 사전평균 근처
    assert abs(seq[-1] - 0.5) < 0.01       # 대표본은 관측값으로 수렴


def test_empirical_bayes_prior_strength_tracks_population_spread():
    """모집단이 이질적일수록 사전분포가 약해져(=수축이 덜해) 개별 실적을 빨리 인정한다."""
    homogeneous = [(10, 100), (11, 100), (9, 100), (10, 100)]
    heterogeneous = [(2, 100), (30, 100), (5, 100), (45, 100)]
    a_h, b_h = sc.empirical_bayes_prior(homogeneous)
    a_t, b_t = sc.empirical_bayes_prior(heterogeneous)
    assert (a_h + b_h) > (a_t + b_t)       # 균질 모집단 = 강한 사전분포
    # 같은 관측(50/100)이라도 이질 모집단에서 더 높게 평가된다
    assert sc.shrink_rate(50, 100, a_t, b_t) > sc.shrink_rate(50, 100, a_h, b_h)


def test_tier_hysteresis_prevents_flapping():
    """경계 근처에서 등급이 진동하지 않는다."""
    assert sc.assign_tier(76.0) == "platinum"
    # platinum 유지: 강등임계(70) 이상이면 74점이어도 유지
    assert sc.assign_tier(72.0, current="platinum") == "platinum"
    # 강등임계 아래로 떨어지면 하락
    assert sc.assign_tier(69.0, current="platinum") == "gold"
    # 승급은 즉시
    assert sc.assign_tier(91.0, current="gold") == "diamond"


def test_geometric_mean_punishes_weak_axis():
    """한 축이 매우 낮으면 종합이 산술평균보다 크게 낮아진다."""
    balanced = sc.weighted_geometric_mean([(70, 1), (70, 1), (70, 1)])
    skewed = sc.weighted_geometric_mean([(100, 1), (100, 1), (10, 1)])
    assert balanced > skewed


# ── 정산: 합계 불변식 ──
def _nodes():
    return {
        1: st.PartnerNode(1, None, "house"),
        2: st.PartnerNode(2, 1, "agency"),
        3: st.PartnerNode(3, 2, "partner"),
    }


def test_split_conserves_total():
    """파트너 + 오버라이드 + 하우스 = 귀속 수수료 (1원도 안 샌다)."""
    gross = Decimal("100000.0000")
    contract = st.Contract(partner_id=3, revenue_share=Decimal("0.70"),
                           override_rates=(Decimal("0.05"), Decimal("0.02")))
    result = st.split_commission(gross, contract=contract, nodes=_nodes(), house_partner_id=1)
    assert result.total() == gross
    assert result.for_partner(3) == Decimal("70000.0000")
    assert result.for_partner(2) == Decimal("5000.0000")     # 1단계 상위
    assert result.for_partner(1) == Decimal("25000.0000")    # 하우스(2% 오버라이드는 상위 없음)


def test_split_conserves_with_odd_amounts():
    """나누어떨어지지 않는 금액에서도 합계가 정확하다."""
    for raw in ("33333.3333", "1.0001", "7.7777", "999999.9999"):
        gross = Decimal(raw)
        contract = st.Contract(partner_id=3, revenue_share=Decimal("0.333333"),
                               override_rates=(Decimal("0.111111"),))
        result = st.split_commission(gross, contract=contract, nodes=_nodes(), house_partner_id=1)
        assert result.total() == gross, f"{raw}: {result.total()}"


def test_split_clamps_overcommitted_contract():
    """비율 합이 1을 넘는 잘못된 계약도 지급불능을 만들지 않는다."""
    gross = Decimal("10000.0000")
    contract = st.Contract(partner_id=3, revenue_share=Decimal("0.90"),
                           override_rates=(Decimal("0.30"), Decimal("0.20")))
    result = st.split_commission(gross, contract=contract, nodes=_nodes(), house_partner_id=1)
    assert result.total() == gross
    assert result.for_partner(3) <= gross


def test_holdback_split():
    contract = st.Contract(partner_id=3, revenue_share=Decimal("0.7"),
                           holdback_rate=Decimal("0.10"))
    pay, hold = st.apply_holdback(Decimal("10000.0000"), contract)
    assert pay + hold == Decimal("10000.0000")
    assert hold == Decimal("1000.0000")


def test_contract_resolution_prefers_specific():
    contracts = [
        {"id": 1, "scope": {}, "priority": 100},
        {"id": 2, "scope": {"network_ids": [7]}, "priority": 100},
    ]
    picked = st.resolve_contract(contracts, network_id=7)
    assert picked["id"] == 2          # 구체적 범위가 이긴다
    picked2 = st.resolve_contract(contracts, network_id=99)
    assert picked2["id"] == 1         # 범위 밖이면 일반 계약


def test_cycle_in_partner_tree_does_not_hang():
    """데이터 오류로 순환이 생겨도 무한루프에 빠지지 않는다."""
    cyclic = {1: st.PartnerNode(1, 2, "partner"), 2: st.PartnerNode(2, 1, "partner")}
    contract = st.Contract(partner_id=1, revenue_share=Decimal("0.5"),
                           override_rates=(Decimal("0.1"), Decimal("0.1"), Decimal("0.1")))
    result = st.split_commission(Decimal("1000.0000"), contract=contract,
                                 nodes=cyclic, house_partner_id=1)
    assert result.total() == Decimal("1000.0000")


# ── 부정 탐지 ──
def test_entropy_flags_uniform_and_concentrated():
    uniform = list(range(24)) * 5                    # 완전 균일 → 봇 의심
    assert fr.time_entropy(uniform) > 0.99
    concentrated = [3] * 100                          # 한 시각 집중
    assert fr.time_entropy(concentrated) < 0.05
    natural = [9, 10, 11, 12, 13, 14, 20, 21, 22] * 5
    assert 0.3 < fr.time_entropy(natural) < 0.95


def test_poisson_tail_detects_burst():
    """평소 시간당 2건인데 갑자기 60건이면 극히 희귀하다."""
    assert fr.poisson_upper_tail(60, 2.0) < 1e-20
    assert fr.poisson_upper_tail(3, 2.0) > 0.1       # 정상 범위


def test_herfindahl_concentration():
    assert fr.herfindahl(["a"] * 10) == 1.0
    assert abs(fr.herfindahl([str(i) for i in range(10)]) - 0.1) < 1e-9


def test_robust_z_ignores_outlier_contamination():
    """평균 기반이면 이상치에 오염되지만 MAD 기반은 견딘다."""
    pop = [0.01, 0.011, 0.009, 0.012, 0.01, 5.0]     # 5.0 은 오염값
    z = fr.robust_zscore(0.01, pop)
    assert abs(z) < 2.0                               # 정상값은 정상으로 판정


def test_detect_concentration_signal():
    sig = fr.detect_concentration(["same"] * 50)
    assert sig is not None and sig.severity == "critical"
    assert fr.detect_concentration([str(i) for i in range(50)]) is None


def test_risk_score_accumulates_but_bounded():
    signals = [fr.Signal("a", "warn", 0.5, {}), fr.Signal("b", "warn", 0.5, {})]
    score = fr.risk_score(signals)
    assert 0 < score < 100
    assert fr.risk_score([]) == 0.0
