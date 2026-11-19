// Shared TypeScript interfaces matching docs/API.md

export type TransferStatus =
  | 'pending'
  | 'verified'
  | 'conflicted'
  | 'exported'
  | 'export_failed';

export interface Transfer {
  id: number;
  officer_name: string;
  // Profile id: link to /officers/{officer_id}.
  officer_id: string | null;
  ias_batch: string;
  cadre: string;
  state: string;
  current_designation: string;
  previous_district: string;
  previous_posting: string;
  new_district: string;
  new_posting: string;
  // Free-form text as written in the article (may not be parseable).
  transfer_date: string;
  effective_date: string;
  // Article publication date (ISO), when known.
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
  id: number;
  url: string;
  resolved_url: string | null;
  title: string | null;
  source_name: string | null;
  language: string | null;
  published_at: string | null;
  status: ArticleStatus;
  relevance_score: number | null;
  transfers_count: number;
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
  news_today: number;
  news_week: number;
  news_total: number;
  last_cycle_at: string | null;
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

export interface AgentStatus {
  last_run: string | null;
  summary: {
    articles?: number;
    transfers?: number;
    new?: number;
    exported?: number;
  } | null;
  interval_seconds: number;
  running: boolean;
  started_at: string | null;
  last_error: string | null;
  next_run: string | null;
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

// ---------- Officer profiles (/api/v1/officers) ----------
// Dates are YYYY-MM-DD strings.

export interface OfficerMovement {
  transfer_id: number;
  date: string;
  /** Transfer/effective date exactly as the article wrote it. */
  stated_date: string | null;
  movement: string;
  role: string;
  role_group: string;
  from_posting: string | null;
  from_district: string | null;
  to_posting: string | null;
  to_district: string | null;
  state: string | null;
  reason: string | null;
  order_number: string | null;
  order_link: string | null;
  headline: string;
  source_name: string | null;
  source_url: string | null;
  source_count: number;
  status: TransferStatus;
  /** Part of the officer's most recent movement. */
  is_current: boolean;
  /** Days in this post until the next move; for a current post, days so far. */
  tenure_days: number | null;
}

export interface OfficerSummary {
  id: string;
  name: string;
  aliases: string[];
  batch: string | null;
  cadre: string | null;
  state: string | null;
  /** One-paragraph summary built from the tracked records. */
  bio: string;
  /** Best photo found by the research agent (a link to where it was published). */
  photo_url: string | null;
  current_role: string;
  current_district: string | null;
  current_state: string | null;
  movements_count: number;
  first_seen: string;
  last_movement_date: string;
  last_movement: string;
}

export type OfficerRelation = 'same_order' | 'same_article' | 'batchmate' | 'same_name';

export interface OfficerLink {
  id: string;
  name: string;
  batch: string | null;
  state: string | null;
  current_role: string;
  relation: OfficerRelation;
}

export interface OfficerStats {
  movements: number;
  distinct_postings: number;
  districts: string[];
  states: string[];
  role_groups: { role_group: string; count: number }[];
  first_seen: string;
  last_seen: string;
  average_tenure_days: number | null;
  sources: number;
  verified_movements: number;
}

export interface PressMention {
  url: string;
  title: string;
  source: string | null;
  published: string | null;
  snippet: string | null;
  /** Text around the officer's name in the article. */
  excerpt: string | null;
  verdict: 'llm' | 'context' | null;
}

export interface OfficerImage {
  image_url: string;
  page_url: string | null;
  caption: string | null;
  source: string | null;
  /** wikipedia = confirmed; press = matched by caption, unverified. */
  origin: 'wikipedia' | 'press';
  hidden: boolean;
}

export interface OfficerResearch {
  status: 'queued' | 'done' | 'failed';
  requested_at: string | null;
  researched_at: string | null;
  error: string | null;
  press: PressMention[];
  images: OfficerImage[];
  photo: OfficerImage | null;
  wikipedia: {
    title: string;
    url: string;
    extract: string;
    image_url: string | null;
    image_page: string | null;
  } | null;
}

export interface OfficerProfile extends OfficerSummary {
  current: OfficerMovement | null;
  timeline: OfficerMovement[];
  stats: OfficerStats;
  sources: { name: string; url: string }[];
  orders: { number: string | null; url: string | null; date: string }[];
  co_transferred: OfficerLink[];
  batchmates: OfficerLink[];
  alternates: OfficerLink[];
  identity_notes: string[];
  research: OfficerResearch | null;
}

export interface OfficersQuery {
  page?: number;
  page_size?: number;
  q?: string;
  state?: string;
  batch?: string;
  cadre?: string;
  sort?: 'recent' | 'name' | 'movements';
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
  /** Title substring search. */
  q?: string;
  /** Only articles that produced at least one transfer record. */
  with_transfers?: boolean;
  /** Only articles published/discovered in the last N days. */
  days?: number;
  /** Hide articles with status 'irrelevant' or 'failed'. */
  exclude_irrelevant?: boolean;
}
