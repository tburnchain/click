import { useEffect, useState } from "react";
import type { Category, Filters, Network } from "../types";

interface Props {
  filters: Filters;
  networks: Network[];
  categories: Category[];
  onChange: (patch: Partial<Filters>) => void;
}

export function FilterBar({ filters, networks, categories, onChange }: Props) {
  const [q, setQ] = useState(filters.q ?? "");

  // 디바운스 실시간 검색 (Enter 불필요)
  useEffect(() => {
    const t = setTimeout(() => {
      if ((filters.q ?? "") !== q) onChange({ q: q || undefined, page: 1 });
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const active = filters.network || filters.category || filters.billing_type || filters.segment || filters.q;

  return (
    <div className="filterbar">
      <div className="search-wrap">
        <span className="search-ico">🔍</span>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="상품명 실시간 검색…" />
        {q && <button className="search-clear" onClick={() => setQ("")}>✕</button>}
      </div>
      <select value={filters.network ?? ""} onChange={(e) => onChange({ network: e.target.value || undefined, page: 1 })}>
        <option value="">전체 네트워크</option>
        {networks.map((n) => <option key={n.code} value={n.code}>{n.display_name}</option>)}
      </select>
      <select value={filters.category ?? ""} onChange={(e) => onChange({ category: e.target.value || undefined, page: 1 })}>
        <option value="">전체 카테고리</option>
        {categories.map((c) => <option key={c.slug} value={c.slug}>{c.name_ko ?? c.slug}</option>)}
      </select>
      <select value={filters.billing_type ?? ""} onChange={(e) => onChange({ billing_type: e.target.value || undefined, page: 1 })}>
        <option value="">전체 과금</option>
        <option value="CPS">CPS</option>
        <option value="CPC">CPC</option>
        <option value="CPA">CPA</option>
      </select>
      <select value={filters.sort} onChange={(e) => onChange({ sort: e.target.value, page: 1 })}>
        <option value="score">정렬: 수익성</option>
        <option value="relevance">정렬: 관련도</option>
        <option value="epc">정렬: EPC</option>
        <option value="commission">정렬: 수수료율</option>
        <option value="price">정렬: 가격</option>
        <option value="freshness">정렬: 신선도</option>
      </select>
      {active && (
        <button className="reset-btn" onClick={() => { setQ(""); onChange({ network: undefined, category: undefined, billing_type: undefined, segment: undefined, q: undefined, page: 1 }); }}>
          필터 초기화
        </button>
      )}
    </div>
  );
}
