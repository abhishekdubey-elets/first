// Shared TypeScript interfaces matching docs/API.md

export type TransferStatus =
  | 'pending'
  | 'verified'
  | 'conflicted'
  | 'exported'
  | 'export_failed';

export interface Transfer {
  id: string;
  officer_name: string;
  ias_batch: string;
  cadre: string;
  state: string;
  current_designation: string;
  previous_district: string;
  previous_posting: string;
  new_district: string;
  new_posting: string;
  transfer_date: string;
  effective_date: string;
  news_date: string | null;
  reason: string;
  notification_number: string;
  gov_order_link: string;
  source_name: string;
  source_url: string;
  corroborating_sources: string[];
  discrepancies: Record<string, unknown>[];
  status: TransferStatus;
  created_at: string;
  updated_at: string;
}

export type ArticleStatus =
  | 'discovered'
  | 'extracted'
  | 'parsed'
  | 'irrelevant'
  | 'failed';

export interface Article {
  id: string;
  url: string;
  title: string;
  source_name: string;
  language: string;
  published_at: string;
  status: ArticleStatus;
  relevance_score: number;
  created_at: string;
}

export interface CountByKey {
  count: number;
  [key: string]: string | number;
}

export interface ByState {
  state: string;
  count: number;
}

export interface ByCadre {
  cadre: string;
  count: number;
}

export interface ByDistrict {
  district: string;
  count: number;
}

export interface ByMonth {
  month: string;
  count: number;
}

export interface Stats {
  total_transfers: number;
  today: number;
  this_week: number;
  this_month: number;
  pending: number;
  verified: number;
  exported: number;
  by_state: ByState[];
}

export interface Analytics {
  by_state: ByState[];
  by_cadre: ByCadre[];
  by_district: ByDistrict[];
  by_month: ByMonth[];
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface SyncStatus {
  last_sync: string | null;
  last_status: string | null;
  exported_rows: number;
  failed_uploads: number;
  sheet: {
    connected: boolean;
    total_rows: number;
    error: string | null;
  };
}

export interface SyncLog {
  id: string;
  status: string;
  rows_written: number;
  rows_failed: number;
  message: string;
  created_at: string;
}

export interface Settings {
  spreadsheet_id: string;
  worksheet_name: string;
  auto_export: boolean;
  credentials_uploaded: boolean;
  llm_provider: string;
  llm_model: string;
  discovery_interval_seconds: number;
  openai_configured: boolean;
}

export interface ProviderModel {
  id: string;
  label: string;
  available: boolean;
  model: string;
}

export interface ModelsResponse {
  providers: ProviderModel[];
  active: string;
}

export interface TransfersQuery {
  page?: number;
  page_size?: number;
  q?: string;
  state?: string;
  district?: string;
  officer?: string;
  batch?: string;
  cadre?: string;
  source?: string;
  status?: string;
  sort?: 'news_date' | 'created_at' | 'transfer_date' | 'officer';
  order?: 'asc' | 'desc';
}

export interface ChatSource {
  id: number;
  officer_name: string;
  state?: string | null;
  previous_district?: string | null;
  previous_posting?: string | null;
  new_district?: string | null;
  new_posting?: string | null;
  transfer_date?: string | null;
  source_name?: string | null;
  source_url?: string | null;
}

export interface WebSource {
  title: string;
  url: string;
  source?: string | null;
  published?: string | null;
}

export interface ChatAnswer {
  answer: string;
  sources: ChatSource[];
  web_sources?: WebSource[];
  from_web?: boolean;
}

export interface NewsQuery {
  page?: number;
  page_size?: number;
  status?: string;
}
