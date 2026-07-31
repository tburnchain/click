import type { Offer } from "../types";

// 기회 지도(§18.8): x=경쟁(K), y=수익성 점수, 버블 크기=수요(D), 색=세그먼트.
// 좌상단(낮은 경쟁 · 높은 수익) = 금맥 구역.
const SEG_COLOR: Record<string, string> = {
  goldmine: "#16a34a", rising: "#2563eb", cashcow: "#d97706",
  saturated: "#ea580c", avoid: "#9ca3af",
};

const W = 640, H = 380, PAD = 44;

export function OpportunityMap({ offers }: { offers: Offer[] }) {
  const pts = offers.filter((o) => o.score.profitability != null);
  const x = (k: number) => PAD + k * (W - 2 * PAD);
  const y = (p: number) => H - PAD - (p / 100) * (H - 2 * PAD);

  return (
    <div className="map-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="기회 지도">
        {/* 축 */}
        <line x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke="var(--border)" />
        <line x1={PAD} y1={PAD} x2={PAD} y2={H - PAD} stroke="var(--border)" />
        {/* 금맥 구역(좌상단) 음영 */}
        <rect x={PAD} y={PAD} width={(W - 2 * PAD) * 0.4} height={(H - 2 * PAD) * 0.5}
              fill="rgba(22,163,74,.06)" />
        <text x={PAD + 8} y={PAD + 16} fontSize="11" fill="var(--gold)">← 금맥 구역 (저경쟁·고수익)</text>
        {/* 축 라벨 */}
        <text x={W / 2} y={H - 10} fontSize="11" fill="var(--muted)" textAnchor="middle">경쟁 지수 (K) →</text>
        <text x={14} y={H / 2} fontSize="11" fill="var(--muted)" textAnchor="middle"
              transform={`rotate(-90 14 ${H / 2})`}>수익성 점수 →</text>
        {/* 점 */}
        {pts.map((o) => {
          const k = o.score.competition ?? 0.5;
          const p = o.score.profitability ?? 0;
          const d = o.score.demand ?? 0.5;
          const seg = o.score.segment ?? "";
          return (
            <circle key={o.id} cx={x(k)} cy={y(p)} r={4 + d * 8}
                    fill={SEG_COLOR[seg] ?? "#94a3b8"} fillOpacity={0.65}
                    stroke={SEG_COLOR[seg] ?? "#94a3b8"}>
              <title>{`${o.title}\n수익성 ${p.toFixed(1)} · 경쟁 ${k.toFixed(2)} · 수요 ${d.toFixed(2)}`}</title>
            </circle>
          );
        })}
      </svg>
      <div className="map-legend">
        {Object.entries(SEG_COLOR).map(([seg, c]) => (
          <span key={seg}><span style={{ color: c }}>●</span> {seg}</span>
        ))}
        <span>· 버블 크기 = 수요</span>
      </div>
    </div>
  );
}
