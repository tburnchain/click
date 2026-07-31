import { useEffect, useMemo, useState } from "react";
import { memberApi, type SiteExport as SiteExportData } from "../auth";

type Tab = "html" | "robots" | "sitemap" | "llms";
const TABS: [Tab, string, string][] = [
  ["html", "index.html", "text/html"],
  ["robots", "robots.txt", "text/plain"],
  ["sitemap", "sitemap.xml", "application/xml"],
  ["llms", "llms.txt", "text/plain"],
];

// 대시보드에 표시할 SEO/AEO 체크리스트 라벨
const SEO_LABELS: [string, string][] = [
  ["title_tag", "타이틀 태그"], ["meta_description", "메타 설명"], ["canonical", "Canonical"],
  ["open_graph", "Open Graph"], ["twitter_card", "Twitter Card"], ["robots_meta", "robots 메타"],
  ["semantic_html", "시맨틱 HTML"], ["image_alt", "이미지 alt"],
  ["jsonld_website_searchaction", "JSON-LD · SearchAction"],
  ["jsonld_itemlist_product_offer", "JSON-LD · Product/Offer"],
  ["jsonld_organization", "JSON-LD · Organization"], ["jsonld_breadcrumb", "JSON-LD · Breadcrumb"],
  ["jsonld_faqpage", "JSON-LD · FAQPage"], ["jsonld_speakable", "JSON-LD · Speakable"],
  ["multi_page_detail", "다중 페이지(상품 상세)"],
  ["sitemap_xml", "sitemap.xml"], ["robots_txt_ai_bots", "AI 크롤러 허용"], ["llms_txt", "llms.txt(AI 요약)"],
];

export function SiteExport({ siteId, onClose }: { siteId: number; onClose: () => void }) {
  const [data, setData] = useState<SiteExportData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("html");
  const [copied, setCopied] = useState(false);
  const [siteUrl, setSiteUrl] = useState("");
  const [zipping, setZipping] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    memberApi.exportSite(siteId, siteUrl.trim() || undefined).then(setData)
      .catch((e) => setErr(String(e instanceof Error ? e.message : e)));
  }, [siteId, siteUrl]);

  const downloadZip = async () => {
    setZipping(true); setMsg(null);
    try {
      const blob = await memberApi.exportZip(siteId, siteUrl.trim() || undefined);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${data?.slug ?? "site"}.zip`; a.click();
      URL.revokeObjectURL(a.href);
      setMsg("✅ 배포 번들(zip) 다운로드 완료");
    } catch (e) { setMsg("실패: " + String(e instanceof Error ? e.message : e)); }
    finally { setZipping(false); }
  };

  const codeOf = (t: Tab): string =>
    data ? ({ html: data.html, robots: data.robots_txt, sitemap: data.sitemap_xml, llms: data.llms_txt }[t]) : "";
  const nameOf = (t: Tab): string => (t === "html" ? (data?.filename ?? "index.html") : TABS.find((x) => x[0] === t)![1]);

  const download = (t: Tab) => {
    const [, , mime] = TABS.find((x) => x[0] === t)!;
    const blob = new Blob([codeOf(t)], { type: `${mime};charset=utf-8` });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = nameOf(t); a.click();
    URL.revokeObjectURL(a.href);
  };
  const copy = () => {
    navigator.clipboard?.writeText(codeOf(tab));
    setCopied(true); setTimeout(() => setCopied(false), 1500);
  };
  const downloadAll = () => TABS.forEach(([t]) => download(t));

  const seo = data?.seo ?? {};
  const applied = useMemo(() => SEO_LABELS.filter(([k]) => seo[k] === true).length, [seo]);

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <div className="editor">
        <div className="editor-head">
          <div>
            <h2>HTML 코드 공개 — {data?.title ?? "…"}</h2>
            <span className="muted">구매한 사이트를 직접 호스팅·수정할 수 있는 SEO·AI검색 최적화 코드</span>
          </div>
          <button className="drawer-x" onClick={onClose}>✕</button>
        </div>

        <div className="export-body">
          {err && <div className="auth-err" style={{ margin: 16 }}>{err}</div>}
          {!data && !err && <div className="pub-empty">생성 중…</div>}
          {data && (
            <>
              <aside className="export-side">
                <div className="export-badge">✅ SEO·AEO {applied}/{SEO_LABELS.length} 적용</div>
                <ul className="export-checks">
                  {SEO_LABELS.map(([k, label]) => (
                    <li key={k} className={seo[k] === true ? "on" : ""}>
                      {seo[k] === true ? "✓" : "·"} {label}
                    </li>
                  ))}
                </ul>
                <div className="export-note">
                  🤖 AI 검색 허용: {(seo.ai_crawlers_allowed as string[] | undefined)?.join(", ") ?? "-"}
                </div>
                <div className="export-note">
                  📄 총 {String(seo.total_pages ?? data.product_count + 1)}페이지 (메인 + 상품 상세 {data.product_count})
                  · 가격표기 {String(seo.products_with_price ?? 0)}개
                </div>

                <label className="export-lbl">배포 도메인 (선택)</label>
                <input className="export-url" placeholder="https://myshop.com"
                       value={siteUrl} onChange={(e) => setSiteUrl(e.target.value)} />
                <div className="export-hint">canonical·sitemap·robots에 반영됩니다. 비우면 나중에 README 안내대로 교체.</div>

                <button className="editor-save export-zip" onClick={downloadZip} disabled={zipping}>
                  {zipping ? "번들 생성 중…" : "📦 배포 번들(zip) 다운로드"}
                </button>
                <div className="export-hint">Netlify·Vercel·GitHub Pages 배포 가이드(README) 포함</div>
                <button className="export-plain" onClick={downloadAll}>개별 파일만 다운로드</button>
                {msg && <div className="editor-msg">{msg}</div>}
              </aside>

              <div className="export-code">
                <div className="export-tabs">
                  {TABS.map(([t, name]) => (
                    <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{name}</button>
                  ))}
                  <div className="export-actions">
                    <button onClick={copy}>{copied ? "복사됨 ✓" : "복사"}</button>
                    <button onClick={() => download(tab)}>다운로드 ↓</button>
                  </div>
                </div>
                <textarea className="export-src" readOnly value={codeOf(tab)} spellCheck={false} />
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
