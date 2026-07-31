import { useEffect, useState } from "react";
import { memberApi } from "../auth";

const KIND_META: Record<string, { emoji: string; label: string; desc: string }> = {
  shopping: { emoji: "🛒", label: "쇼핑형", desc: "카드 그리드 쇼핑몰 · 상품 상세·구매" },
  deal: { emoji: "⚡", label: "핫딜형", desc: "마감임박 타임특가 · 할인율 강조" },
  ranking: { emoji: "🏅", label: "랭킹형", desc: "에디터 베스트 순위·비교 리뷰" },
  boutique: { emoji: "🕊️", label: "감성 셀렉트샵", desc: "룩북·에디토리얼 감성몰" },
  search: { emoji: "🔍", label: "검색형", desc: "검색 중심 포탈 · 실시간 검색" },
  directory: { emoji: "📊", label: "가격비교형", desc: "다나와식 최저가 비교 표" },
  coupon: { emoji: "🎟️", label: "쿠폰형", desc: "쿠폰·프로모코드 혜택 모음" },
  blog: { emoji: "✍️", label: "리뷰 블로그형", desc: "직접 써본 후기 블로그" },
  article: { emoji: "📰", label: "기사형", desc: "매거진·리뷰 콘텐츠" },
  enterprise: { emoji: "🏢", label: "기업형", desc: "프리미엄 브랜드몰" },
  general: { emoji: "📄", label: "일반형", desc: "심플 링크 리스트" },
  mixed: { emoji: "🧩", label: "혼합형", desc: "검색+쇼핑+기사 허브" },
  google_ads: { emoji: "🅖", label: "구글광고 전용", desc: "고전환 랜딩·GA4·전환추적·리마케팅" },
};

export function BuilderShowcase() {
  const [sites, setSites] = useState<{ kind: string; slug: string; title: string }[]>([]);
  useEffect(() => { memberApi.showcase().then(setSites).catch(() => {}); }, []);

  if (sites.length === 0) return null;

  return (
    <section className="lsec">
      <h2>실제 빌더 사이트 미리보기</h2>
      <p className="muted" style={{ textAlign: "center", marginTop: -14, marginBottom: 24 }}>
        완성된 <b>{sites.length}가지</b> 스타일을 직접 확인하세요. 클릭하면 실제 사이트가 열립니다.
      </p>
      <div className="showcase-grid">
        {sites.map((s) => {
          const m = KIND_META[s.kind] ?? { emoji: "🧱", label: s.kind, desc: "" };
          const url = `/site/${encodeURIComponent(s.slug)}`;
          return (
            <a className="showcase-card" href={url} key={s.slug}>
              <div className="showcase-preview">
                <iframe src={url} title={s.title} loading="lazy" scrolling="no" tabIndex={-1} />
                <div className="showcase-overlay"><span>미리보기 →</span></div>
              </div>
              <div className="showcase-info">
                <div className="showcase-label">{m.emoji} {m.label}</div>
                <div className="showcase-title">{s.title}</div>
                <div className="showcase-desc">{m.desc}</div>
              </div>
            </a>
          );
        })}
      </div>
    </section>
  );
}
