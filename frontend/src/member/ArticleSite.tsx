import type { PublicSiteData, PubProduct } from "../auth";
import { thumb, onImgError } from "../img";

function priceOf(p: PubProduct): string {
  if (p.price_krw) return "₩" + Math.round(p.price_krw).toLocaleString("ko-KR");
  if (p.price_amount) return `${p.currency ?? ""} ${p.price_amount.toLocaleString()}`;
  return "";
}

export function ArticleSite({ slug, data }: { slug: string; data: PublicSiteData }) {
  const owner = data.owner_info || {};
  const products = data.products;
  const hero = products[0];
  const picks = products.slice(1, 4);
  const rest = products.slice(4, 12);

  return (
    <div className="art">
      <header className="art-masthead">
        <div className="art-brand">{data.title}</div>
        <nav className="art-nav"><span>매거진</span><span>리뷰</span><span>추천</span><span>랭킹</span></nav>
      </header>

      <article className="art-main">
        <div className="art-tag">EDITOR'S PICK · 상품 리뷰</div>
        <h1 className="art-headline">2026년 지금 사야 할 인기 아이템 {products.length}선</h1>
        <div className="art-byline">에디터 {owner["상호"] ?? data.title} · 실사용 리뷰 기반 큐레이션</div>

        {hero && (
          <a className="art-hero" href={`/site/${slug}/p/${hero.id}`}>
            <img src={thumb(hero.thumbnail_url)} onError={onImgError} alt="" />
            <div className="art-hero-cap">대표 추천: {hero.title} — {priceOf(hero)}</div>
          </a>
        )}

        <p className="art-lead">
          {owner["소개"] ?? "요즘 가장 주목받는 상품들을 직접 살펴봤습니다."} 아래는 판매량·평점·가격을 종합해
          엄선한 리스트입니다. 각 상품명을 누르면 상세 정보와 구매 페이지로 이동합니다.
        </p>

        {picks.map((p, i) => (
          <section className="art-block" key={p.id}>
            <h2>{i + 1}. {p.title}</h2>
            <a className="art-embed" href={`/site/${slug}/p/${p.id}`}>
              <img src={thumb(p.thumbnail_url)} onError={onImgError} alt="" />
              <div className="art-embed-info">
                {p.brand && <div className="art-embed-brand">{p.brand}</div>}
                <div className="art-embed-title">{p.title}</div>
                <div className="art-embed-price">{priceOf(p)}</div>
                <span className="art-embed-cta">자세히 보기 →</span>
              </div>
            </a>
            <p>{p.brand ? `${p.brand}의 ` : ""}{p.title}은(는) {p.category ?? "인기"} 카테고리에서 꾸준히 사랑받는 제품입니다.
              합리적인 가격과 검증된 품질로 지금 구매하기 좋은 타이밍입니다.</p>
          </section>
        ))}
      </article>

      {rest.length > 0 && (
        <section className="art-more">
          <h3>이런 상품도 추천해요</h3>
          <div className="art-grid">
            {rest.map((p) => (
              <a className="art-card" key={p.id} href={`/site/${slug}/p/${p.id}`}>
                <img src={thumb(p.thumbnail_url)} onError={onImgError} alt="" loading="lazy" />
                <div className="art-card-title">{p.title}</div>
                <div className="art-card-price">{priceOf(p)}</div>
              </a>
            ))}
          </div>
        </section>
      )}

      <footer className="art-foot">
        {data.affiliate_applied && <span>※ 본 콘텐츠는 제휴 활동으로 일정 수수료를 받을 수 있습니다. </span>}
        © {data.title} · Powered by TBURN.CLICK
      </footer>
    </div>
  );
}
