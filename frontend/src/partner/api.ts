/** 파트너 대시보드 API — 파트너 세션 토큰으로 '자기 데이터만' 조회한다. */

const BASE = "/api/v1/growth";
const TOKEN_KEY = "tb_partner_token";

export function getPartnerToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setPartnerToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearPartnerToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function get<T>(path: string): Promise<T> {
  const token = getPartnerToken();
  const res = await fetch(BASE + path, {
    headers: token ? { "X-Partner-Token": token } : {},
  });
  if (!res.ok) {
    if (res.status === 401) clearPartnerToken();
    throw new Error(`${res.status}`);
  }
  return (await res.json()) as T;
}

export type PartnerProfile = {
  id: number;
  display_name: string;
  kind: string;
  tier: string;
  depth: number;
  created_at: string;
  reach_score: number | null;
  engagement_score: number | null;
  conversion_score: number | null;
  composite_score: number | null;
  fraud_score: number | null;
};

export type DayPoint = {
  day: string;
  clicks: number;
  unique_visitors: number;
  conversions: number;
  revenue_krw: string;
  epc_krw: string | null;
  cvr: string | null;
};

export type Settlement = {
  period_start: string;
  period_end: string;
  gross_krw: string;
  share_krw: string;
  override_krw: string;
  holdback_krw: string;
  payable_krw: string;
  status: string;
};

export type ChildPartner = {
  id: number;
  display_name: string;
  kind: string;
  tier: string;
  clicks: number;
  revenue_krw: string;
};

export type PartnerMe = {
  profile: PartnerProfile | null;
  totals: {
    clicks: number; conversions: number; revenue_krw: string;
    cvr: number; epc_krw: number;
  };
  series: DayPoint[];
  settlements: Settlement[];
  children: ChildPartner[];
  unpaid_krw: string;
};

export const partnerApi = {
  me: (days = 30) => get<PartnerMe>(`/me?days=${days}`),
};

/** 등급 표시 정보 — 색상은 CSS 변수로 매핑된다. */
export const TIER_META: Record<string, { label: string; rank: number }> = {
  bronze: { label: "브론즈", rank: 1 },
  silver: { label: "실버", rank: 2 },
  gold: { label: "골드", rank: 3 },
  platinum: { label: "플래티넘", rank: 4 },
  diamond: { label: "다이아몬드", rank: 5 },
};

export const KIND_LABEL: Record<string, string> = {
  house: "플랫폼",
  agency: "에이전시",
  partner: "파트너",
  influencer: "인플루언서",
};

/** 등급별 기본 수익 배분율(계약이 없을 때 적용되는 값) — service.py 와 동일. */
export const TIER_SHARE: Record<string, number> = {
  bronze: 0.50, silver: 0.60, gold: 0.70, platinum: 0.78, diamond: 0.85,
};

export function krw(value: string | number | null | undefined): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return "0";
  return Math.round(n).toLocaleString("ko-KR");
}

export function pct(value: number | string | null | undefined, digits = 2): string {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : "0%";
}
