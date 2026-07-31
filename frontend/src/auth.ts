// 회원 인증 토큰 관리 + 회원 API
const TOKEN_KEY = "gamdap_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string) {
  localStorage.setItem(TOKEN_KEY, t);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

const BASE = "/api/v1";

async function req<T>(path: string, method = "GET", body?: unknown, auth = true): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (auth && token) headers["X-Member-Token"] = token;
  const res = await fetch(BASE + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch { /* noop */ }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export interface Plan {
  code: string; display_name: string; price_monthly_usd: number;
  tier: string; monthly_points: number; entitlements: Record<string, unknown>;
}
export interface Me {
  email: string; display_name: string | null; plan: string; tier: string; points: number;
  referral_code: string | null; referral_count: number; referral_points: number;
}
export interface Builder {
  id: number; code: string; name: string; kind: string;
  point_cost: number; complexity: number; description: string;
}
export interface AffiliateAccount {
  id: number; network_code: string; network_name: string;
  tracking: Record<string, string>; has_secret: boolean; status: string;
}
export interface MemberSite {
  id: number; slug: string; title: string; status: string;
  views: number; clicks: number; points_spent: number; builder_name: string; kind: string;
}
export interface PubProduct {
  id: number; title: string; thumbnail_url: string | null; url: string; network: string;
  price_amount: number | null; price_krw: number | null; currency: string | null;
  segment: string | null; brand: string | null; category: string | null;
}
export interface PublicSiteData {
  title: string; kind: string; builder_name: string; owner_info: Record<string, string>;
  site_config: Record<string, string>;
  owner_ref: string | null; affiliate_applied: boolean; product_count: number; products: PubProduct[];
}
export interface SiteExport {
  slug: string; filename: string; title: string; product_count: number;
  html: string; robots_txt: string; sitemap_xml: string; llms_txt: string;
  seo: Record<string, unknown>;
}
export interface EditableSite {
  id: number; slug: string; title: string; owner_info: Record<string, string>;
  filter: Record<string, unknown>; config: Record<string, string>; status: string;
  kind: string; builder_name: string;
}
export interface ProductDetail {
  id: number; store: string; owner_info: Record<string, string>; owner_ref: string | null;
  title: string; brand: string | null; rating: number | null; category: string | null;
  price: number | null; currency: string; thumbnail_url: string | null; network: string;
  stock_status: string | null; buy_url: string | null; affiliate_applied: boolean;
  related: { id: number; title: string; thumbnail_url: string | null;
             price_krw: number | null; price_amount: number | null; currency: string | null }[];
}

export interface NetworkExtraction {
  method: "keyless" | "api" | "feed" | "manual";
  needs_api: boolean; connector_ready: boolean;
  api_name: string | null; credentials: string[]; note: string;
}
export interface NetworkInfo {
  slug: string; name: string; emoji: string; region: string; category: string;
  integration: "api" | "manual"; status: "active" | "pending";
  homepage: string; signup_url: string; connector_code: string | null; tracking_param: string;
  tagline: string; commission: string; approval: string; payout: string;
  referral_url: string | null; note: string | null; cautions: string[];
  extraction: NetworkExtraction;
}
export interface KeylessSource {
  slug: string; name: string; emoji: string; method: string;
  needs_api: boolean; connector_ready: boolean; note: string;
}
export interface NetworkCatalog {
  networks: NetworkInfo[]; keyless_sources: KeylessSource[]; common_cautions: string[];
  summary: { total: number; api: number; manual: number; pending: number; referral: number };
  extraction_summary: { total_networks: number; api: number; feed: number; manual: number;
    connector_ready: number; connector_ready_slugs: string[]; keyless_sources: number };
}

export const memberApi = {
  plans: () => req<Plan[]>("/plans", "GET", undefined, false),
  networksCatalog: () => req<NetworkCatalog>("/affiliate-networks", "GET", undefined, false),
  signup: (b: { email: string; password: string; display_name?: string; plan?: string; ref?: string }) =>
    req<{ token: string; plan: string; referred?: boolean }>("/auth/signup", "POST", b, false),
  subscribe: (plan: string) =>
    req<{ plan: string; tier: string; points: number }>("/me/subscribe", "POST", { plan }),
  login: (b: { email: string; password: string }) =>
    req<{ token: string }>("/auth/login", "POST", b, false),
  me: () => req<Me>("/me"),
  points: () => req<{ balance: number; ledger: { delta: number; balance: number; reason: string; created_at: string }[] }>("/me/points"),
  affiliates: () => req<AffiliateAccount[]>("/me/affiliate-accounts"),
  connectAffiliate: (b: { network_code: string; tracking: Record<string, string>; secret?: string }) =>
    req<{ account_id: number }>("/me/affiliate-accounts", "POST", b),
  builders: () => req<Builder[]>("/builders", "GET", undefined, false),
  showcase: () => req<{ kind: string; slug: string; title: string; builder_name: string }[]>("/showcase", "GET", undefined, false),
  claim: (b: { template_code: string; title: string; affiliate_network_code?: string; filter?: Record<string, unknown>; owner_info?: Record<string, string> }) =>
    req<{ slug: string; points_spent: number; balance: number }>("/builders/claim", "POST", b),
  sites: () => req<MemberSite[]>("/me/sites"),
  getSite: (id: number) => req<EditableSite>(`/me/sites/${id}`),
  exportSite: (id: number, siteUrl?: string) =>
    req<SiteExport>(`/me/sites/${id}/export${siteUrl ? `?site_url=${encodeURIComponent(siteUrl)}` : ""}`),
  exportZip: async (id: number, siteUrl?: string): Promise<Blob> => {
    const token = getToken();
    const res = await fetch(
      `${BASE}/me/sites/${id}/export.zip${siteUrl ? `?site_url=${encodeURIComponent(siteUrl)}` : ""}`,
      { headers: token ? { "X-Member-Token": token } : {} },
    );
    if (!res.ok) throw new Error(`${res.status}`);
    return res.blob();
  },
  updateSite: (id: number, patch: Partial<{ title: string; owner_info: Record<string, string>; filter: Record<string, unknown>; config: Record<string, string>; status: string }>) =>
    req<EditableSite>(`/me/sites/${id}`, "PATCH", patch),
  publicSite: (slug: string, sort = "score") =>
    req<PublicSiteData>(`/site/${slug}?sort=${sort}`, "GET", undefined, false),
  product: (slug: string, id: number) =>
    req<ProductDetail>(`/site/${slug}/product/${id}`, "GET", undefined, false),
};
