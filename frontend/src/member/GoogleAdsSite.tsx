import { Fragment, useEffect, useRef, type CSSProperties } from "react";
import { thumb, onImgError } from "../img";
import type { PubProduct, PublicSiteData } from "../auth";

declare global {
  interface Window { dataLayer?: unknown[]; gtag?: (...args: unknown[]) => void; adsbygoogle?: unknown[] }
}

const ATTR_KEYS = ["gclid", "wbraid", "gbraid", "utm_source", "utm_medium",
  "utm_campaign", "utm_term", "utm_content"];

function readAttr(): Record<string, string> {
  let store: Record<string, string> = {};
  try { store = JSON.parse(sessionStorage.getItem("gads_attr") || "{}"); } catch { /* noop */ }
  const p = new URLSearchParams(location.search);
  ATTR_KEYS.forEach((k) => { const v = p.get(k); if (v) store[k] = v; });
  try { sessionStorage.setItem("gads_attr", JSON.stringify(store)); } catch { /* noop */ }
  return store;
}

function won(p: PubProduct): string {
  if (p.price_krw) return "₩" + Math.round(p.price_krw).toLocaleString("ko-KR");
  if (p.price_amount) return `${p.currency ?? ""} ${p.price_amount.toLocaleString()}`;
  return "무료";
}
const priceNum = (p: PubProduct) => p.price_krw ?? p.price_amount ?? 0;

// 광고 슬롯: client 설정 시 실제 AdSense <ins>, 아니면 위치 확인용 플레이스홀더
function AdSlot({ client, slot, variant, label }: {
  client: string; slot: string; variant: "rail" | "inline" | "anchor"; label: string;
}) {
  const pushed = useRef(false);
  useEffect(() => {
    if (client && !pushed.current) {
      try { (window.adsbygoogle = window.adsbygoogle || []).push({}); pushed.current = true; } catch { /* noop */ }
    }
  }, [client]);
  const fmt = variant === "rail" ? "vertical" : variant === "anchor" ? "horizontal" : "auto";
  return (
    <div className={`gad-ad gad-ad-${variant}`}>
      <span className="gad-ad-tag">광고 · Google</span>
      {client ? (
        <ins className="adsbygoogle" style={{ display: "block", width: "100%", height: "100%" }}
             data-ad-client={client} data-ad-slot={slot || undefined}
             data-ad-format={fmt} data-full-width-responsive="true" />
      ) : (
        <div className="gad-ad-ph">📢 {label} 광고 영역<br /><small>게시자 ID 입력 시 노출</small></div>
      )}
    </div>
  );
}

