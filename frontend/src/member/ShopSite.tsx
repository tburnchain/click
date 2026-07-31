import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { thumb, onImgError } from "../img";
import { memberApi, type ProductDetail, type PubProduct, type PublicSiteData } from "../auth";

function won(n: number | null, cur?: string | null): string {
  if (n == null) return "";
  if (!cur || cur === "KRW") return "₩" + Math.round(n).toLocaleString("ko-KR");
  return `${cur} ${n.toLocaleString()}`;
}
const orig = (p: number | null) => (p == null ? null : Math.round(p * 1.28));
const discount = (p: number | null) => (p == null ? 0 : Math.round((1 - p / (p * 1.28)) * 100));
function stars(rating: number | null): string {
  const r = Math.round(rating ?? 4.5);
  return "★★★★★☆☆☆☆☆".slice(5 - Math.min(r, 5), 10 - Math.min(r, 5));
}
const reviews = (id: number) => 40 + ((id * 37) % 950);

const NAV = ["전체", "베스트", "신상품", "특가", "브랜드"];
const SORT_OF: Record<string, string> = { "전체": "score", "베스트": "best", "신상품": "new", "특가": "deal" };

function StoreHeader({ store, active, onNav, search, onSearch, ownerRef }: {
  store: { name: string; slug: string }; active?: string; onNav?: (n: string) => void;
  search?: string; onSearch?: (q: string) => void; ownerRef?: string | null;
}) {
  const rp = ownerRef ? `&ref=${ownerRef}` : "";
  return (
    <header className="shop-header">
      <div className="shop-header-in">
        <a className="shop-logo" href={`/site/${store.slug}`}
           onClick={(e) => { if (onNav) { e.preventDefault(); onNav("전체"); } }}>{store.name}</a>
        <div className="shop-search">
          <input placeholder="상품을 검색해보세요" value={search ?? ""}
                 onChange={(e) => onSearch?.(e.target.value)} disabled={!onSearch} />
          <button>🔍</button>
        </div>
        <div className="shop-icons">
          <a href={`/?auth=signup${rp}`}>♡ 찜</a>
          <a href={`/?auth=signup${rp}`}>🛒 장바구니</a>
          <a href={`/?auth=login${rp}`}>👤 로그인</a>
        </div>
      </div>
      <nav className="shop-nav">
        {NAV.map((c) => (
          <span key={c} className={active === c ? "on" : ""}
                onClick={onNav ? () => onNav(c) : undefined}>{c}</span>
        ))}
      </nav>
    </header>
  );
}

function ProductCard({ slug, p }: { slug: string; p: PubProduct }) {
  const price = p.price_krw ?? p.price_amount;
  const cur = p.price_krw ? "KRW" : p.currency;
  return (
    <a className="shop-card" href={`/site/${slug}/p/${p.id}`}>
      <div className="shop-card-img">
        <img src={thumb(p.thumbnail_url)} onError={onImgError} alt="" loading="lazy" />
        <span className="shop-badge">무료배송</span>
      </div>
      <div className="shop-card-body">
        {p.brand && <div className="shop-card-brand">{p.brand}</div>}
        <div className="shop-card-title">{p.title}</div>
        <div className="shop-card-price">
          <span className="shop-dc">{discount(price)}%</span>
          <span className="shop-now">{won(price, cur)}</span>
        </div>
        <div className="shop-card-orig">{won(orig(price), cur)}</div>
        <div className="shop-card-rate">{stars(4)} <span>({reviews(p.id)})</span></div>
      </div>
    </a>
  );
}

