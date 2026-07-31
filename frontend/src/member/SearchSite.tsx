import { useMemo, useState } from "react";
import { thumb, onImgError } from "../img";
import type { PublicSiteData } from "../auth";

function priceOf(p: { price_krw: number | null; price_amount: number | null; currency: string | null }): string {
  if (p.price_krw) return "₩" + Math.round(p.price_krw).toLocaleString("ko-KR");
  if (p.price_amount) return `${p.currency ?? ""} ${p.price_amount.toLocaleString()}`;
  return "";
}

const SEG: Record<string, string> = { goldmine: "🟢 강력추천", rising: "🔵 인기상승", cashcow: "🟡 스테디셀러", saturated: "🟠 인기", avoid: "" };

export function SearchSite({ slug, data }: { slug: string; data: PublicSiteData }) {
  const [q, setQ] = useState("");
  const owner = data.owner_info || {};
  const cats = useMemo(() => [...new Set(data.products.map((p) => p.category).filter(Boolean))].slice(0, 8) as string[], [data]);
  const brands = useMemo(() => [...new Set(data.products.map((p) => p.brand).filter(Boolean))].slice(0, 10) as string[], [data]);

  const ql = q.trim().toLowerCase();
  const results = data.products.filter((p) =>
    !ql || `${p.title} ${p.brand ?? ""} ${p.category ?? ""}`.toLowerCase().includes(ql));

  return (
    <div className="srch">
      <div className="srch-top">
        <div className="srch-logo">{data.title}</div>
        <div className="srch-box">
          <input autoFocus placeholder="무엇을 찾으세요? 상품·브랜드·카테고리 검색"
                 value={q} onChange={(e) => setQ(e.target.value)} />
          <button>🔍 검색</button>
        </div>
        <div className="srch-hot">
          <span className="muted">인기검색어</span>
          {brands.slice(0, 6).map((b) => <button key={b} onClick={() => setQ(b)}>{b}</button>)}
        </div>
      </div>

      <div className="srch-body">
        <aside className="srch-side">
          <h4>카테고리</h4>
          <ul>
            <li className={!ql ? "on" : ""} onClick={() => setQ("")}>전체</li>
            {cats.map((c) => <li key={c} onClick={() => setQ(c)}>{c}</li>)}
          </ul>
        </aside>
        <main className="srch-results">
          <div className="srch-count">{ql ? <>‘<b>{q}</b>’ 검색결과 <b>{results.length}</b>건</> : <>전체 <b>{results.length}</b>건</>}</div>
          {results.length === 0 ? <div className="pub-empty">검색 결과가 없습니다.</div> : results.map((p, i) => (
            <a className="srch-item" key={p.id} href={`/site/${slug}/p/${p.id}`}>
              <span className="srch-rank">{i + 1}</span>
              <img src={thumb(p.thumbnail_url)} onError={onImgError} alt="" loading="lazy" />
              <div className="srch-item-body">
                <div className="srch-item-title">{p.title}</div>
                <div className="srch-item-sub">
                  {p.brand && <span className="srch-brand">{p.brand}</span>}
                  {p.category && <span className="muted"> · {p.category}</span>}
                  {p.segment && SEG[p.segment] && <span className="srch-seg"> · {SEG[p.segment]}</span>}
                </div>
              </div>
              <div className="srch-item-right">
                <div className="srch-price">{priceOf(p)}</div>
                <span className="srch-go">바로가기 →</span>
              </div>
            </a>
          ))}
        </main>
      </div>
      <footer className="srch-foot">
        {owner["소개"] && <span>{owner["소개"]} · </span>}
        {data.affiliate_applied && <span>제휴 활동으로 수수료를 받을 수 있습니다 · </span>}Powered by TBURN.CLICK
      </footer>
    </div>
  );
}
