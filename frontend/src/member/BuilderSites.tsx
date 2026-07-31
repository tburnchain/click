import { useMemo, useState, type CSSProperties } from "react";
import { thumb, onImgError } from "../img";
import type { PubProduct, PublicSiteData } from "../auth";

// ── 공용 헬퍼 ──
function won(p: PubProduct): string {
  if (p.price_krw) return "₩" + Math.round(p.price_krw).toLocaleString("ko-KR");
  if (p.price_amount) return `${p.currency ?? ""} ${p.price_amount.toLocaleString()}`;
  return "가격문의";
}
const priceNum = (p: PubProduct) => p.price_krw ?? p.price_amount ?? 0;
const dcOf = (id: number) => 12 + ((id * 7) % 48);            // 12~59% (상품별 고정)
const origWon = (p: PubProduct) => {
  const n = priceNum(p); if (!n) return "";
  const o = Math.round(n / (1 - dcOf(p.id) / 100));
  return p.price_krw ? "₩" + o.toLocaleString("ko-KR") : `${p.currency ?? ""} ${o.toLocaleString()}`;
};
const rateOf = (id: number) => (38 + (id * 13) % 12) / 10;     // 3.8~4.9
const reviewsOf = (id: number) => 42 + (id * 37) % 1900;
const stars = (r: number) => "★★★★★☆☆☆☆☆".slice(5 - Math.min(Math.round(r), 5), 10 - Math.min(Math.round(r), 5));
const stockLeft = (id: number) => 3 + (id * 17) % 40;

const SEG_LABEL: Record<string, string> = {
  goldmine: "강력추천", rising: "인기상승", cashcow: "스테디셀러", saturated: "인기", avoid: "",
};

// 로그인/가입 → GAMDAP(회원 추천코드 주입 → 가입 커미션)
function JoinBar({ ownerRef, theme }: { ownerRef: string | null; theme?: string }) {
  const rp = ownerRef ? `&ref=${ownerRef}` : "";
  return (
    <div className={`nb-join ${theme ?? ""}`}>
      <a href={`/?auth=signup${rp}`}>♡ 찜</a>
      <a href={`/?auth=signup${rp}`}>🛒 담기</a>
      <a href={`/?auth=login${rp}`}>👤 로그인</a>
    </div>
  );
}

function Foot({ data }: { data: PublicSiteData }) {
  const owner = data.owner_info || {};
  return (
    <footer className="nb-foot">
      <b>{data.title}</b>{owner["상호"] ? ` · ${owner["상호"]}` : ""}
      {owner["소개"] && <div className="muted">{owner["소개"]}</div>}
      {data.affiliate_applied && <div className="nb-ftc">※ 일부 링크는 제휴 활동으로 수수료를 받을 수 있습니다.</div>}
      <div className="muted" style={{ fontSize: 12 }}>Powered by GAMDAP</div>
    </footer>
  );
}

const accentStyle = (data: PublicSiteData): CSSProperties | undefined => {
  const c = data.site_config?.primary_color;
  return c ? ({ "--nb-accent": c } as CSSProperties) : undefined;
};
const heroTitle = (data: PublicSiteData, fb: string) => data.site_config?.hero_title || fb;
const heroSub = (data: PublicSiteData, fb: string) =>
  data.site_config?.hero_subtitle || data.owner_info?.["소개"] || fb;

// ══════════════ 1) 핫딜·타임특가형 ══════════════
export function DealSite({ slug, data }: { slug: string; data: PublicSiteData }) {
  const items = [...data.products].sort((a, b) => priceNum(a) - priceNum(b));
  return (
    <div className="deal" style={accentStyle(data)}>
      <header className="deal-top">
        <div className="deal-logo">⚡ {data.title}</div>
        <div className="deal-timer">오늘 자정 <b>23:59</b> 마감 · 매일 갱신</div>
        <JoinBar ownerRef={data.owner_ref} theme="dark" />
      </header>
      <div className="deal-hero">
        <h1>{heroTitle(data, "🔥 오늘의 핫딜")}</h1>
        <p>{heroSub(data, "마감 임박! 최대 59% 할인 · 수량 소진 시 종료")}</p>
      </div>
      <main className="deal-grid">
        {items.map((p, i) => (
          <a className="deal-card" key={p.id} href={`/site/${slug}/p/${p.id}`}>
            <div className="deal-badge">{dcOf(p.id)}%<small>↓</small></div>
            {i < 3 && <div className="deal-rank">🔥 인기 {i + 1}위</div>}
            <div className="deal-img"><img src={thumb(p.thumbnail_url)} onError={onImgError} alt="" loading="lazy" /></div>
            <div className="deal-body">
              <div className="deal-name">{p.title}</div>
              <div className="deal-price"><span className="deal-orig">{origWon(p)}</span><span className="deal-now">{won(p)}</span></div>
              <div className="deal-stock">
                <div className="deal-stock-bar"><span style={{ width: `${100 - stockLeft(p.id) * 2}%` }} /></div>
                <span>{stockLeft(p.id)}개 남음</span>
              </div>
              <div className="deal-cta">딜 받기 →</div>
            </div>
          </a>
        ))}
      </main>
      <Foot data={data} />
    </div>
  );
}