export function GoogleAdsSite({ data }: { slug: string; data: PublicSiteData }) {
  const cfg = data.site_config || {};
  const primary = cfg.primary_color || "#1a73e8";
  const heroTitle = cfg.hero_title || `${data.title} — 지금 특별 혜택`;
  const heroSub = cfg.hero_subtitle || (data.owner_info?.["소개"]) || "엄선한 인기 상품을 최저가로 만나보세요. 오늘만 특별가!";
  const aw = (cfg.ads_conversion_id || "").trim();
  const label = (cfg.ads_conversion_label || "").trim();
  const sendTo = aw && label ? `${aw}/${label}` : aw;
  const adClient = (cfg.adsense_client || "").trim();
  const adSlot = (cfg.adsense_slot || "").trim();

  // gtag + gclid/UTM 캡처
  useEffect(() => {
    const ids = [cfg.ga4_id, cfg.ads_conversion_id].map((x) => (x || "").trim()).filter(Boolean);
    readAttr();
    if (!ids.length) return;
    window.dataLayer = window.dataLayer || [];
    if (!window.gtag) window.gtag = function gtag() { window.dataLayer!.push(arguments); };
    if (!document.getElementById("gtag-js")) {
      const s = document.createElement("script");
      s.id = "gtag-js"; s.async = true;
      s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(ids[0]);
      document.head.appendChild(s);
    }
    window.gtag("js", new Date());
    ids.forEach((id) => window.gtag!("config", id));
    window.gtag("event", "view_item_list", { items: data.products.length });
  }, [cfg.ga4_id, cfg.ads_conversion_id, data.products.length]);

  // AdSense 로더(게시자 ID 설정 시)
  useEffect(() => {
    if (!adClient) return;
    if (!document.getElementById("adsense-js")) {
      const s = document.createElement("script");
      s.id = "adsense-js"; s.async = true; s.crossOrigin = "anonymous";
      s.src = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" + encodeURIComponent(adClient);
      document.head.appendChild(s);
    }
  }, [adClient]);

  const onBuy = (e: React.MouseEvent<HTMLAnchorElement>, p: PubProduct) => {
    const store = readAttr();
    const a = e.currentTarget;
    try {
      const u = new URL(a.href);
      Object.entries(store).forEach(([k, v]) => u.searchParams.set(k, v));
      a.href = u.toString();
    } catch { /* noop */ }
    if (window.gtag) {
      if (sendTo) window.gtag("event", "conversion", { send_to: sendTo, value: priceNum(p), currency: p.price_krw ? "KRW" : (p.currency || "USD") });
      window.gtag("event", "select_content", { content_type: "product", item_id: String(p.id) });
    }
  };

  const items = data.products.slice(0, 12);
  const style = { "--gad": primary } as CSSProperties;
  const ad = (variant: "rail" | "inline" | "anchor", lbl: string) =>
    <AdSlot client={adClient} slot={adSlot} variant={variant} label={lbl} />;

  return (
    <div className="gad gad-ads" style={style}>
      <header className="gad-top">
        <div className="gad-logo">{data.title}</div>
        <a className="gad-top-cta" href="#offers">혜택 보기 →</a>
      </header>

      <div className="gad-layout">
        {/* 좌측 광고 */}
        <aside className="gad-rail gad-rail-l">{ad("rail", "좌측")}</aside>

        <main className="gad-main">
          <section className="gad-hero">
            <div className="gad-badge">🔥 오늘의 프로모션</div>
            <h1>{heroTitle}</h1>
            <p>{heroSub}</p>
            <a className="gad-cta" href="#offers">지금 확인하기</a>
            <div className="gad-trust">
              <span>✅ 검증된 판매처</span><span>🚚 빠른 배송</span><span>🔒 안전 결제</span><span>⭐ 실사용 리뷰</span>
            </div>
          </section>

          {/* 중앙 광고(인콘텐츠) */}
          {ad("inline", "중앙")}

          <section className="gad-offers" id="offers">
            <h2>엄선 특가 {items.length}선</h2>
            <div className="gad-grid">
              {items.map((p, i) => (
                <Fragment key={p.id}>
                  <div className="gad-card">
                    <div className="gad-img">
                      <img src={thumb(p.thumbnail_url)} onError={onImgError} alt={p.title} loading="lazy" />
                      <span className="gad-off">특가</span>
                    </div>
                    <div className="gad-b">
                      {p.brand && <div className="gad-brand">{p.brand}</div>}
                      <div className="gad-name">{p.title}</div>
                      <div className="gad-price">{won(p)}</div>
                      <a className="gad-buy" href={p.url} target="_blank"
                         rel="sponsored nofollow noopener" onClick={(e) => onBuy(e, p)}
                         data-buy data-id={p.id}>구매하기 →</a>
                    </div>
                  </div>
                  {/* 그리드 중앙 인피드 광고 */}
                  {i === 3 && <div className="gad-infeed">{ad("inline", "인피드")}</div>}
                </Fragment>
              ))}
            </div>
          </section>

          <section className="gad-why">
            <h2>왜 지금 구매해야 할까요?</h2>
            <div className="gad-why-grid">
              <div><b>⏱️ 한정 수량</b><p>인기 상품은 조기 품절될 수 있습니다.</p></div>
              <div><b>💰 최저가 비교</b><p>여러 판매처 중 합리적인 가격만 선별했습니다.</p></div>
              <div><b>🎁 오늘의 혜택</b><p>지금 구매 시 추가 적립·무료배송 혜택.</p></div>
            </div>
            <a className="gad-cta" href="#offers">특가 상품 다시 보기</a>
          </section>
        </main>

        {/* 우측 광고 */}
        <aside className="gad-rail gad-rail-r">{ad("rail", "우측")}</aside>
      </div>

      <footer className="gad-foot">
        <b>{data.title}</b>
        {data.affiliate_applied && <div className="gad-ftc">※ 일부 링크는 제휴 활동으로 수수료를 받을 수 있습니다.</div>}
        <div className="gad-ftc">Powered by TBURN.CLICK · Google Ads·AdSense 최적화</div>
      </footer>

      {/* 하단 고정 광고(앵커) */}
      <div className="gad-anchor">{ad("anchor", "하단")}</div>
    </div>
  );
}
