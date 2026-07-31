import type {
  Category, Connector, HistoryPoint, Job, Network, Offer, OfferList, Opportunity, Summary, Filters,
} from "./types";

const BASE = "/api/v1";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

function qs(f: Partial<Filters>): string {
  const p = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  });
  return p.toString();
}

export const api = {
  offers: (f: Filters) => get<OfferList>(`/offers?${qs(f)}`),
  rankings: (category?: string, limit = 50) =>
    get<Offer[]>(`/rankings?${qs({ category, limit } as never)}`),
  offerHistory: (id: number) => get<HistoryPoint[]>(`/offers/${id}/history?limit=60`),
  productOffers: (productId: number) => get<Offer[]>(`/products/${productId}/offers`),
  compare: (productId: number) => get<Offer[]>(`/compare?product_id=${productId}`),
  summary: () => get<Summary>(`/analytics/summary`),
  opportunities: (limit = 50) => get<Opportunity[]>(`/analytics/opportunities?limit=${limit}`),
  networks: () => get<Network[]>(`/meta/networks`),
  categories: () => get<Category[]>(`/meta/categories`),
  connectors: () => get<Connector[]>(`/crawl/connectors`),
  jobs: (limit = 30) => get<Job[]>(`/crawl/jobs?limit=${limit}`),
  triggerIngest: (network: string, keyword: string, limit: number) =>
    post<Job>(`/crawl/ingest`, { network, keyword: keyword || null, limit }),
};
