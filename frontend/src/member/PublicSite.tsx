import { useEffect, useState } from "react";
import { thumb, onImgError } from "../img";
import { memberApi, type PublicSiteData } from "../auth";

function price(p: PublicSiteData["products"][0]): string {
  if (p.price_krw) return "₩" + Math.round(p.price_krw).toLocaleString("ko-KR");
  if (p.price_amount) return `${p.currency ?? ""} ${p.price_amount.toLocaleString()}`;
  return "";
}

export function PublicSite({ slug, preloaded }: { slug: string; preloaded?: PublicSiteData }) {
  const [data, setData] = useState<PublicSiteData | null>(preloaded ?? null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    if (preloaded) { setData(preloaded); return; }
    memberApi.publicSite(slug).then(setData).catch(() => setErr(true));
  }, [slug, preloaded]);

  if (err) return <div className="pub-empty">사이트를 찾을 수 없습니다.</div>;
  if (!data) return <div className="pub-empty">불러오는 중…</div>;

  const grid = data.kind === "shopping" || data.kind === "enterprise" || data.kind === "mixed";
  const owner = data.owner_info || {};

  return (
    <div className={`pub pub-${data.kind}`}>
      <header className="pub-head">
        <h1>{data.title}</h1>
        {Object.keys(owner).length > 0 && (
          <p className="pub-owner">{Object.entries(owner).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>
        )}
        {(data.kind === "search" || data.kind === "mixed") && (
          <div className="pub-search"><input placeholder="상품 검색…" disabled /> 🔍</div>
        )}
      </header>

      <div className={grid ? "pub-grid" : "pub-list"}>
        {data.products.map((p, i) => (
          <a className="pub-item" key={i} href={p.url} target="_blank" rel="noreferrer noopener sponsored">
            <img src={thumb(p.thumbnail_url)} onError={onImgError} alt="" loading="lazy" />
            <div className="pub-item-body">
              <div className="pub-item-title">{p.title}</div>
              <div className="pub-item-meta">
                <span className="pub-price">{price(p)}</span>
                <span className="pub-net">{p.network}</span>
              </div>
            </div>
          </a>
        ))}
        {data.products.length === 0 && <div className="pub-empty">등록된 상품이 없습니다.</div>}
      </div>

      <footer className="pub-foot">
        {data.affiliate_applied && <span className="pub-disc">※ 본 페이지의 링크는 제휴 활동으로 수수료를 받을 수 있습니다.</span>}
        <span className="muted"> · Powered by GAMDAP</span>
      </footer>
    </div>
  );
}
