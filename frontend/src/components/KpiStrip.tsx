import type { Summary } from "../types";

function fmt(n: number | null): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("ko-KR", { maximumFractionDigits: 0 });
}

export function KpiStrip({ summary }: { summary: Summary | null }) {
  const items = [
    { label: "총 활성 오퍼", value: summary ? fmt(summary.total_offers) : "—" },
    { label: "활성 네트워크", value: summary ? fmt(summary.active_networks) : "—" },
    { label: "평균 EPC (₩)", value: summary ? fmt(summary.avg_epc) : "—" },
    { label: "오늘의 기회", value: summary ? fmt(summary.opportunities) : "—" },
  ];
  return (
    <div className="kpi-strip">
      {items.map((it) => (
        <div className="kpi" key={it.label}>
          <div className="label">{it.label}</div>
          <div className="value">{it.value}</div>
        </div>
      ))}
    </div>
  );
}
