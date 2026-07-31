import { useEffect, useState } from "react";
import { memberApi, type PublicSiteData } from "../auth";
import { PublicSite } from "./PublicSite";
import { ShopDetail, ShopHome } from "./ShopSite";
import { SearchSite } from "./SearchSite";
import { ArticleSite } from "./ArticleSite";
import { DealSite, RankingSite, CouponSite, BoutiqueSite, BlogSite, DirectorySite } from "./BuilderSites";
import { GoogleAdsSite } from "./GoogleAdsSite";

export function SitePage({ path }: { path: string }) {
  // /site/{slug}  또는  /site/{slug}/p/{id}
  const rest = decodeURIComponent(path.slice("/site/".length));
  const segs = rest.split("/");
  const slug = segs[0];
  const productId = segs[1] === "p" && segs[2] ? parseInt(segs[2], 10) : null;

  const [data, setData] = useState<PublicSiteData | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    if (productId != null) return; // 상세는 ShopDetail이 자체 fetch
    memberApi.publicSite(slug).then(setData).catch(() => setErr(true));
  }, [slug, productId]);

  if (productId != null) return <ShopDetail slug={slug} productId={productId} />;
  if (err) return <div className="pub-empty">사이트를 찾을 수 없습니다.</div>;
  if (!data) return <div className="pub-empty">불러오는 중…</div>;

  switch (data.kind) {
    case "shopping":
    case "mixed":
      return <ShopHome slug={slug} data={data} />;
    case "enterprise":
      return <ShopHome slug={slug} data={data} variant="enterprise" />;
    case "search":
      return <SearchSite slug={slug} data={data} />;
    case "article":
      return <ArticleSite slug={slug} data={data} />;
    case "deal":
      return <DealSite slug={slug} data={data} />;
    case "ranking":
      return <RankingSite slug={slug} data={data} />;
    case "coupon":
      return <CouponSite slug={slug} data={data} />;
    case "boutique":
      return <BoutiqueSite slug={slug} data={data} />;
    case "blog":
      return <BlogSite slug={slug} data={data} />;
    case "directory":
      return <DirectorySite slug={slug} data={data} />;
    case "google_ads":
      return <GoogleAdsSite slug={slug} data={data} />;
    default:
      return <PublicSite slug={slug} preloaded={data} />;
  }
}