export function ShopHome({ slug, data, variant }: { slug: string; data: PublicSiteData; variant?: string }) {
  const owner = data.owner_info || {};
  const cfg = data.site_config || {};
  const primary = cfg.primary_color || undefined;
  const heroTitle = cfg.hero_title || (variant === "enterprise" ? "프리미엄 셀렉션" : "지금 가장 인기있는 상품");
  const heroSub = cfg.hero_subtitle || owner["소개"] || "엄선된 상품을 특별한 가격에 만나보세요";
  const [products, setProducts] = useState<PubProduct[]>(data.products);
  const [active, setActive] = useState("전체");
  const [brand, setBrand] = useState<string | null>(null);
  const [catFilter, setCatFilter] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);

  const brands = useMemo(() => [...new Set(products.map((p) => p.brand).filter(Boolean))] as string[], [products]);
  const cats = useMemo(() => [...new Set(products.map((p) => p.category).filter(Boolean))] as string[], [products]);

  const onNav = (n: string) => {
    setActive(n); setBrand(null); setCatFilter(null);
    if (n === "브랜드") return;
    setLoading(true);
    memberApi.publicSite(slug, SORT_OF[n] ?? "score")
      .then((r) => setProducts(r.products)).catch(() => {}).finally(() => setLoading(false));
  };

  const ql = q.trim().toLowerCase();
  const shown = products.filter((p) =>
    (!brand || p.brand === brand) &&
    (!catFilter || p.category === catFilter) &&
    (!ql || `${p.title} ${p.brand ?? ""} ${p.category ?? ""}`.toLowerCase().includes(ql)),
  );
  const headLabel: Record<string, string> = {
    "전체": "전체 상품", "베스트": "🏆 베스트 상품(평점순)", "신상품": "🆕 신상품", "특가": "🔥 특가 상품", "브랜드": "브랜드별 상품",
  };
  const sectionTitle = ql ? `"${q}" 검색결과` : brand ? `${brand} 상품` : catFilter ? `${catFilter}` : headLabel[active];

  return (
    <div className={`shop ${variant === "enterprise" ? "shop-ent" : ""}`}
         style={primary ? ({ "--shop-primary": primary } as CSSProperties) : undefined}>
      <StoreHeader store={{ name: data.title, slug }} active={active} onNav={onNav} search={q} onSearch={setQ} ownerRef={data.owner_ref} />
      <section className="shop-hero">
        <div className="shop-hero-txt">
          <div className="shop-hero-tag">{variant === "enterprise" ? "PREMIUM COLLECTION" : "TODAY'S PICK"}</div>
          <h2>{heroTitle}</h2>
          <p>{heroSub}</p>
        </div>
      </section>

      {/* 카테고리 스트립(실작동) */}
      {cats.length > 0 && (
        <div className="shop-cat-strip">
          <span className={!catFilter ? "on" : ""} onClick={() => setCatFilter(null)}>전체</span>
          {cats.map((c) => (
            <span key={c} className={catFilter === c ? "on" : ""} onClick={() => setCatFilter(catFilter === c ? null : c)}>{c}</span>
          ))}
        </div>
      )}

      {/* 브랜드 필터 바 */}
      {active === "브랜드" && (
        <div className="shop-brand-bar">
          <button className={!brand ? "on" : ""} onClick={() => setBrand(null)}>전체 브랜드</button>
          {brands.map((b) => <button key={b} className={brand === b ? "on" : ""} onClick={() => setBrand(b)}>{b}</button>)}
        </div>
      )}

      <main className="shop-main">
        <div className="shop-sec-head"><h3>{sectionTitle}</h3><span className="muted">{shown.length}개 상품</span></div>
        {loading ? (
          <div className="shop-grid">{Array.from({ length: 8 }).map((_, i) => <div className="shop-card" key={i}><div className="shop-card-img shop-ph" /></div>)}</div>
        ) : shown.length === 0 ? (
          <div className="pub-empty">해당 조건의 상품이 없습니다.</div>
        ) : (
          <div className="shop-grid">{shown.map((p) => <ProductCard key={p.id} slug={slug} p={p} />)}</div>
        )}
      </main>

      <footer className="shop-foot">
        <div className="shop-foot-in">
          <div><b>{data.title}</b>{owner["상호"] ? ` · ${owner["상호"]}` : ""}</div>
          {owner["소개"] && <div className="muted">{owner["소개"]}</div>}
          {data.affiliate_applied && <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>※ 일부 상품 링크는 제휴 활동으로 수수료를 받을 수 있습니다.</div>}
          <div className="muted" style={{ fontSize: 12 }}>Powered by TBURN.CLICK</div>
        </div>
      </footer>
    </div>
  );
}

