import type { Offer } from "../types";
import { ScoreBar } from "./ScoreBar";
import { SegmentBadge } from "./SegmentBadge";

const SEG_COLOR: Record<string, string> = {
  goldmine: "#16a34a", rising: "#2563eb", cashcow: "#d97706",
  saturated: "#ea580c", avoid: "#9ca3af",
};

function relTime(iso: string): { label: string; stale: boolean } {
  const then = new Date(iso).getTime();
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 60) return { label: `${Math.max(0, mins)}분 전`, stale: false };
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return { label: `${hrs}시간 전`, stale: hrs >= 12 };
  return { label: `${Math.floor(hrs / 24)}일 전`, stale: true };
}

function money(krw: string | null, currency: string | null, amount: string | null): string {
  if (krw) return "₩" + Number(krw).toLocaleString("ko-KR", { maximumFractionDigits: 0 });
  if (amount) return `${currency ?? ""} ${Number(amount).toLocaleString()}`;
  return "—";
}

function commission(o: Offer): string {
  if (o.commission_kind === "percent" && o.commission_rate)
    return (Number(o.commission_rate) * 100).toFixed(1) + "%";
  if (o.commission_kind === "fixed" && o.commission_fixed)
    return money(null, o.commission_fixed.currency, o.commission_fixed.amount) + "/건";
  return "—";
}

interface Props {
  offers: Offer[];
  sort: string;
  onSort: (key: string) => void;
  onRowClick: (o: Offer) => void;
}

const COLS: { key?: string; label: string; num?: boolean }[] = [
  { label: "" },
  { label: "상품" },
  { label: "네트워크" },
  { label: "과금" },
  { key: "price", label: "가격", num: true },
  { key: "commission", label: "수수료", num: true },
  { key: "epc", label: "건당수익(₩)", num: true },
  { key: "score", label: "수익성" },
  { label: "세그먼트" },
  { key: "freshness", label: "신선도" },
  { label: "출처" },
];

export function OffersTable({ offers, sort, onSort, onRowClick }: Props) {
  if (offers.length === 0)
    return <div className="empty">조건에 맞는 오퍼가 없습니다. 필터를 완화해 보세요.</div>;
  return (
    <div className="table-wrap">
      <table className="offers-table">
        <thead>
          <tr>
            {COLS.map((c, i) => (
              <th key={i} className={`${c.num ? "num" : ""} ${c.key ? "sortable" : ""}`}
                  onClick={c.key ? () => onSort(c.key!) : undefined}>
                {c.label}{c.key && sort === c.key && <span className="sort-caret"> ▾</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {offers.map((o) => {
            const rt = relTime(o.fetched_at);
            const official = o.data_source === "official_api";
            const accent = SEG_COLOR[o.score.segment ?? ""] ?? "transparent";
            return (
              <tr key={o.id} className="row-click" onClick={() => onRowClick(o)}
                  style={{ borderLeft: `3px solid ${accent}` }}>
                <td>{o.thumbnail_url ? <img className="thumb" src={o.thumbnail_url} alt="" /> : <div className="thumb" />}</td>
                <td className="title-cell">{o.title}</td>
                <td>{o.network_name}</td>
                <td className="muted">{o.billing_type ?? "—"}</td>
                <td className="num">{money(o.price.krw, o.price.currency, o.price.amount)}</td>
                <td className="num">{commission(o)}</td>
                <td className="num">{o.score.epc != null ? "₩" + o.score.epc.toLocaleString("ko-KR", { maximumFractionDigits: 0 }) : "—"}</td>
                <td><ScoreBar value={o.score.profitability} /></td>
                <td><SegmentBadge segment={o.score.segment} /></td>
                <td className={rt.stale ? "" : ""} style={rt.stale ? { color: "#d97706" } : { color: "var(--muted)" }}>{rt.label}</td>
                <td><span className={`badge-src ${official ? "src-official" : "src-est"}`}>{official ? "공식" : "추정"}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
