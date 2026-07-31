import { useEffect, useState } from "react";
import { clearToken, memberApi, type AffiliateAccount, type Builder, type Me, type MemberSite, type Plan } from "../auth";
import { clearBasket, getBasket, type BasketItem } from "../basket";
import { SiteEditor } from "./SiteEditor";
import { SiteExport } from "./SiteExport";
import { SignupGuide } from "../components/SignupGuide";

const TIER_FEATURES: Record<string, string[]> = {
  basic: ["네트워크 1개", "사이트 1개", "일일 신선도"],
  pro: ["네트워크 3개", "사이트 5개", "12시간 신선도", "고급 분석"],
  premium: ["전체 네트워크", "사이트 20개", "실시간 신선도", "고급 분석"],
  vip: ["전체 네트워크", "무제한 사이트", "실시간", "우선 지원"],
};

const NETWORKS = [
  { code: "opendata", name: "공개데이터(샌드박스)", param: "ref" },
  { code: "coupang_partners", name: "쿠팡 파트너스", param: "subId" },
  { code: "amazon_assoc", name: "Amazon", param: "tag" },
  { code: "cj_affiliate", name: "CJ Affiliate", param: "sid" },
  { code: "impact", name: "Impact", param: "subId1" },
  { code: "clickbank", name: "ClickBank", param: "tid" },
];

const KIND_EMOJI: Record<string, string> = {
  shopping: "🛒", search: "🔍", general: "📄", enterprise: "🏢", mixed: "🧩", article: "📰",
  deal: "⚡", ranking: "🏅", coupon: "🎟️", boutique: "🕊️", blog: "✍️", directory: "📊",
  google_ads: "🅖",
};

