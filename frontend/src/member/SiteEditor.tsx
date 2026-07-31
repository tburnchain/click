import { useEffect, useMemo, useState } from "react";
import { thumb, onImgError } from "../img";
import { memberApi, type EditableSite } from "../auth";
import { api } from "../api";
import type { Category, Offer } from "../types";

export function SiteEditor({ siteId, onClose, onSaved }: {
  siteId: number; onClose: () => void; onSaved: () => void;
}) {
  const [site, setSite] = useState<EditableSite | null>(null);
  const [title, setTitle] = useState("");
  const [biz, setBiz] = useState("");
  const [intro, setIntro] = useState("");
  const [heroTitle, setHeroTitle] = useState("");
  const [heroSub, setHeroSub] = useState("");
  const [color, setColor] = useState("#ff4d4f");
  const [ga4, setGa4] = useState("");
  const [adsId, setAdsId] = useState("");
  const [adsLabel, setAdsLabel] = useState("");
  const [adsenseClient, setAdsenseClient] = useState("");
  const [adsenseSlot, setAdsenseSlot] = useState("");
  const [mode, setMode] = useState<"filter" | "manual">("filter");
  const [fCategory, setFCategory] = useState("");
  const [fSegment, setFSegment] = useState("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [pq, setPq] = useState("");
  const [results, setResults] = useState<Offer[]>([]);
  const [previewKey, setPreviewKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => { api.categories().then(setCategories).catch(() => {}); }, []);

  useEffect(() => {
    memberApi.getSite(siteId).then((s) => {
      setSite(s);
      setTitle(s.title);
      setBiz(s.owner_info?.["상호"] ?? "");
      setIntro(s.owner_info?.["소개"] ?? "");
      setHeroTitle(s.config?.hero_title ?? "");
      setHeroSub(s.config?.hero_subtitle ?? "");
      setColor(s.config?.primary_color ?? "#ff4d4f");
      setGa4(s.config?.ga4_id ?? "");
      setAdsId(s.config?.ads_conversion_id ?? "");
      setAdsLabel(s.config?.ads_conversion_label ?? "");
      setAdsenseClient(s.config?.adsense_client ?? "");
      setAdsenseSlot(s.config?.adsense_slot ?? "");
      const ids = (s.filter?.offer_ids as number[] | undefined) ?? [];
      if (ids.length) { setMode("manual"); setSelectedIds(ids); }
      else {
        setMode("filter");
        setFCategory((s.filter?.category as string) ?? "");
        setFSegment((s.filter?.segment as string) ?? "");
      }
    }).catch(() => setMsg("사이트를 불러올 수 없습니다"));
  }, [siteId]);

  // 상품 검색(직접 선택 모드)
  useEffect(() => {
    if (mode !== "manual") return;
    const t = setTimeout(() => {
      api.offers({ sort: "score", page: 1, size: 24, q: pq || undefined })
        .then((r) => setResults(r.data)).catch(() => {});
    }, 250);
    return () => clearTimeout(t);
  }, [pq, mode]);

  const toggle = (id: number) =>
    setSelectedIds((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const save = async () => {
    setSaving(true); setMsg(null);
    try {
      const filter = mode === "manual"
        ? { offer_ids: selectedIds }
        : { ...(fCategory ? { category: fCategory } : {}), ...(fSegment ? { segment: fSegment } : {}),
            ...(site?.filter?.network ? { network: site.filter.network } : {}) };
      await memberApi.updateSite(siteId, {
        title,
        owner_info: { 상호: biz, 소개: intro },
        config: {
          hero_title: heroTitle, hero_subtitle: heroSub, primary_color: color,
          ga4_id: ga4.trim(), ads_conversion_id: adsId.trim(), ads_conversion_label: adsLabel.trim(),
          adsense_client: adsenseClient.trim(), adsense_slot: adsenseSlot.trim(),
        },
        filter,
      });
      setMsg("✅ 저장되었습니다");
      setPreviewKey((k) => k + 1);
      onSaved();
    } catch (e) { setMsg("저장 실패: " + String(e instanceof Error ? e.message : e)); }
    finally { setSaving(false); }
  };

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  if (!site) return (<><div className="drawer-scrim" onClick={onClose} /><div className="editor"><div className="pub-empty">불러오는 중…</div></div></>);

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <div className="editor">
        <div className="editor-head">
          <div><h2>사이트 수정 — {site.builder_name}</h2><span className="muted">/site/{site.slug}</span></div>
          <button className="drawer-x" onClick={onClose}>✕</button>
        </div>

        <div className="editor-body">
          <div className="editor-form">
            <label>사이트 이름</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} />

            <div className="editor-row2">
              <div><label>상호</label><input value={biz} onChange={(e) => setBiz(e.target.value)} /></div>
              <div><label>대표 색상</label><input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="editor-color" /></div>
            </div>

            <label>소개 문구</label>
            <input value={intro} onChange={(e) => setIntro(e.target.value)} placeholder="예: 엄선된 인기상품 셀렉트샵" />

            <label>히어로 제목</label>
            <input value={heroTitle} onChange={(e) => setHeroTitle(e.target.value)} placeholder="예: 이번 주 특가 모음전" />
            <label>히어로 부제</label>
            <input value={heroSub} onChange={(e) => setHeroSub(e.target.value)} placeholder="예: 최대 50% 할인" />

            <label>노출 상품</label>
            <div className="editor-mode">
              <button className={mode === "filter" ? "on" : ""} onClick={() => setMode("filter")}>필터 자동</button>
              <button className={mode === "manual" ? "on" : ""} onClick={() => setMode("manual")}>직접 선택 ({selectedIds.length})</button>
            </div>

            {mode === "filter" ? (
              <div className="editor-row2">
                <div><label>카테고리</label>
                  <select value={fCategory} onChange={(e) => setFCategory(e.target.value)}>
                    <option value="">전체</option>
                    {categories.map((c) => <option key={c.slug} value={c.slug}>{c.name_ko ?? c.slug}</option>)}
                  </select>
                </div>
                <div><label>세그먼트</label>
                  <select value={fSegment} onChange={(e) => setFSegment(e.target.value)}>
                    <option value="">전체</option>
                    <option value="goldmine">🟢 금맥</option><option value="rising">🔵 신흥</option>
                    <option value="cashcow">🟡 안정</option>
                  </select>
                </div>
              </div>
            ) : (
              <div className="editor-picker">
                <input placeholder="상품 검색해서 추가…" value={pq} onChange={(e) => setPq(e.target.value)} />
                <div className="editor-picklist">
                  {results.map((o) => (
                    <div className={`editor-pick ${selectedSet.has(o.id) ? "on" : ""}`} key={o.id} onClick={() => toggle(o.id)}>
                      <img src={thumb(o.thumbnail_url)} onError={onImgError} alt="" />
                      <span className="editor-pick-title">{o.title}</span>
                      <span className="editor-pick-add">{selectedSet.has(o.id) ? "✓" : "＋"}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <label style={{ marginTop: 18 }}>🅖 구글광고 추적 (Google Ads 패키지)</label>
            <div className="gads-fields">
              <input value={ga4} onChange={(e) => setGa4(e.target.value)} placeholder="GA4 측정 ID (G-XXXXXXXXXX)" />
              <div className="editor-row2">
                <input value={adsId} onChange={(e) => setAdsId(e.target.value)} placeholder="전환 ID (AW-XXXXXXXXX)" />
                <input value={adsLabel} onChange={(e) => setAdsLabel(e.target.value)} placeholder="전환 라벨" />
              </div>
              <div className="editor-hint2">입력 시 랜딩·익스포트에 gtag·전환추적·리마케팅·gclid/UTM 캡처가 자동 적용됩니다.</div>
            </div>

            <label style={{ marginTop: 16 }}>📢 구글 애드센스 광고 배치 (좌·우·중앙·하단)</label>
            <div className="gads-fields">
              <input value={adsenseClient} onChange={(e) => setAdsenseClient(e.target.value)} placeholder="게시자 ID (ca-pub-XXXXXXXXXXXXXXXX)" />
              <input value={adsenseSlot} onChange={(e) => setAdsenseSlot(e.target.value)} placeholder="광고 슬롯 ID (선택)" />
              <div className="editor-hint2">구글광고 전용 랜딩에 좌측·우측·중앙·하단 AdSense 광고가 배치됩니다. 실제 광고는 승인된 배포 도메인에서 노출됩니다.</div>
            </div>

            {msg && <div className="editor-msg">{msg}</div>}
            <button className="editor-save" onClick={save} disabled={saving}>{saving ? "저장 중…" : "저장하고 반영"}</button>
          </div>

          <div className="editor-preview">
            <div className="editor-preview-bar">실시간 미리보기</div>
            <iframe key={previewKey} src={`/site/${encodeURIComponent(site.slug)}`} title="preview" />
          </div>
        </div>
      </div>
    </>
  );
}
