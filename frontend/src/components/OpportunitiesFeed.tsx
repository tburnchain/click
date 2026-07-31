import type { Opportunity } from "../types";

const KIND_LABEL: Record<string, string> = {
  price_drop: "💸 가격 급락",
  price_up: "📈 가격 상승",
  commission_up: "🔥 수수료 인상",
  commission_down: "📉 수수료 인하",
  stock_low: "⚠️ 재고 임박",
  stock_out: "⛔ 재고 소진",
  back_in_stock: "✅ 재입고",
};

const SEV_COLOR: Record<string, string> = {
  high: "#dc2626",
  warn: "#d97706",
  info: "#6b7280",
};

function detailText(d: Record<string, unknown>): string {
  const parts: string[] = [];
  if ("from" in d && "to" in d) parts.push(`${d.from} → ${d.to}`);
  if ("pct" in d && typeof d.pct === "number") parts.push(`${(d.pct * 100).toFixed(1)}%`);
  if ("delta" in d && typeof d.delta === "number") parts.push(`Δ${(d.delta * 100).toFixed(1)}%p`);
  return parts.join(" · ");
}

export function OpportunitiesFeed({ items }: { items: Opportunity[] }) {
  if (items.length === 0)
    return <div className="empty">감지된 변동이 없습니다. 수집·감지 잡 실행 후 표시됩니다.</div>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>변동</th>
            <th>상품</th>
            <th>네트워크</th>
            <th>상세</th>
            <th>감지 시각</th>
          </tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.id}>
              <td style={{ color: SEV_COLOR[e.severity], fontWeight: 600 }}>
                {KIND_LABEL[e.kind] ?? e.kind}
              </td>
              <td className="title-cell">{e.title}</td>
              <td>{e.network_name}</td>
              <td className="muted">{detailText(e.detail)}</td>
              <td className="muted">{new Date(e.detected_at).toLocaleString("ko-KR")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
