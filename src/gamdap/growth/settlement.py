"""위탁 정산 엔진 — 귀속된 수수료를 파트너 체인에 배분하고 지급액을 확정한다.

핵심 불변식(테스트로 강제)
  Σ(파트너 몫) + Σ(상위 오버라이드) + 하우스 몫 = 귀속 수수료 총액
  — 1원도 생성되거나 증발하지 않는다. 반올림 잔차는 하우스가 흡수한다.

왜 Decimal 인가: float 는 0.1+0.2≠0.3 이다. 정산은 감사 대상이므로 십진 고정소수로
계산하고, 최소단위(0.0001) 이하는 최대잔여법으로 분배해 합계를 정확히 맞춘다.

배분 순서
  1) 귀속 수수료(gross) 에서 파트너 자신의 몫 = gross × revenue_share
  2) 상위 체인에 오버라이드 = gross × override_rates[깊이]
     (자기 몫과 오버라이드의 합이 gross 를 넘지 않도록 사전 검증·비례 축소)
  3) 남은 전액이 하우스(플랫폼) 몫
  4) 파트너 지급액에서 holdback_rate 만큼 보류(반품 대비), holdback_days 후 해제
  5) min_payout_krw 미만이면 이월(carry-over)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

__all__ = [
    "QUANT", "Contract", "PartnerNode", "SplitLine", "SplitResult",
    "split_commission", "apply_holdback", "allocate_exact",
]

QUANT = Decimal("0.0001")   # NUMERIC(18,4) 최소단위
_ZERO = Decimal("0")


@dataclass(frozen=True)
class Contract:
    """적용 계약 조건(해석 완료된 상태)."""

    partner_id: int
    revenue_share: Decimal          # 0~1
    override_rates: tuple[Decimal, ...] = ()   # [1단계 상위, 2단계 상위, ...]
    holdback_rate: Decimal = _ZERO
    holdback_days: int = 30
    min_payout_krw: Decimal = Decimal("10000")


@dataclass(frozen=True)
class PartnerNode:
    """파트너 트리의 한 노드(정산 계산에 필요한 최소 정보)."""

    partner_id: int
    parent_id: int | None
    kind: str = "partner"


@dataclass(frozen=True)
class SplitLine:
    partner_id: int
    kind: str            # 'attribution'|'override'|'house'
    amount: Decimal
    source_partner_id: int | None = None
    level: int = 0       # 오버라이드 단계(1=직속 상위)


@dataclass
class SplitResult:
    gross: Decimal
    lines: list[SplitLine] = field(default_factory=list)

    def total(self) -> Decimal:
        return sum((ln.amount for ln in self.lines), _ZERO)

    def for_partner(self, partner_id: int) -> Decimal:
        return sum((ln.amount for ln in self.lines if ln.partner_id == partner_id), _ZERO)


def allocate_exact(amount: Decimal, ratios: Sequence[Decimal]) -> list[Decimal]:
    """금액을 비율대로 배분하되 합계가 정확히 amount 가 되도록(최대잔여법).

    단순 반올림은 합계가 어긋난다. 내림 배분 후 남은 최소단위를 소수부가 큰
    순서로 나눠주면 합계 불일치가 0 이 된다(Hamilton 방식).
    """
    if not ratios:
        return []
    rsum = sum(ratios, _ZERO)
    if rsum <= 0:
        return [_ZERO] * len(ratios)
    exact = [amount * (r / rsum) for r in ratios]
    floored = [e.quantize(QUANT, rounding=ROUND_DOWN) for e in exact]
    remainder = amount - sum(floored, _ZERO)
    if remainder > 0:
        steps = int((remainder / QUANT).to_integral_value(rounding=ROUND_HALF_UP))
        order = sorted(range(len(exact)), key=lambda i: exact[i] - floored[i], reverse=True)
        for k in range(steps):
            floored[order[k % len(order)]] += QUANT
    return floored


def _ancestors(node_id: int, nodes: dict[int, PartnerNode], max_depth: int) -> list[int]:
    """상위 체인을 최대 max_depth 까지. 순환은 방문집합으로 차단."""
    out: list[int] = []
    seen = {node_id}
    cur = nodes.get(node_id)
    while cur and cur.parent_id and len(out) < max_depth:
        if cur.parent_id in seen:
            break               # 데이터 오류로 인한 순환 방지
        out.append(cur.parent_id)
        seen.add(cur.parent_id)
        cur = nodes.get(cur.parent_id)
    return out


def split_commission(gross: Decimal, *, contract: Contract,
                     nodes: dict[int, PartnerNode], house_partner_id: int) -> SplitResult:
    """귀속 수수료 1건을 파트너·상위체인·하우스로 배분.

    비율 합이 1을 넘으면(계약 설정 오류) 비례 축소해 gross 를 넘지 않게 한다 —
    지급 불능 상태를 만들지 않기 위한 방어.
    """
    gross = gross.quantize(QUANT, rounding=ROUND_DOWN)
    result = SplitResult(gross=gross)
    if gross <= 0:
        return result

    chain = _ancestors(contract.partner_id, nodes, len(contract.override_rates))

    # 요구 비율 구성: [자기몫] + [단계별 오버라이드(상위가 실재하는 만큼만)]
    ratios: list[Decimal] = [max(_ZERO, contract.revenue_share)]
    targets: list[tuple[int, str, int]] = [(contract.partner_id, "attribution", 0)]
    for level, ancestor_id in enumerate(chain, start=1):
        rate = contract.override_rates[level - 1]
        if rate <= 0:
            continue
        ratios.append(rate)
        targets.append((ancestor_id, "override", level))

    demanded = sum(ratios, _ZERO)
    if demanded > 1:
        # 초과 요구 → 비례 축소(하우스 몫 0). 계약 오류를 지급불능으로 만들지 않는다.
        ratios = [r / demanded for r in ratios]
        demanded = Decimal("1")

    house_ratio = Decimal("1") - demanded
    ratios.append(house_ratio)
    targets.append((house_partner_id, "house", 0))

    amounts = allocate_exact(gross, ratios)
    for (pid, kind, level), amt in zip(targets, amounts, strict=True):
        if amt == 0 and kind != "house":
            continue
        result.lines.append(SplitLine(
            partner_id=pid, kind=kind, amount=amt,
            source_partner_id=(contract.partner_id if kind == "override" else None),
            level=level,
        ))
    return result


def apply_holdback(payable: Decimal, contract: Contract) -> tuple[Decimal, Decimal]:
    """(즉시지급액, 보류액). 보류는 holdback_days 후 별도 라인으로 해제한다."""
    payable = payable.quantize(QUANT, rounding=ROUND_DOWN)
    if payable <= 0 or contract.holdback_rate <= 0:
        return payable, _ZERO
    hold = (payable * contract.holdback_rate).quantize(QUANT, rounding=ROUND_HALF_UP)
    hold = min(hold, payable)
    return payable - hold, hold


def resolve_contract(contracts: Sequence[dict], *, network_id: int | None = None,
                     category: str | None = None,
                     offer_type: str | None = None) -> dict | None:
    """적용 계약 선택 — 범위가 더 구체적이고 priority 가 낮은 계약이 이긴다.

    scope 예: {"network_ids":[1,2], "categories":["뷰티"], "offer_types":["physical_product"]}
    빈 scope 는 전체 적용(가장 일반적).
    """
    def _matches(scope: dict) -> tuple[bool, int]:
        """(적용가능?, 구체성 점수). 점수가 클수록 구체적."""
        specificity = 0
        nids = scope.get("network_ids")
        if nids:
            if network_id is None or network_id not in nids:
                return False, 0
            specificity += 4
        cats = scope.get("categories")
        if cats:
            if category is None or category not in cats:
                return False, 0
            specificity += 2
        otypes = scope.get("offer_types")
        if otypes:
            if offer_type is None or offer_type not in otypes:
                return False, 0
            specificity += 1
        return True, specificity

    best = None
    best_key = None
    for c in contracts:
        ok, spec = _matches(c.get("scope") or {})
        if not ok:
            continue
        key = (-spec, c.get("priority", 100), c.get("id", 0))
        if best_key is None or key < best_key:
            best, best_key = c, key
    return best
