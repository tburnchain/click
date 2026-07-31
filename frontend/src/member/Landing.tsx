import { useEffect, useState } from "react";
import { AuthModal } from "./AuthModal";
import { Logo } from "../Logo";
import { LandingProducts } from "./LandingProducts";
import { BuilderShowcase } from "./BuilderShowcase";

const BUILDERS = [
  { emoji: "🛒", name: "쇼핑형", desc: "카드 그리드 쇼핑몰" },
  { emoji: "⚡", name: "핫딜형", desc: "마감임박 타임특가" },
  { emoji: "🏅", name: "랭킹형", desc: "베스트 순위·리뷰" },
  { emoji: "🕊️", name: "감성 셀렉트샵", desc: "룩북·에디토리얼" },
  { emoji: "🔍", name: "검색형", desc: "검색 중심 포탈" },
  { emoji: "📊", name: "가격비교형", desc: "최저가 비교 표" },
  { emoji: "🎟️", name: "쿠폰형", desc: "쿠폰·프로모 혜택" },
  { emoji: "✍️", name: "리뷰 블로그형", desc: "직접 써본 후기" },
  { emoji: "📰", name: "기사형", desc: "매거진 콘텐츠" },
  { emoji: "🏢", name: "기업형", desc: "브랜드 고급 몰" },
  { emoji: "🅖", name: "구글광고 전용", desc: "고전환 랜딩·전환추적" },
];

export function Landing({ onAuthed }: { onAuthed: () => void }) {
  const [auth, setAuth] = useState<{ mode: "login" | "signup" } | null>(null);
  const [refCode, setRefCode] = useState<string | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const ref = q.get("ref");
    if (ref) localStorage.setItem("gamdap_ref", ref);
    setRefCode(ref || localStorage.getItem("gamdap_ref"));
    const a = q.get("auth");
    if (a === "login" || a === "signup") setAuth({ mode: a });
  }, []);

  const open = (mode: "login" | "signup") => setAuth({ mode });

  return (
    <div className="landing">
      <nav className="lnav">
        <div className="lnav-logo"><Logo size={28} /></div>
        <button className="lnav-login" onClick={() => open("login")}>로그인 / 가입</button>
      </nav>

      <section className="hero">
        <h1>전 세계 제휴상품을<br /><span>내 제휴코드로</span> 수익화</h1>
        <p>제휴 API만 연결하면, 수집된 방대한 상품 데이터로 나만의 링크 포탈을<br />
          클릭 몇 번에 만들어 홍보·수익화합니다.</p>
        <button className="hero-cta" onClick={() => open("signup")}>무료로 시작하기 →</button>
        <div className="hero-flow">
          가입 → 제휴 API 연결 → 빌더 선택 → 내 코드 자동 주입 → 홍보 → 수익
        </div>
      </section>

      <section className="lsec">
        <h2>다양한 링크 포탈 빌더</h2>
        <div className="builder-showcase">
          {BUILDERS.map((b) => (
            <div className="bshow" key={b.name}>
              <span className="bshow-emoji">{b.emoji}</span>
              <div className="bshow-name">{b.name}</div>
              <div className="bshow-desc">{b.desc}</div>
            </div>
          ))}
        </div>
        <p className="muted" style={{ textAlign: "center" }}>
          빌더는 복잡도에 따라 포인트가 책정됩니다. 구독 포인트로 원하는 빌더를 내 사이트로 만드세요.
        </p>
      </section>

      <BuilderShowcase />

      <LandingProducts onRequireLogin={() => open("signup")} />

      <footer className="lfoot">TBURN.CLICK · 글로벌 제휴마케팅 링크 포탈 빌더</footer>

      {auth && <AuthModal initialMode={auth.mode} refCode={refCode} onClose={() => setAuth(null)} onAuthed={onAuthed} />}
    </div>
  );
}
