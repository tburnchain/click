import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Symbol } from "./Logo";
import type { Category, Facet, Filters, Network, Offer, Opportunity, Summary } from "./types";
import { KpiStrip } from "./components/KpiStrip";
import { FilterBar } from "./components/FilterBar";
import { FacetChips } from "./components/FacetChips";
import { OffersTable } from "./components/OffersTable";
import { OpportunityMap } from "./components/OpportunityMap";
import { OpportunitiesFeed } from "./components/OpportunitiesFeed";
import { CrawlManager } from "./components/CrawlManager";
import { DetailDrawer } from "./components/DetailDrawer";
import { TableSkeleton } from "./components/Skeleton";
import { SignupGuide } from "./components/SignupGuide";

type Tab = "offers" | "rankings" | "map" | "alerts" | "crawl";
const DEFAULT_FILTERS: Filters = { sort: "score", page: 1, size: 30 };

export function App() {
  const [tab, setTab] = useState<Tab>("offers");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [networks, setNetworks] = useState<Network[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [facets, setFacets] = useState<{ network?: Facet[]; segment?: Facet[] }>({});
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Offer | null>(null);
  const [guideOpen, setGuideOpen] = useState(false);

  const netName = useMemo(() => {
    const m = new Map(networks.map((n) => [n.code, n.display_name]));
    return (code: string) => m.get(code) ?? code;
  }, [networks]);

  useEffect(() => {
    api.summary().then(setSummary).catch(() => {});
    api.networks().then(setNetworks).catch(() => {});
    api.categories().then(setCategories).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true); setError(null);
    if (tab === "crawl") { setLoading(false); return; }
    if (tab === "alerts") {
      api.opportunities(80).then(setOpportunities).catch((e) => setError(String(e))).finally(() => setLoading(false));
      return;
    }
    const load = tab === "rankings"
      ? api.rankings(filters.category, 50).then((d) => ({ data: d, total: d.length, facets: {} }))
      : api.offers(filters).then((r) => ({ data: r.data, total: r.total, facets: r.facets ?? {} }));
    load.then((r) => { setOffers(r.data); setTotal(r.total); setFacets(r.facets); })
      .catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, [filters, tab]);

  const patch = (p: Partial<Filters>) => setFilters((f) => ({ ...f, ...p }));
  const onSort = (key: string) => patch({ sort: key, page: 1 });

  const showFilters = tab === "offers" || tab === "rankings";

  return (
    <div className="app">
      <div className="header">
        <Symbol size={30} />
        <h1>TBURN<span className="brand-dot">.CLICK</span></h1>
        <span className="sub">글로벌 제휴마케팅 데이터 대시보드 · 어떤 상품을 밀지 10초 안에 결정</span>
        <button className="guide-btn" onClick={() => setGuideOpen(true)} title="제휴 네트워크 가입 가이드">
          <span className="guide-btn-ico">📋</span> 가입 가이드
        </button>
      </div>

      <KpiStrip summary={summary} />

      <div className="tabs">
        {([["offers", "상품 탐색"], ["rankings", "수익성 랭킹"], ["map", "기회 지도"], ["alerts", "기회 알림"], ["crawl", "크롤링 관리"]] as [Tab, string][]).map(([t, label]) => (
          <div key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>{label}</div>
        ))}
      </div>

      {showFilters && <FilterBar filters={filters} networks={networks} categories={categories} onChange={patch} />}
      {tab === "offers" && (
        <FacetChips
          networkFacets={facets.network ?? []} segmentFacets={facets.segment ?? []}
          activeNetwork={filters.network} activeSegment={filters.segment} networkName={netName}
          onNetwork={(c) => patch({ network: c, page: 1 })}
          onSegment={(s) => patch({ segment: s, page: 1 })}
        />
      )}

      {error && <div className="error">불러오기 실패: {error}</div>}

      {tab === "crawl" && <CrawlManager />}
      {loading && showFilters && <TableSkeleton />}
      {!loading && !error && tab === "map" && <OpportunityMap offers={offers} />}
      {!loading && !error && tab === "alerts" && <OpportunitiesFeed items={opportunities} />}
      {!loading && !error && showFilters && (
        <>
          <OffersTable offers={offers} sort={filters.sort} onSort={onSort} onRowClick={setSelected} />
          {tab === "offers" && (
            <div className="pager">
              <span>총 {total.toLocaleString("ko-KR")}건</span>
              <span>
                <button disabled={filters.page <= 1} onClick={() => patch({ page: filters.page - 1 })}>이전</button>
                {" "}페이지 {filters.page}{" "}
                <button disabled={offers.length < filters.size} onClick={() => patch({ page: filters.page + 1 })}>다음</button>
              </span>
            </div>
          )}
        </>
      )}

      <DetailDrawer offer={selected} onClose={() => setSelected(null)} />
      {guideOpen && <SignupGuide onClose={() => setGuideOpen(false)} />}
    </div>
  );
}
