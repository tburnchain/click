import { useEffect, useState } from "react";
import { api } from "../api";
import type { Connector, Job } from "../types";

function StatusBadge({ s }: { s: string }) {
  const color =
    s === "success" ? "#16a34a" : s === "partial" ? "#d97706" :
    s === "running" ? "#2563eb" : "#dc2626";
  return <span style={{ color, fontWeight: 600 }}>{s}</span>;
}

export function CrawlManager() {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [network, setNetwork] = useState("opendata");
  const [keyword, setKeyword] = useState("phone");
  const [limit, setLimit] = useState(10);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = () => {
    api.connectors().then(setConnectors).catch(() => {});
    api.jobs(20).then(setJobs).catch(() => {});
  };
  useEffect(refresh, []);

  const run = async () => {
    setRunning(true);
    setMsg(null);
    try {
      const job = await api.triggerIngest(network, keyword, limit);
      setMsg(
        job.status === "success"
          ? `✅ ${job.network_code} 수집 완료 · ${job.fetched}건 수신 (키워드: ${job.keyword ?? "-"})`
          : `⚠️ ${job.network_code} 실패 · ${job.error ?? ""}`,
      );
      refresh();
    } catch (e) {
      setMsg("요청 실패: " + String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      {/* 수집 실행 패널 */}
      <div className="filterbar" style={{ gap: 10 }}>
        <strong style={{ marginRight: 6 }}>수집 실행</strong>
        <select value={network} onChange={(e) => setNetwork(e.target.value)}>
          {connectors.map((c) => (
            <option key={c.code} value={c.code}>
              {c.display_name} {c.configured ? "" : "(키 필요)"}
            </option>
          ))}
        </select>
        <input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="키워드" />
        <input type="number" value={limit} min={1} max={100} style={{ width: 70 }}
               onChange={(e) => setLimit(Number(e.target.value))} />
        <button onClick={run} disabled={running}
                style={{ padding: "6px 14px", borderRadius: 7, background: "var(--accent)",
                         color: "#fff", border: "none", cursor: "pointer" }}>
          {running ? "수집 중…" : "▶ 실행"}
        </button>
        <button onClick={refresh} style={{ padding: "6px 10px", borderRadius: 7,
                background: "transparent", border: "1px solid var(--border)", color: "var(--text)" }}>
          새로고침
        </button>
      </div>
      {msg && <div style={{ margin: "0 0 12px", padding: "8px 12px", borderRadius: 8,
                            background: "var(--panel)", border: "1px solid var(--border)" }}>{msg}</div>}
      <p className="muted" style={{ fontSize: 12, margin: "0 0 12px" }}>
        💡 <b>공개데이터(샌드박스)</b>는 API 키 없이 실제 라이브 수집이 동작합니다. 나머지는 .env 에 자격증명 등록 후 사용.
      </p>

      {/* 커넥터 상태 */}
      <h3 style={{ margin: "8px 0" }}>커넥터 상태</h3>
      <div className="table-wrap" style={{ marginBottom: 20 }}>
        <table>
          <thead>
            <tr><th>네트워크</th><th>어댑터</th><th>소스</th><th>상태</th><th className="num">오퍼 수</th><th>최근 수집</th></tr>
          </thead>
          <tbody>
            {connectors.map((c) => (
              <tr key={c.code}>
                <td>{c.display_name}</td>
                <td className="muted">{c.adapter ?? "—"}</td>
                <td className="muted">{c.data_source}</td>
                <td>{c.healthy
                  ? <span style={{ color: "#16a34a", fontWeight: 600 }}>● 정상</span>
                  : <span className="muted">○ {c.configured ? "오류" : "키 필요"}</span>}</td>
                <td className="num">{c.offer_count.toLocaleString()}</td>
                <td className="muted">{c.last_ingest_at ? new Date(c.last_ingest_at).toLocaleString("ko-KR") : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 수집 작업 이력 */}
      <h3 style={{ margin: "8px 0" }}>수집 작업 이력</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>#</th><th>네트워크</th><th>유형</th><th>키워드</th><th>상태</th>
              <th className="num">수신</th><th className="num">변경</th><th>시각</th><th>오류</th></tr>
          </thead>
          <tbody>
            {jobs.length === 0 && <tr><td colSpan={9} className="empty">작업 이력이 없습니다.</td></tr>}
            {jobs.map((j) => (
              <tr key={j.id}>
                <td className="muted">{j.id}</td>
                <td>{j.network_code}</td>
                <td className="muted">{j.job_type}</td>
                <td className="muted">{j.keyword ?? "—"}</td>
                <td><StatusBadge s={j.status} /></td>
                <td className="num">{j.fetched || j.rows_upserted}</td>
                <td className="num">{j.rows_changed}</td>
                <td className="muted">{j.finished_at ? new Date(j.finished_at).toLocaleTimeString("ko-KR") : "—"}</td>
                <td className="muted" style={{ maxWidth: 220, color: j.error ? "#dc2626" : undefined }}>{j.error ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
