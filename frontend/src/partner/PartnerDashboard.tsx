/** 파트너 대시보드 — 파트너가 자기 실적·등급·정산·하위 파트너를 확인한다.
 *
 *  운영되는 화면이지 읽는 문서가 아니므로, 요약을 먼저 보이고 상태를 형태로 부호화한다
 *  (등급 칩, 위험 배지, 정산 상태). 숫자는 전부 tabular-nums 로 자리를 맞춘다.
 */

import { useEffect, useState } from "react";
import {
  KIND_LABEL, TIER_META, TIER_SHARE, clearPartnerToken, krw,
  partnerApi, pct, type DayPoint, type PartnerMe,
} from "./api";
import { Symbol } from "../Logo";

const RANGES = [7, 30, 90] as const;

/** 일별 수익 스파크라인. 값이 0뿐이면 그리지 않는다. */
function Spark({ series }: { series: DayPoint[] }) {
  const pts = series.map((d) => Number(d.revenue_krw || 0));
  const max = Math.max(...pts, 0);
  if (!pts.length || max <= 0) {
    return <div className="pd-spark-empty">아직 수익 데이터가 없습니다</div>;
  }
  const w = 100, h = 32;
  const step = pts.length > 1 ? w / (pts.length - 1) : w;
  const path = pts.map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(2)},${(h - (v / max) * h).toFixed(2)}`).join(" ");
  const area = `${path} L${w},${h} L0,${h} Z`;
  const lastX = ((pts.length - 1) * step).toFixed(2);
  const lastY = (h - (pts[pts.length - 1] / max) * h).toFixed(2);
  return (
    <svg className="pd-spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={area} className="pd-spark-area" />
      <path d={path} className="pd-spark-line" />
      <circle cx={lastX} cy={lastY} r="1.8" className="pd-spark-dot" />
    </svg>
  );
}

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  const v = Math.max(0, Math.min(100, Number(value ?? 0)));
  return (
    <div className="pd-score">
      <div className="pd-score-head">
        <span>{label}</span>
        <b>{v.toFixed(1)}</b>
      </div>
      <div className="pd-score-track"><div className="pd-score-fill" style={{ width: `${v}%` }} /></div>
    </div>
  );
}

export function PartnerDashboard({ onLogout }: { onLogout: () => void }) {
  const [days, setDays] = useState<number>(30);
  const [data, setData] = useState<PartnerMe | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setError(null);
    partnerApi.me(days)
      .then((d) => { if (alive) setData(d); })
      .catch(() => { if (alive) setError("세션이 만료되었습니다. 다시 로그인하세요."); });
    return () => { alive = false; };
  }, [days]);

  if (error) {
    return (
      <div className="pd-shell">
        <div className="pd-note">
          {error}
          <button className="pd-btn" onClick={() => { clearPartnerToken(); onLogout(); }}>
            로그인으로
          </button>
        </div>
      </div>
    );
  }
  if (!data) return <div className="pd-shell"><div className="pd-note">불러오는 중…</div></div>;

  const p = data.profile;
  const tier = p?.tier ?? "bronze";
  const tierInfo = TIER_META[tier] ?? TIER_META.bronze;
  const share = TIER_SHARE[tier] ?? 0.5;
  const risk = Number(p?.fraud_score ?? 0);

  return (
    <div className="pd-shell">
      <header className="pd-top">
        <div className="pd-brand"><Symbol size={26} /><span>파트너 센터</span></div>
        <div className="pd-top-right">
          <div className="pd-who">
            <b>{p?.display_name ?? "파트너"}</b>
            <span className="pd-kind">{KIND_LABEL[p?.kind ?? "partner"] ?? "파트너"}</span>
          </div>
          <button className="pd-btn ghost" onClick={() => { clearPartnerToken(); onLogout(); }}>
            로그아웃
          </button>
        </div>
      </header>

      {/* 요약 먼저 — 스캔되는 화면 */}
      <section className="pd-kpis">
        <div className="pd-kpi accent">
          <div className="pd-kpi-label">미지급 잔액</div>
          <div className="pd-kpi-value">₩{krw(data.unpaid_krw)}</div>
          <div className="pd-kpi-sub">정산 확정 시 지급</div>
        </div>
        <div className="pd-kpi">
          <div className="pd-kpi-label">기간 수익</div>
          <div className="pd-kpi-value">₩{krw(data.totals.revenue_krw)}</div>
          <Spark series={data.series} />
        </div>
        <div className="pd-kpi">
          <div className="pd-kpi-label">클릭</div>
          <div className="pd-kpi-value">{Number(data.totals.clicks).toLocaleString("ko-KR")}</div>
          <div className="pd-kpi-sub">전환 {Number(data.totals.conversions).toLocaleString("ko-KR")}건</div>
        </div>
        <div className="pd-kpi">
          <div className="pd-kpi-label">클릭당 수익 · 전환율</div>
          <div className="pd-kpi-value">₩{krw(data.totals.epc_krw)}</div>
          <div className="pd-kpi-sub">CVR {pct(data.totals.cvr)}</div>
        </div>
      </section>

      <div className="pd-rangebar">
        {RANGES.map((r) => (
          <button key={r} className={`pd-range ${days === r ? "on" : ""}`} onClick={() => setDays(r)}>
            {r}일
          </button>
        ))}
      </div>

      <div className="pd-grid">
        {/* 등급 · 점수 */}
        <section className="pd-card">
          <h3>내 등급</h3>
          <div className="pd-tierrow">
            <span className={`pd-tier t-${tier}`}>{tierInfo.label}</span>
            <span className="pd-tiernote">수익 배분 {Math.round(share * 100)}%</span>
          </div>
          <div className="pd-tiersteps">
            {Object.entries(TIER_META)
              .sort((a, b) => a[1].rank - b[1].rank)
              .map(([code, meta]) => (
                <span key={code} className={`pd-step ${meta.rank <= tierInfo.rank ? "on" : ""}`}
                      title={`${meta.label} · 배분 ${Math.round((TIER_SHARE[code] ?? 0) * 100)}%`} />
              ))}
          </div>
          <div className="pd-scores">
            <ScoreBar label="도달" value={p?.reach_score ?? null} />
            <ScoreBar label="참여" value={p?.engagement_score ?? null} />
            <ScoreBar label="전환" value={p?.conversion_score ?? null} />
          </div>
          <div className="pd-composite">
            종합 <b>{Number(p?.composite_score ?? 0).toFixed(1)}</b>
            {risk >= 30 && <span className="pd-risk">위험 신호 {risk.toFixed(0)}</span>}
          </div>
          <p className="pd-hint">
            전환 점수는 표본이 적을수록 보수적으로 계산됩니다. 클릭이 쌓이면 실제 성과에 가까워집니다.
          </p>
        </section>

        {/* 정산 이력 */}
        <section className="pd-card wide">
          <h3>정산 내역</h3>
          {data.settlements.length === 0 ? (
            <p className="pd-empty">아직 정산 기록이 없습니다. 전환이 발생하면 기간별로 생성됩니다.</p>
          ) : (
            <div className="pd-tablewrap">
              <table className="pd-table">
                <thead>
                  <tr>
                    <th>기간</th>
                    <th className="n">귀속</th>
                    <th className="n">내 몫</th>
                    <th className="n">오버라이드</th>
                    <th className="n">보류</th>
                    <th className="n">지급</th>
                    <th>상태</th>
                  </tr>
                </thead>
                <tbody>
                  {data.settlements.map((s) => (
                    <tr key={`${s.period_start}-${s.period_end}`}>
                      <td className="mono">{s.period_start} ~ {s.period_end}</td>
                      <td className="n">{krw(s.gross_krw)}</td>
                      <td className="n">{krw(s.share_krw)}</td>
                      <td className="n">{krw(s.override_krw)}</td>
                      <td className="n muted">{krw(s.holdback_krw)}</td>
                      <td className="n strong">{krw(s.payable_krw)}</td>
                      <td><span className={`pd-badge s-${s.status}`}>{
                        { draft: "산정", confirmed: "확정", paid: "지급완료", void: "취소" }[s.status] ?? s.status
                      }</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="pd-hint">
            보류액은 반품·취소에 대비해 일정 기간 유보되며, 기간이 지나면 자동 해제됩니다.
            지급액이 최소 지급 기준에 미달하면 다음 기수로 이월됩니다.
          </p>
        </section>

        {/* 하위 파트너 */}
        <section className="pd-card wide">
          <h3>내 하위 파트너 <span className="pd-count">{data.children.length}</span></h3>
          {data.children.length === 0 ? (
            <p className="pd-empty">
              하위 파트너를 초대하면 그들의 실적에서 오버라이드 수익이 발생합니다.
            </p>
          ) : (
            <div className="pd-tablewrap">
              <table className="pd-table">
                <thead>
                  <tr>
                    <th>파트너</th><th>유형</th><th>등급</th>
                    <th className="n">클릭</th><th className="n">수익</th>
                  </tr>
                </thead>
                <tbody>
                  {data.children.map((c) => (
                    <tr key={c.id}>
                      <td>{c.display_name}</td>
                      <td className="muted">{KIND_LABEL[c.kind] ?? c.kind}</td>
                      <td><span className={`pd-tier sm t-${c.tier}`}>{TIER_META[c.tier]?.label ?? c.tier}</span></td>
                      <td className="n">{Number(c.clicks).toLocaleString("ko-KR")}</td>
                      <td className="n">{krw(c.revenue_krw)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
