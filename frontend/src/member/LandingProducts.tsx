import { useEffect, useState } from "react";
import { api } from "../api";
import { onImgError } from "../img";
import type { Category, Offer } from "../types";
import { getBasket, inBasket, toggleBasket } from "../basket";

const SEG_LABEL: Record<string, string> = {
  goldmine: "🟢 금맥", rising: "🔵 신흥", cashcow: "🟡 안정",
  saturated: "🟠 포화", avoid: "🔴 회피",
};
const SORTS: [string, string][] = [["score", "수익성순"], ["price", "가격순"], ["freshness", "신선도순"]];

// 오퍼 유형(제품만이 아님) — 필터·배지·CTA
const OFFER_TYPES: [string, string][] = [
  ["", "전체"], ["physical_product", "🛍 상품"], ["digital_product", "💾 디지털"],
  ["app_install", "📱 앱설치"], ["subscription", "🔄 구독"], ["service", "🧾 서비스"],
  ["lead", "✍ 리드"], ["coupon", "🎟 쿠폰"],
];
const TYPE_BADGE: Record<string, string> = {
  physical_product: "상품", digital_product: "디지털", app_install: "앱설치",
  subscription: "구독", service: "서비스", lead: "리드", coupon: "쿠폰",
};
const TYPE_CTA: Record<string, string> = {
  physical_product: "구매하기", digital_product: "받기", app_install: "설치하기",
  subscription: "무료체험", service: "신청하기", lead: "신청하기", coupon: "쿠폰받기",
};
const TYPE_ICON: Record<string, string> = {
  physical_product: "🛍", digital_product: "💾", app_install: "📱",
  subscription: "🔄", service: "🧾", lead: "✍", coupon: "🎟",
};
const PER_LABEL: Record<string, string> = {
  app_install: "설치당", lead: "리드당", service: "건당", subscription: "월",
};

function price(o: Offer): string {
  if (o.price.krw) return "₩" + Math.round(Number(o.price.krw)).toLocaleString("ko-KR");
  if (o.price.amount) return `${o.price.currency ?? ""} ${Number(o.price.amount).toLocaleString()}`;
  return "";
}

// 유형별 핵심 값: 가격형은 가격(구독은 /월), 성과형은 건당 적립액
function valueOf(o: Offer): string {
  const p = price(o);
  if (o.commission_kind === "fixed" && o.commission_fixed?.amount) {
    const krw = o.commission_fixed.currency === "KRW"
      ? Number(o.commission_fixed.amount)
      : Number(o.commission_fixed.krw ?? o.commission_fixed.amount);
    return `${PER_LABEL[o.offer_type] ?? "건당"} ₩${Math.round(krw).toLocaleString("ko-KR")}`;
  }
  if (p && o.offer_type === "subscription") return `${p}/월`;
  return p || "무료";
}