// ══════════════ 2) 랭킹·리뷰형 ══════════════
const RANK_PROS: Record<string, string[]> = {
  goldmine: ["가성비 최고", "재구매율 높음"], rising: ["요즘 뜨는", "리뷰 급상승"],
  cashcow: ["스테디셀러", "검증된 만족도"], saturated: ["대중적 인기", "무난한 선택"], avoid: ["입문용"],
};
export function RankingSite({ slug, data }: { slug: string; data: PublicSiteData }) {
  const items = data.products.slice(0, 15);
  return (
    <div className="rank" style={accentStyle(data)}>
      <header className="rank-top">
        <div className="rank-logo">🏅 {data.title}</div>
        <span className="rank-tag">전문가 랭킹 · {new Date().getFullYear()}</span>
        <JoinBar ownerRef={data.owner_ref} />
      </header>
      <div className="rank-hero">
        <h1>{heroTitle(data, `에디터가 뽑은 베스트 ${items.length}`)}</h1>
        <p>{heroSub(data, "실사용 후기·평점·가성비를 종합해 직접 순위를 매겼습니다.")}</p>
      </div>
      <main className="rank-list">
        {items.map((p, i) => (
          <a className={`rank-item ${i === 0 ? "rank-1" : ""}`} key={p.id} href={`/site/${slug}/p/${p.id}`}>
            <div className="rank-num">{i === 0 ? "👑" : ""}{i + 1}</div>
            <div className="rank-thumb"><img src={thumb(p.thumbnail_url)} onError={onImgError} alt="" loading="lazy" /></div>
            <div className="rank-info">
              {i === 0 && <div className="rank-crown">1위 BEST PICK</div>}
              {p.brand && <div className="rank-brand">{p.brand}</div>}
              <div className="rank-name">{p.title}</div>
              <div className="rank-rate"><b>{rateOf(p.id).toFixed(1)}</b> <span className="rank-stars">{stars(rateOf(p.id))}</span> <span className="muted">({reviewsOf(p.id).toLocaleString()} 리뷰)</span></div>
              <div className="rank-pros">
                {(RANK_PROS[p.segment ?? ""] ?? RANK_PROS.cashcow).map((t) => <span key={t}>✓ {t}</span>)}
                {p.category && <span>✓ {p.category}</span>}
              </div>
            </div>
            <div className="rank-right"><div className="rank-price">{won(p)}</div><span className="rank-go">자세히 →</span></div>
          </a>
        ))}
      </main>
      <Foot data={data} />
    </div>
  );
}