export function ShopDetail({ slug, productId }: { slug: string; productId: number }) {
  const [d, setD] = useState<ProductDetail | null>(null);
  const [err, setErr] = useState(false);
  const [qty, setQty] = useState(1);
  const [store, setStore] = useState("");

  useEffect(() => {
    memberApi.product(slug, productId).then((r) => { setD(r); setStore(r.store); }).catch(() => setErr(true));
  }, [slug, productId]);

  const desc = useMemo(() => {
    if (!d) return "";
    const b = d.brand ? `${d.brand} ` : "";
    return `${b}${d.title}. ${d.category ?? "인기"} 카테고리의 베스트셀러로, 검증된 품질과 합리적인 가격을 자랑합니다. 지금 구매하시면 무료배송 혜택을 받으실 수 있습니다.`;
  }, [d]);

  if (err) return <div className="pub-empty">상품을 찾을 수 없습니다.</div>;
  if (!d) return <div className="pub-empty">불러오는 중…</div>;
  const price = d.price;

  return (
    <div className="shop">
      <StoreHeader store={{ name: store, slug }} ownerRef={d.owner_ref} />
      <div className="shop-crumb"><a href={`/site/${slug}`}>홈</a> › {d.category ?? "상품"} › <b>{d.title}</b></div>

      <div className="shop-detail">
        <div className="shop-gallery">
          <img className="shop-gal-main" src={thumb(d.thumbnail_url)} onError={onImgError} alt="" />
          <div className="shop-gal-thumbs">
            {Array.from({ length: 4 }).map((_, i) => <img key={i} src={thumb(d.thumbnail_url)} onError={onImgError} alt="" />)}
          </div>
        </div>
        <div className="shop-info">
          {d.brand && <div className="shop-brand">{d.brand}</div>}
          <h1 className="shop-name">{d.title}</h1>
          <div className="shop-rate">{stars(d.rating)} <b>{(d.rating ?? 4.5).toFixed(1)}</b> <span className="muted">리뷰 {reviews(d.id).toLocaleString()}개</span></div>
          <div className="shop-price-box">
            <div className="shop-orig">{won(orig(price), d.currency)}</div>
            <div className="shop-price-row"><span className="shop-dc-big">{discount(price)}%</span><span className="shop-price-now">{won(price, d.currency)}</span></div>
            <div className="shop-benefit">🚚 무료배송 · 💳 무이자 할부 · 🎁 적립 {price ? Math.round(price * 0.01).toLocaleString() : 0}P</div>
          </div>
          <div className="shop-buy-area">
            <div className="shop-qty">
              <button onClick={() => setQty((x) => Math.max(1, x - 1))}>−</button><span>{qty}</span><button onClick={() => setQty((x) => x + 1)}>＋</button>
            </div>
            <div className="shop-total">총 상품금액 <b>{won(price ? price * qty : null, d.currency)}</b></div>
          </div>
          <div className="shop-actions">
            <a className="shop-buy" href={d.buy_url ?? "#"} target="_blank" rel="noreferrer noopener sponsored">구매하기</a>
            <button className="shop-cart">장바구니</button>
            <button className="shop-wish">♡</button>
          </div>
          <div className="shop-ship muted">{d.stock_status === "out_of_stock" ? "일시품절" : "재고 있음"} · {d.network} 판매 · 오늘 주문 시 내일 도착</div>
        </div>
      </div>

      <div className="shop-tabs"><span className="on">상품정보</span><span>리뷰({reviews(d.id)})</span><span>배송/교환</span></div>
      <div className="shop-desc">
        <p>{desc}</p>
        {d.thumbnail_url && <img src={d.thumbnail_url} alt="" className="shop-desc-img" />}
        <p className="muted" style={{ fontSize: 12 }}>본 상품은 {d.network}에서 판매되며, 구매하기 클릭 시 판매처로 이동합니다.</p>
      </div>

      {d.related.length > 0 && (
        <div className="shop-main">
          <div className="shop-sec-head"><h3>함께 보면 좋은 상품</h3></div>
          <div className="shop-grid">
            {d.related.map((r) => (
              <a className="shop-card" key={r.id} href={`/site/${slug}/p/${r.id}`}>
                <div className="shop-card-img"><img src={thumb(r.thumbnail_url)} onError={onImgError} alt="" /></div>
                <div className="shop-card-body"><div className="shop-card-title">{r.title}</div>
                  <div className="shop-card-price"><span className="shop-now">{won(r.price_krw ?? r.price_amount, r.price_krw ? "KRW" : r.currency)}</span></div></div>
              </a>
            ))}
          </div>
        </div>
      )}
      <footer className="shop-foot"><div className="shop-foot-in"><b>{store}</b><div className="muted" style={{ fontSize: 12 }}>※ 제휴 활동으로 수수료를 받을 수 있습니다 · Powered by TBURN.CLICK</div></div></footer>
    </div>
  );
}