export function LandingProducts({ onRequireLogin }: { onRequireLogin: () => void }) {
  const [offers, setOffers] = useState<Offer[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<Category[]>([]);
  const [cat, setCat] = useState<string | undefined>(undefined);
  const [otype, setOtype] = useState<string>("");
  const [sort, setSort] = useState("score");
  const [view, setView] = useState<"card" | "list">("card");
  const [loading, setLoading] = useState(true);
  const [basketN, setBasketN] = useState(getBasket().length);

  useEffect(() => { api.categories().then(setCategories).catch(() => {}); }, []);
  useEffect(() => {
    const h = () => setBasketN(getBasket().length);
    window.addEventListener("basket-change", h);
    return () => window.removeEventListener("basket-change", h);
  }, []);

  useEffect(() => {
    setLoading(true);
    api.offers({ sort, page: 1, size: 12, category: cat, offer_type: otype || undefined })
      .then((r) => { setOffers(r.data); setTotal(r.total); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [cat, sort, otype]);

  const add = (e: React.MouseEvent, o: Offer) => {
    e.stopPropagation();
    toggleBasket({ id: o.id, title: o.title, thumbnail_url: o.thumbnail_url });
    setBasketN(getBasket().length);
  };

  return (
    <section className="lsec">
      <h2>지금 수집된 광고상품</h2>
      <p className="muted" style={{ textAlign: "center", marginTop: -14, marginBottom: 14 }}>
        총 {total.toLocaleString("ko-KR")}건 집계 중 · 상품뿐 아니라 디지털·앱·구독·리드·쿠폰까지 · 담아두면 가입 후 내 사이트에 자동 반영됩니다
      </p>

      <div className="lp-types">
        {OFFER_TYPES.map(([v, l]) => (
          <button key={v} className={`lp-type-tab ${otype === v ? "on" : ""}`}
                  onClick={() => setOtype(v)}>{l}</button>
        ))}
      </div>

      <div className="lp-controls">
        <div className="lp-cats">
          <button className={`chip ${!cat ? "chip-on" : ""}`} onClick={() => setCat(undefined)}>전체</button>
          {categories.filter((c) => !c.slug.includes(".")).map((c) => (
            <button key={c.slug} className={`chip ${cat === c.slug ? "chip-on" : ""}`}
                    onClick={() => setCat(cat === c.slug ? undefined : c.slug)}>
              {c.name_ko ?? c.slug}
            </button>
          ))}
        </div>
        <div className="lp-right-ctrls">
          <div className="lp-view" role="group" aria-label="보기 방식">
            <button className={view === "card" ? "on" : ""} onClick={() => setView("card")}
                    title="카드형">▦</button>
            <button className={view === "list" ? "on" : ""} onClick={() => setView("list")}
                    title="가로 리스트형">☰</button>
          </div>
          <select className="lp-sort" value={sort} onChange={(e) => setSort(e.target.value)}>
            {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      </div>

      {loading ? (
        <div className={view === "list" ? "lp-list" : "lp-grid"}>
          {Array.from({ length: 8 }).map((_, i) => (view === "list"
            ? <div className="lp-row" key={i}><div className="lp-row-thumb lp-thumb-ph" /><div className="lp-row-main"><div className="skel" style={{ width: "55%" }} /></div></div>
            : <div className="lp-card" key={i}><div className="lp-thumb-ph" /><div className="lp-body"><div className="skel" style={{ width: "80%" }} /></div></div>))}
        </div>
      ) : offers.length === 0 ? (
        <div className="empty">이 카테고리에 표시할 상품이 없습니다.</div>
      ) : (
        <div className={view === "list" ? "lp-list" : "lp-grid"}>
          {offers.map((o) => {
            const picked = inBasket(o.id);
            const thumb = o.thumbnail_url
              ? <img src={o.thumbnail_url} onError={onImgError} alt="" loading="lazy" />
              : <div className="lp-thumb-ph" data-type={o.offer_type}>{TYPE_ICON[o.offer_type] ?? "🔗"}</div>;
            const badge = <span className={`lp-type-badge t-${o.offer_type}`}>{TYPE_BADGE[o.offer_type] ?? "오퍼"}</span>;
            const pick = (
              <button className={`lp-pick ${picked ? "on" : ""}`} onClick={(e) => add(e, o)}
                      title={picked ? "담기 취소" : "담아두기"}>{picked ? "✓ 담김" : "＋ 담기"}</button>
            );
            if (view === "list") {
              return (
                <div className={`lp-row lp-clickable ${picked ? "picked" : ""}`} key={o.id}
                     onClick={onRequireLogin} title="로그인하고 내 사이트에 담기">
                  <div className="lp-row-thumb">{thumb}{badge}</div>
                  <div className="lp-row-main">
                    <div className="lp-title">{o.title}</div>
                    <div className="lp-sub">
                      <span className="muted">{o.network_name}</span>
                      {o.score.segment && <span className="lp-seg">{SEG_LABEL[o.score.segment]}</span>}
                      {o.is_sample && <span className="lp-sample-inline">샘플</span>}
                    </div>
                  </div>
                  <div className="lp-row-right">
                    <span className="lp-price">{valueOf(o)}</span>
                    <span className="lp-cta-hint">{TYPE_CTA[o.offer_type] ?? "보러가기"}</span>
                    {pick}
                  </div>
                </div>
              );
            }
            return (
              <div className={`lp-card lp-clickable ${picked ? "picked" : ""}`} key={o.id}
                   onClick={onRequireLogin} title="로그인하고 내 사이트에 담기">
                <div className="lp-thumb-wrap">
                  {thumb}
                  {badge}
                  {o.is_sample && <span className="lp-sample" title="API 연동 시 실데이터로 대체">샘플</span>}
                  {pick}
                </div>
                <div className="lp-body">
                  <div className="lp-title">{o.title}</div>
                  <div className="lp-meta">
                    <span className="lp-price">{valueOf(o)}</span>
                    {o.score.segment && <span className="lp-seg">{SEG_LABEL[o.score.segment]}</span>}
                  </div>
                  <div className="lp-sub">
                    <span className="muted">{o.network_name}</span>
                    <span className="lp-cta-hint">{TYPE_CTA[o.offer_type] ?? "보러가기"}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {basketN > 0 && (
        <div className="basket-bar">
          🛒 담은 상품 <b>{basketN}</b>개 — 가입하면 이 상품들로 내 링크 포탈이 만들어집니다
          <button onClick={onRequireLogin}>가입하고 내 사이트 만들기 →</button>
        </div>
      )}
    </section>
  );
}