export function MemberDashboard({ onLogout }: { onLogout: () => void }) {
  const [me, setMe] = useState<Me | null>(null);
  const [builders, setBuilders] = useState<Builder[]>([]);
  const [accounts, setAccounts] = useState<AffiliateAccount[]>([]);
  const [sites, setSites] = useState<MemberSite[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  // 제휴 연결 폼
  const [affNet, setAffNet] = useState("opendata");
  const [affCode, setAffCode] = useState("");
  const [basket, setBasket] = useState<BasketItem[]>(getBasket());
  const [editingId, setEditingId] = useState<number | null>(null);
  const [exportingId, setExportingId] = useState<number | null>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [previews, setPreviews] = useState<Record<string, string>>({});  // kind → 대표 사이트 slug

  const reload = () => {
    memberApi.me().then(setMe).catch(() => onLogout());
    memberApi.builders().then(setBuilders).catch(() => {});
    memberApi.affiliates().then(setAccounts).catch(() => {});
    memberApi.sites().then(setSites).catch(() => {});
    memberApi.plans().then(setPlans).catch(() => {});
  };
  useEffect(reload, []);
  useEffect(() => {
    memberApi.showcase()
      .then((rows) => setPreviews(Object.fromEntries(rows.map((r) => [r.kind, r.slug]))))
      .catch(() => {});
  }, []);

  const connect = async () => {
    const net = NETWORKS.find((n) => n.code === affNet)!;
    try {
      await memberApi.connectAffiliate({ network_code: affNet, tracking: { [net.param]: affCode } });
      setMsg(`✅ ${net.name} 제휴코드 연결됨`); setAffCode(""); reload();
    } catch (e) { setMsg("연결 실패: " + String(e instanceof Error ? e.message : e)); }
  };

  const claim = async (b: Builder) => {
    const title = prompt(`"${b.name}" 사이트 제목을 입력하세요`, `내 ${b.name}`);
    if (!title) return;
    const net = accounts[0]?.network_code;
    try {
      const r = await memberApi.claim({
        template_code: b.code, title,
        affiliate_network_code: net,
        filter: net ? { network: net } : {},
      });
      setMsg(`✅ "${title}" 생성! (${r.points_spent}P 차감, 잔액 ${r.balance}P) → /site/${r.slug}`);
      reload();
    } catch (e) { setMsg("클레임 실패: " + String(e instanceof Error ? e.message : e)); }
  };

  const createFromBasket = async (b: Builder) => {
    const ids = basket.map((i) => i.id);
    if (ids.length === 0) return;
    const net = accounts[0]?.network_code;
    try {
      const r = await memberApi.claim({
        template_code: b.code, title: `담아둔 상품 ${ids.length}개`,
        affiliate_network_code: net, filter: { offer_ids: ids },
      });
      clearBasket(); setBasket([]);
      setMsg(`✅ 담아둔 ${ids.length}개 상품으로 "${b.name}" 생성! (${r.points_spent}P 차감) → /site/${r.slug}`);
      reload();
    } catch (e) { setMsg("생성 실패: " + String(e instanceof Error ? e.message : e)); }
  };

  const goSubscribe = () => {
    setMsg("빌더를 만들려면 먼저 구독하세요. 구독하면 포인트가 지급됩니다.");
    document.getElementById("subscribe")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const subscribe = async (planCode: string) => {
    try {
      const r = await memberApi.subscribe(planCode);
      setMsg(`✅ ${planCode.toUpperCase()} 구독 완료! ${r.points.toLocaleString()}P 적립 — 이제 빌더를 만드세요.`);
      reload();
    } catch (e) { setMsg("구독 실패: " + String(e instanceof Error ? e.message : e)); }
  };

  const logout = () => { clearToken(); onLogout(); };

  return (
    <div className="app">
      <div className="header">
        <div className="logo">◆</div>
        <h1>내 대시보드</h1>
        <span className="sub">{me?.email}</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 10, alignItems: "center" }}>
          <span className="points-pill">💎 {me?.points?.toLocaleString() ?? "—"} P</span>
          <span className="tier-pill">{me?.tier?.toUpperCase()}</span>
          <button className="reset-btn" onClick={logout}>로그아웃</button>
        </div>
      </div>

      {msg && <div className="mem-msg">{msg}</div>}

      {/* 리퍼럴(추천 커미션) */}
      {me?.referral_code && (
        <div className="ref-card">
          <div className="ref-info">
            <div>🎁 <b>추천 커미션</b> — 내 사이트 방문자가 가입하면 포인트를 받습니다</div>
            <div className="ref-stat">추천 가입 <b>{me.referral_count}</b>명 · 획득 <b>{me.referral_points.toLocaleString()}</b>P</div>
          </div>
          <div className="ref-link">
            <span className="ref-code">{me.referral_code}</span>
            <input readOnly value={`${location.origin}/?auth=signup&ref=${me.referral_code}`} />
            <button className="btn-primary" onClick={() => {
              navigator.clipboard?.writeText(`${location.origin}/?auth=signup&ref=${me.referral_code}`);
              setMsg("✅ 추천 링크가 복사되었습니다");
            }}>링크 복사</button>
          </div>
        </div>
      )}

      {/* 담아둔 상품 자동 반영 */}
      {basket.length > 0 && (
        <div className="basket-banner">
          <div>🛒 가입 전 담아둔 상품 <b>{basket.length}개</b>가 있습니다. 빌더를 선택해 바로 사이트로 만드세요.</div>
          <div className="basket-thumbs">
            {basket.slice(0, 6).map((i) => i.thumbnail_url
              ? <img key={i.id} src={i.thumbnail_url} alt="" />
              : <div key={i.id} className="basket-ph" />)}
            {basket.length > 6 && <span className="muted">+{basket.length - 6}</span>}
          </div>
          <div className="basket-actions">
            {builders.filter((b) => ["shopping_grid", "search_portal", "general_basic"].includes(b.code)).map((b) => (
              <button key={b.id} className="btn-primary" disabled={(me?.points ?? 0) < b.point_cost}
                      onClick={() => createFromBasket(b)}>
                {b.name} ({b.point_cost}P)
              </button>
            ))}
            <button className="reset-btn" onClick={() => { clearBasket(); setBasket([]); }}>비우기</button>
          </div>
        </div>
      )}

      {/* 1) 제휴 계정 연결 */}
      <section className="mem-card">
        <div className="mem-card-head">
          <h3>① 내 제휴 API 계정 연결</h3>
          <button className="guide-btn" onClick={() => setGuideOpen(true)} title="제휴 네트워크 가입 가이드">
            <span className="guide-btn-ico">📋</span> 제휴사이트 가입 가이드
          </button>
        </div>
        <p className="muted" style={{ fontSize: 13 }}>아직 제휴사이트 계정이 없다면 <b>가입 가이드</b>로 먼저 가입한 뒤, 발급받은 트래킹 코드를 연결하세요. 연결하면 사이트 링크에 자동 주입되어 <b>내 수익</b>이 됩니다.</p>
        <div className="mem-form">
          <select value={affNet} onChange={(e) => setAffNet(e.target.value)}>
            {NETWORKS.map((n) => <option key={n.code} value={n.code}>{n.name} ({n.param})</option>)}
          </select>
          <input placeholder="내 트래킹 코드 (예: myseller-20)" value={affCode} onChange={(e) => setAffCode(e.target.value)} />
          <button className="btn-primary" onClick={connect} disabled={!affCode}>연결</button>
        </div>
        <div className="chips" style={{ marginTop: 10 }}>
          {accounts.map((a) => (
            <span className="chip chip-on" key={a.id}>{a.network_name}: {Object.values(a.tracking)[0]}</span>
          ))}
          {accounts.length === 0 && <span className="muted" style={{ fontSize: 12 }}>연결된 계정 없음</span>}
        </div>
      </section>

      {/* 2) 빌더 갤러리 */}
      <section className="mem-card">
        <h3>② 빌더 선택 (미리보기 · 포인트로 구매)</h3>
        <p className="muted" style={{ fontSize: 13 }}>각 빌더의 실제 사이트 미리보기입니다. 썸네일을 누르면 새 탭에서 전체 화면으로 열립니다.</p>
        <div className="builder-grid">
          {builders.map((b) => {
            const slug = previews[b.kind];
            const url = slug ? `/site/${encodeURIComponent(slug)}` : null;
            return (
            <div className="builder-card" key={b.id}>
              {url ? (
                <a className="builder-preview" href={url} target="_blank" rel="noreferrer" title="실제 사이트 미리보기">
                  <iframe src={url} title={b.name} loading="lazy" scrolling="no" tabIndex={-1} />
                  <span className="builder-preview-badge">{KIND_EMOJI[b.kind] ?? "🧱"} 미리보기 →</span>
                </a>
              ) : (
                <div className="builder-preview builder-preview-empty"><span>{KIND_EMOJI[b.kind] ?? "🧱"}</span></div>
              )}
              <div className="builder-top">
                <span className="builder-name">{b.name}</span>
                <span className="builder-cost">💎 {b.point_cost}P</span>
              </div>
              <div className="builder-desc">{b.description}</div>
              <div className="builder-complexity">복잡도 {"★".repeat(b.complexity)}</div>
              {(me?.points ?? 0) < b.point_cost ? (
                <button className="btn-primary" onClick={goSubscribe}>구독하고 만들기 →</button>
              ) : (
                <button className="btn-primary" onClick={() => claim(b)}>이 빌더로 만들기</button>
              )}
            </div>
            );
          })}
        </div>
      </section>

      {/* 3) 내 사이트 */}
      <section className="mem-card">
        <h3>③ 내 사이트</h3>
        {sites.length === 0 ? (
          <p className="muted" style={{ fontSize: 13 }}>아직 만든 사이트가 없습니다. 위에서 빌더를 선택하세요.</p>
        ) : (
          <div className="table-wrap">
            <table className="offers-table">
              <thead><tr><th>사이트</th><th>빌더</th><th className="num">조회</th><th className="num">차감P</th><th>공개 링크</th><th></th></tr></thead>
              <tbody>
                {sites.map((s) => (
                  <tr key={s.id}>
                    <td>{KIND_EMOJI[s.kind]} {s.title}</td>
                    <td className="muted">{s.builder_name}</td>
                    <td className="num">{s.views}</td>
                    <td className="num">{s.points_spent}</td>
                    <td><a href={`/site/${s.slug}`} target="_blank" rel="noreferrer">/site/{s.slug} ↗</a></td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button className="edit-btn" onClick={() => setEditingId(s.id)}>✎ 수정</button>
                      <button className="edit-btn" onClick={() => setExportingId(s.id)} style={{ marginLeft: 6 }}>⟨/⟩ 코드</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 4) 구독 등급 */}
      <section className="mem-card" id="subscribe">
        <h3>④ 구독 등급 — 빌더 제작은 구독으로</h3>
        <p className="muted" style={{ fontSize: 13 }}>가입은 무료입니다. 빌더를 만들려면 구독하세요. 등급이 높을수록 더 많은 월 포인트와 사이트 한도를 받습니다.</p>
        <div className="pricing" style={{ marginTop: 12 }}>
          {plans.map((p) => {
            const current = me?.tier === p.tier;
            return (
              <div className={`price-card ${current ? "featured" : ""}`} key={p.code}>
                {current && <div className="price-badge">현재 이용 중</div>}
                <div className="price-tier">{p.display_name}</div>
                <div className="price-amt">${p.price_monthly_usd}<small>/월</small></div>
                <div className="price-points">💎 {p.monthly_points.toLocaleString()} P/월</div>
                <ul>{(TIER_FEATURES[p.tier] ?? []).map((f) => <li key={f}>✓ {f}</li>)}</ul>
                <button disabled={current} onClick={() => subscribe(p.code)}
                        style={current ? { opacity: 0.5 } : undefined}>
                  {current ? "이용 중" : "이 등급으로 구독"}
                </button>
              </div>
            );
          })}
        </div>
      </section>

      {editingId !== null && (
        <SiteEditor siteId={editingId} onClose={() => setEditingId(null)}
                    onSaved={reload} />
      )}
      {exportingId !== null && (
        <SiteExport siteId={exportingId} onClose={() => setExportingId(null)} />
      )}
      {guideOpen && <SignupGuide onClose={() => setGuideOpen(false)} />}
    </div>
  );
}
