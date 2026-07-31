// 가격 이력 미니 라인차트 (외부 라이브러리 없이 SVG)
export function Sparkline({ values, width = 260, height = 60 }: {
  values: number[]; width?: number; height?: number;
}) {
  const pts = values.filter((v) => v != null && !isNaN(v));
  if (pts.length < 2) return <div className="muted" style={{ fontSize: 12 }}>이력 데이터 부족</div>;
  const min = Math.min(...pts), max = Math.max(...pts);
  const range = max - min || 1;
  const pad = 4;
  const x = (i: number) => pad + (i / (pts.length - 1)) * (width - 2 * pad);
  const y = (v: number) => height - pad - ((v - min) / range) * (height - 2 * pad);
  const d = pts.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${d} L${x(pts.length - 1)},${height - pad} L${x(0)},${height - pad} Z`;
  const last = pts[pts.length - 1], first = pts[0];
  const up = last >= first;
  const c = up ? "#dc2626" : "#16a34a"; // 가격 상승=빨강(홍보 매력↓), 하락=초록
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img">
      <path d={area} fill={c} fillOpacity={0.08} />
      <path d={d} fill="none" stroke={c} strokeWidth={2} />
      <circle cx={x(pts.length - 1)} cy={y(last)} r={3} fill={c} />
    </svg>
  );
}
