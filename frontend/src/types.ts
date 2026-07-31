export interface Money {
  amount: string | null;
  currency: string | null;
  krw: string | null;
  usd: string | null;
}

export interface Score {
  profitability: number | null;
  epc: number | null;
  demand: number | null;
  competition: number | null;
  segment: string | null;
}

export interface Offer {
  id: number;
  product_id: number | null;
  network_code: string;
  network_name: string;
  title: string;
  thumbnail_url: string | null;
  landing_url: string | null;
  offer_type: string;
  is_sample: boolean;
  price: Money;
  billing_type: string | null;
  commission_kind: string | null;
  commission_rate: string | null;
  commission_fixed: Money | null;
  stock_status: string | null;
  native_rank: number | null;
  data_source: string;
  fetched_at: string;
  score: Score;
}

export interface Facet {
  key: string;
  count: number;
}

export interface OfferList {
  data: Offer[];
  page: number;
  size: number;
  total: number;
  facets?: { network?: Facet[]; segment?: Facet[] };
}

export interface HistoryPoint {
  observed_at: string;
  price_amount: string | null;
  commission_rate: string | null;
  stock_status: string | null;
}

export interface Summary {
  total_offers: number;
  active_networks: number;
  avg_epc: number | null;
  opportunities: number;
  last_ingest_at: string | null;
}

export interface Network {
  code: string;
  display_name: string;
  country: string | null;
  is_active: boolean;
}

export interface Category {
  slug: string;
  name_ko: string | null;
  name_en: string | null;
}

export interface Opportunity {
  id: number;
  offer_id: number;
  title: string;
  network_name: string;
  kind: string;
  severity: string;
  detail: Record<string, unknown>;
  detected_at: string;
}

export interface Connector {
  code: string;
  display_name: string;
  adapter: string | null;
  data_source: string;
  healthy: boolean;
  configured: boolean;
  offer_count: number;
  last_ingest_at: string | null;
}

export interface Job {
  id: number;
  network_code: string;
  job_type: string;
  status: string;
  keyword: string | null;
  rows_upserted: number;
  rows_changed: number;
  fetched: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface Filters {
  network?: string;
  category?: string;
  billing_type?: string;
  offer_type?: string;
  segment?: string;
  min_price?: number;
  max_price?: number;
  q?: string;
  sort: string;
  page: number;
  size: number;
}