// ══════════════ 3) 쿠폰·혜택형 ══════════════
export function CouponSite({ slug, data }: { slug: string; data: PublicSiteData }) {
  const [copied, setCopied] = useState<number | null>(null);
  const code = (p: PubProduct) => `SAVE${dcOf(p.id)}`;
  const copy = (p: PubProduct, e: React.MouseEvent) => {
    e.preventDefault();
    navigator.clipboard?.writeText(code(p));
    setCopied(p.id); setTimeout(() => setCopied((c) => (c === p.id ? null : c)), 1500);
  };
  return (
    <div className="cpn" style={accentStyle(data)}>
      <header className="cpn-top">
        <div className="cpn-logo">🎟️ {data.title}</div>
        <span className="cpn-tag">오늘의 쿠폰·프로모코드</span>
        <JoinBar ownerRef={data.owner_ref} />
      </header>
      <div className="cpn-hero">
        <h1>{heroTitle(data, "지금 쓸 수 있는 할인 쿠폰")}</h1>
        <p>{heroSub(data, "코드를 복사하고 구매처에서 붙여넣으면 추가 할인!")}</p>
      </div>
      <main className="cpn-grid">
        {data.products.map((p) => (
          <div className="cpn-ticket" key={p.id}>
            <div className="cpn-left">
              <div className="cpn-off">{dcOf(p.id)}%<small>OFF</small></div>
              <div className="cpn-brand">{p.brand || p.network}</div>
            </div>
            <div className="cpn-mid">
              <div className="cpn-name">{p.title}</div>
              {p.segment && SEG_LABEL[p.segment] && <div className="cpn-seg">{SEG_LABEL[p.segment]}</div>}
              <div className="cpn-code">
                <code>{code(p)}</code>
                <button onClick={(e) => copy(p, e)}>{copied === p.id ? "복사됨 ✓" : "코드 복사"}</button>
              </div>
            </div>
            <a className="cpn-use" href={`/site/${slug}/p/${p.id}`}>쿠폰 쓰러가기 →</a>
          </div>
        ))}
      </main>
      <Foot data={data} />
    </div>
  );
}

// ══════════════ 4) 감성 셀렉트샵(룩북)형 ══════════════
export function BoutiqueSite({ slug, data }: { slug: string; data: PublicSiteData }) {
  return (
    <div className="btq">
      <header className="btq-top">
        <div className="btq-nav">NEW · LOOKBOOK · SALE</div>
        <div className="btq-logo">{data.title}</div>
        <JoinBar ownerRef={data.owner_ref} theme="btq" />
      </header>
      <div className="btq-hero">
        <div className="btq-hero-sub">CURATED SELECTION</div>
        <h1>{heroTitle(data, "LOOKBOOK")}</h1>
        <p>{heroSub(data, "취향을 아는 셀렉트샵 — 하나하나 골라 담았습니다.")}</p>
      </div>
      <main className="btq-grid">
        {data.products.map((p, i) => (
          <a className={`btq-card ${i % 5 === 0 ? "btq-wide" : ""}`} key={p.id} href={`/site/${slug}/p/${p.id}`}>
            <div className="btq-img"><img src={thumb(p.thumbnail_url)} onError={onImgError} alt="" loading="lazy" /></div>
            <div className="btq-info">
              <div className="btq-brand">{(p.brand || p.category || "SELECT").toUpperCase()}</div>
              <div className="btq-name">{p.title}</div>
              <div className="btq-price">{won(p)}</div>
              <span className="btq-shop">SHOP →</span>
            </div>
          </a>
        ))}
      </main>
      <Foot data={data} />
    </div>
  );
}

// ══════════════ 5) 리뷰 블로그형 ══════════════
const BLOG_INTROS = [
  "요즘 부쩍 문의가 많아서, 제가 직접 써보고 정말 만족했던 것들만 골라 정리했어요.",
  "가격·성능·후기를 며칠에 걸쳐 비교해봤는데, 결론부터 말하면 아래 제품들은 후회 없습니다.",
  "협찬 없이 제 돈으로 사서 써본 솔직 후기예요. 장단점 가감 없이 적어둘게요.",
];
const BLOG_LINES = [
  "실제로 한 달 넘게 매일 쓰면서 느낀 건, 이 가격대에서 이 정도 마감이면 충분하다는 점이에요.",
  "배송도 빠르고 포장도 꼼꼼했어요. 무엇보다 재구매 의사가 확실히 생기더라고요.",
  "친구들한테도 추천했더니 다들 만족했어요. 아래 링크에서 최저가 확인해보세요.",
];
export function BlogSite({ slug, data }: { slug: string; data: PublicSiteData }) {
  const owner = data.owner_info || {};
  const author = owner["상호"] || data.title;
  const posts = data.products.slice(0, 12);
  return (
    <div className="blog">
      <header className="blog-top">
        <div className="blog-logo">✍️ {data.title}</div>
        <JoinBar ownerRef={data.owner_ref} theme="blog" />
      </header>
      <article className="blog-post">
        <div className="blog-cat">REVIEW · 추천템</div>
        <h1>{heroTitle(data, "내가 직접 써보고 추천하는 아이템 모음")}</h1>
        <div className="blog-byline">by <b>{author}</b> · {new Date().getFullYear()}. {new Date().getMonth() + 1} · 실사용 후기</div>
        <p className="blog-lead">{heroSub(data, BLOG_INTROS[data.title.length % BLOG_INTROS.length])}</p>

        {posts.map((p, i) => (
          <section className="blog-block" key={p.id}>
            <h2>{i + 1}. {p.title}</h2>
            <p>{BLOG_LINES[i % BLOG_LINES.length]} {p.brand ? `${p.brand} 제품이라 신뢰가 갔고, ` : ""}
              {p.category ? `${p.category} 카테고리에서 특히 반응이 좋아요.` : "가성비가 좋아요."}</p>
            <a className="blog-rec" href={`/site/${slug}/p/${p.id}`}>
              <img src={thumb(p.thumbnail_url)} onError={onImgError} alt="" loading="lazy" />
              <div className="blog-rec-info">
                <div className="blog-rec-tag">👉 추천 아이템</div>
                <div className="blog-rec-name">{p.title}</div>
                <div className="blog-rec-rate">{stars(rateOf(p.id))} {rateOf(p.id).toFixed(1)} · 리뷰 {reviewsOf(p.id).toLocaleString()}</div>
                <div className="blog-rec-price">{won(p)} <span className="blog-rec-go">구매처 보기 →</span></div>
              </div>
            </a>
          </section>
        ))}
        <p className="blog-out">읽어주셔서 감사해요! 도움이 됐다면 위 링크로 구매하시면 저에게 소소한 커미션이 돌아갑니다 🙏</p>
      </article>
      <Foot data={data} />
    </div>
  );
}

