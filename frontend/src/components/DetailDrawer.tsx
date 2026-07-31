import { useEffect, useState } from "react";
import { api } from "../api";
import type { HistoryPoint, Offer } from "../types";
import { Sparkline } from "./Sparkline";
import { SegmentBadge } from "./SegmentBadge";

const SEG_WHY: Record<string, string> = {
  goldmine: "고수익·고수요·저경쟁 → 지금 집중할 최우선 상품",
  rising: "저경쟁 신흥 구간 → 선점 진입 유리",
  cashcow: "검증된 고수익이나 경쟁 치열 → 차별화 필요",
  saturated: "경쟁 포화·마진 압축 → 관망 권장",
  avoid: "수익성 또는 수요 부족 → 제외 권장",
};

// 0~1 지표 막대
function MetricBar({ label, value, invert = false }: { label: string; value: number | null; invert?: boolean }) {
  const v = value == null ? 0 : Math.max(0, Math.min(1, value));
  const good = invert ? 1 - v : v;
  const hue = good * 120;
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <div className="metric-track"><span style={{ width: `${v * 100}%`, background: `hsl(${hue} 65% 45%)` }} /></div>
      <span className="metric-val">{value == null ? "—" : v.toFixed(2)}</span>
    </div>
  );
}

export function DetailDrawer({ offer, onClose }: { offer: Offer | null; onClose: () => void }) {
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [siblings, setSiblings] = useState<Offer[]>([]);

  useEffect(() => {
    if (!offer) return;
    setHistory([]); setSiblings([]);
    api.offerHistory(offer.id).then(setHistory).catch(() => {});
    if (offer.product_id != null) api.productOffers(offer.product_id).then(setSiblings).catch(() => {});
  }, [offer]);

  if (!offer) return null;
  const s = offer.score;
  const prices = history.map((h) => Number(h.price_amount)).filter((n) => !isNaN(n));

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer">
        <div className="drawer-head">
          <div>
            <div className="muted" style={{ fontSize: 12 }}>{offer.network_name} · {offer.billing_type}</div>
            <h2>{offer.title}</h2>
          </div>
          <button className="drawer-x" onClick={onClose}>✕</button>
        </div>

        <div className="drawer-body">
          {/* 세그먼트 + 점수 */}
          <div className="drawer-row">
            <SegmentBadge segment={s.segment} />
            <span className="big-score" title="수익성 점수">
              {s.profitability != null ? s.profitability.toFixed(1) : "—"}
              <small>/100</small>
            </span>
          </div>
          <p className="seg-why">{s.segment ? SEG_WHY[s.segment] : "미분류 상품"}</p>

          {/* 점수 분해 (초지능 수학 투명화) */}
          <h3>점수 분해</h3>
          <div className="metrics">
            <MetricBar label="수요 (D)" value={s.demand} />
            <MetricBar label="경쟁 (K) · 낮을수록 좋음" value={s.competition} invert />
            <div className="metric">
              <span className="metric-label">건당수익 (EPC)</span>
              <span className="metric-val" style={{ marginLeft: "auto" }}>
                {s.epc != null ? "₩" + Math.round(s.epc).toLocaleString() : "—"}
              </span>
            </div>
          </div>
          <p className="formula">점수 = 100 · norm(EPC)<sup>.5</sup> · 수요<sup>.3</sup> · (1−경쟁)<sup>.2</sup> · 신선도</p>

          {/* 가격 이력 */}
          <h3>가격 추이 (최근 {history.length}포인트)</h3>
          <Sparkline values={prices} />

          {/* 네트워크 비교 */}
          <h3>같은 상품 · 네트워크 비교</h3>
          {siblings.length <= 1 ? (
            <p className="muted" style={{ fontSize: 13 }}>다른 네트워크 오퍼 없음 (단일 소스)</p>
          ) : (
            <table className="mini-table">
              <thead><tr><th>네트워크</th><th className="num">수수료</th><th className="num">점수</th></tr></thead>
              <tbody>
                {siblings.map((o) => (
                  <tr key={o.id} className={o.id === offer.id ? "row-self" : ""}>
                    <td>{o.network_name}</td>
                    <td className="num">{o.commission_rate ? (Number(o.commission_rate) * 100).toFixed(1) + "%" : "—"}</td>
                    <td className="num">{o.score.profitability?.toFixed(0) ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {offer.landing_url && (
            <a className="drawer-cta" href={offer.landing_url} target="_blank" rel="noreferrer">
              상품 페이지 열기 ↗
            </a>
          )}
        </div>
      </aside>
    </>
  );
}
