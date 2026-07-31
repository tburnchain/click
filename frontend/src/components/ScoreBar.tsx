// 수익성 점수(0~100)를 빨강→노랑→초록 컬러 바로 시각화(§10.3)
export function ScoreBar({ value }: { value: number | null }) {
  if (value === null || value === undefined) return <span className="muted">—</span>;
  const v = Math.max(0, Math.min(100, value));
  // hue 0(red) → 120(green)
  const hue = (v / 100) * 120;
  return (
    <div className="scorebar" title={`수익성 ${v.toFixed(1)}`}>
      <span style={{ width: `${v}%`, background: `hsl(${hue} 70% 45%)` }} />
      <em>{v.toFixed(0)}</em>
    </div>
  );
}
