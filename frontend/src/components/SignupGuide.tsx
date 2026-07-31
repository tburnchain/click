// 제휴 네트워크 가입 가이드 — 백엔드 카탈로그(단일 원천) 기반. 자격증명 미포함.
import { useEffect, useMemo, useState } from "react";
import { memberApi, type NetworkCatalog, type NetworkInfo } from "../auth";

const INTEGRATION_BADGE: Record<string, { label: string; cls: string }> = {
  api: { label: "🟢 API 자동연동", cls: "gnet-b-api" },
  manual: { label: "📋 가이드·수동", cls: "gnet-b-manual" },
};
const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  active: { label: "이용가능", cls: "gnet-s-active" },
  pending: { label: "심사·가입중", cls: "gnet-s-pending" },
};
// 데이터 추출 요구사항
const EXTRACT_LABEL: Record<string, string> = {
  keyless: "🟢 가입·키 불필요", api: "🔑 가입 + API 키", feed: "📄 가입 + 상품피드/API", manual: "✍ 가입 후 링크 수동",
};

export function SignupGuide({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<NetworkCatalog | null>(null);
  const [err, setErr] = useState(false);
  const [cat, setCat] = useState<string>("전체");

  useEffect(() => { memberApi.networksCatalog().then(setData).catch(() => setErr(true)); }, []);

  const cats = useMemo(
    () => ["전체", ...[...new Set((data?.networks ?? []).map((n) => n.category))]],
    [data],
  );
  const shown: NetworkInfo[] = (data?.networks ?? []).filter((n) => cat === "전체" || n.category === cat);

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <div className="guide-modal">
        <div className="guide-head">
          <div>
            <h2>제휴 네트워크 가입 가이드</h2>
            <span className="muted" style={{ fontSize: 13 }}>
              {data
                ? `전 세계 ${data.summary.total}개 네트워크 · API 자동연동 ${data.summary.api} · 심사중 ${data.summary.pending}`
                : "수익화를 시작할 네트워크를 고르고, 주의사항을 확인한 뒤 가입하세요."}
            </span>
          </div>
          <button className="drawer-x" onClick={onClose}>✕</button>
        </div>

        <div className="guide-body">
          {err && <div className="auth-err">카탈로그를 불러올 수 없습니다.</div>}

          {/* 데이터 추출 요구사항 요약 */}
          {data && (
            <div className="gnet-summary">
              <h3>📊 데이터 추출 요구사항 한눈에</h3>
              <div className="gnet-sum-grid">
                <div><b>{data.extraction_summary.connector_ready}</b><span>⚡ 커넥터 구현<br/>(키만 입력→라이브)</span></div>
                <div><b>{data.extraction_summary.api}</b><span>🔑 가입 + API 키</span></div>
                <div><b>{data.extraction_summary.feed}</b><span>📄 가입 + 상품피드</span></div>
                <div><b>{data.extraction_summary.manual}</b><span>✍ 가입 후 링크 수동</span></div>
                <div><b>{data.extraction_summary.keyless_sources}</b><span>🟢 키리스 실원천<br/>(가입·키 불필요)</span></div>
              </div>
              <p className="muted" style={{ fontSize: 12.5, margin: "8px 0 0" }}>
                <b>핵심:</b> 제휴 네트워크는 <b>가입만으로 상품 데이터를 추출할 수 없습니다.</b> 가입은 필수 전제이고,
                카탈로그를 우리 DB로 추출하려면 대부분 <b>API 키/토큰(또는 상품 피드)</b>이 추가로 필요합니다.
                이미 <b>{data.keyless_sources.map((k) => k.name.split("(")[0]).join(", ")}</b>는 키 없이 실데이터를 추출 중입니다.
              </p>
            </div>
          )}

          {/* 공통 주의사항 */}
          {data && (
            <div className="guide-common">
              <h3>⚠️ 공통 주의사항 (먼저 읽으세요)</h3>
              <ul>{data.common_cautions.map((c, i) => <li key={i}>{c}</li>)}</ul>
            </div>
          )}

          {/* 카테고리 필터 */}
          {data && (
            <div className="gnet-cats">
              {cats.map((c) => (
                <button key={c} className={cat === c ? "on" : ""} onClick={() => setCat(c)}>{c}</button>
              ))}
            </div>
          )}

          {/* 네트워크 카드 */}
          <div className="guide-grid">
            {shown.map((n) => {
              const ib = INTEGRATION_BADGE[n.integration];
              const sb = STATUS_BADGE[n.status];
              return (
              <div className="guide-card" key={n.slug}>
                <div className="guide-card-head">
                  <span className="guide-emoji">{n.emoji}</span>
                  <div>
                    <div className="guide-name">{n.name}</div>
                    <div className="muted" style={{ fontSize: 12 }}>{n.region} · {n.category}</div>
                  </div>
                </div>
                <div className="gnet-badges">
                  <span className={`gnet-badge ${ib.cls}`}>{ib.label}</span>
                  <span className={`gnet-badge ${sb.cls}`}>{sb.label}</span>
                  {n.extraction.connector_ready && <span className="gnet-badge gnet-b-ready">⚡ 커넥터 준비됨</span>}
                </div>
                <p className="guide-tagline">{n.tagline}</p>
                <div className="gnet-extract">
                  <b>데이터 추출</b> {EXTRACT_LABEL[n.extraction.method] ?? n.extraction.method}
                  {n.extraction.api_name && <div className="muted">{n.extraction.api_name}</div>}
                  {n.extraction.credentials.length > 0 && (
                    <div className="gnet-creds">필요 키: {n.extraction.credentials.map((c) => <code key={c}>{c}</code>)}</div>
                  )}
                </div>
                <dl className="guide-facts">
                  <div><dt>수수료</dt><dd>{n.commission}</dd></div>
                  <div><dt>승인</dt><dd>{n.approval}</dd></div>
                  <div><dt>정산</dt><dd>{n.payout}</dd></div>
                  <div><dt>트래킹</dt><dd><code>{n.tracking_param}</code> 파라미터로 딥링크 주입</dd></div>
                </dl>
                {n.note && <div className="gnet-note">ℹ️ {n.note}</div>}
                <ul className="guide-cautions">
                  {n.cautions.map((c, i) => <li key={i}>{c}</li>)}
                </ul>
                <div className="gnet-ctas">
                  <a className="guide-cta" href={n.signup_url} target="_blank" rel="noreferrer noopener">가입 페이지 열기 ↗</a>
                  {n.referral_url && (
                    <a className="gnet-ref" href={n.referral_url} target="_blank" rel="noreferrer noopener"
                       title="공개 레퍼럴/초대 링크">🎁 레퍼럴 링크</a>
                  )}
                </div>
              </div>
              );
            })}
          </div>

          <p className="guide-foot muted">
            ※ 로그인 비밀번호는 TBURN.CLICK에 저장되지 않습니다 — 비밀번호 관리자에 보관하고, 발급받은 <b>트래킹 코드만</b> 대시보드 ①에서 연결하세요.
            수수료율·정책은 수시로 변경되니 가입 전 각 네트워크 최신 약관을 확인하세요.
          </p>
        </div>
      </div>
    </>
  );
}