// ══════════════ 6) 가격비교·카탈로그형 ══════════════
export function DirectorySite({ slug, data }: { slug: string; data: PublicSiteData }) {
  const [cat, setCat] = useState<string | null>(null);
  const [sort, setSort] = useState<"price" | "rate">("price");
  const cats = useMemo(() => [...new Set(data.products.map((p) => p.category).filter(Boolean))].slice(0, 10) as string[], [data]);
  const rows = useMemo(() => {
    const r = data.products.filter((p) => !cat || p.category === cat);
    return r.sort((a, b) => sort === "price" ? priceNum(a) - priceNum(b) : rateOf(b.id) - rateOf(a.id));
  }, [data, cat, sort]);
  return (
    <div className="dir" style={accentStyle(data)}>
      <header className="dir-top">
        <div className="dir-logo">📊 {data.title}</div>
        <span className="dir-tag">최저가 비교 · 카탈로그</span>
        <JoinBar ownerRef={data.owner_ref} />
      </header>
      <div className="dir-hero">
        <h1>{heroTitle(data, "최저가 한눈에 비교")}</h1>
        <p>{heroSub(data, "가격·평점·판매처를 한 표에서 비교하고 최저가로 이동하세요.")}</p>
      </div>
      <div className="dir-toolbar">
        <div className="dir-cats">
          <span className={!cat ? "on" : ""} onClick={() => setCat(null)}>전체</span>
          {cats.map((c) => <span key={c} className={cat === c ? "on" : ""} onClick={() => setCat(c)}>{c}</span>)}
        </div>
        <div className="dir-sort">
          <button className={sort === "price" ? "on" : ""} onClick={() => setSort("price")}>최저가순</button>
          <button className={sort === "rate" ? "on" : ""} onClick={() => setSort("rate")}>평점순</button>
        </div>
      </div>
      <div className="dir-table-wrap">
        <table className="dir-table">
          <thead><tr><th>#</th><th>상품</th><th>카테고리</th><th>판매처</th><th className="num">평점</th><th className="num">최저가</th><th></th></tr></thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={p.id}>
                <td className="dir-rk">{i + 1}</td>
                <td className="dir-prod">
                  <img src={thumb(p.thumbnail_url)} onError={onImgError} alt="" loading="lazy" />
                  <div><div className="dir-name">{p.title}</div>{p.brand && <div className="muted">{p.brand}</div>}</div>
                </td>
                <td className="muted">{p.category || "-"}</td>
                <td><span className="dir-net">{p.network}</span></td>
                <td className="num">{rateOf(p.id).toFixed(1)} <span className="dir-star">★</span></td>
                <td className="num dir-price">{won(p)}</td>
                <td><a className="dir-go" href={`/site/${slug}/p/${p.id}`}>최저가 →</a></td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <div className="pub-empty">해당 조건의 상품이 없습니다.</div>}
      </div>
      <Foot data={data} />
    </div>
  );
}
