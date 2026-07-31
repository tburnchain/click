// 기회 세그먼트 뱃지(§18.6)
const LABEL: Record<string, string> = {
  goldmine: "🟢 금맥",
  rising: "🔵 신흥",
  cashcow: "🟡 안정",
  saturated: "🟠 포화",
  avoid: "🔴 회피",
};

export function SegmentBadge({ segment }: { segment: string | null }) {
  if (!segment) return <span className="seg-none">미분류</span>;
  const label = LABEL[segment] ?? segment;
  return <span className={`seg seg-${segment}`}>{label}</span>;
}
