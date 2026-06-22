import axios, { AxiosInstance } from 'axios';
import type {
  Analytics,
  Article,
  AuthUser,
  ChatAnswer,
  LoginResponse,
  ModelsResponse,
  NewsQuery,
  Paginated,
  Settings,
  Stats,
  SyncLog,
  SyncStatus,
  Transfer,
  TransfersQuery,
} from './types';

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export const TOKEN_KEY = 'ias_token';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(TOKEN_KEY);
}

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Attach bearer token on every request.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  return config;
});

// Redirect to /login on 401.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      typeof window !== 'undefined' &&
      error?.response?.status === 401 &&
      !window.location.pathname.startsWith('/login')
    ) {
      clearToken();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Strip undefined / empty-string params so we never send blanks.
function cleanParams<T extends Record<string, unknown>>(params?: T) {
  if (!params) return undefined;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    out[k] = v;
  }
  return out;
}

// ---------- Auth ----------
export async function login(
  email: string,
  password: string
): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>('/api/v1/auth/login', {
    email,
    password,
  });
  return data;
}

export async function getMe(): Promise<AuthUser> {
  const { data } = await api.get<AuthUser>('/api/v1/auth/me');
  return data;
}

// ---------- Transfers ----------
export async function getTransfers(
  query?: TransfersQuery
): Promise<Paginated<Transfer>> {
  const { data } = await api.get<Paginated<Transfer>>('/api/v1/transfers', {
    params: cleanParams(query as Record<string, unknown>),
  });
  return data;
}

export async function getTransfer(id: string): Promise<Transfer> {
  const { data } = await api.get<Transfer>(`/api/v1/transfers/${id}`);
  return data;
}

export async function getOfficerTransfers(name: string): Promise<Transfer[]> {
  const { data } = await api.get<Transfer[]>(
    `/api/v1/transfers/officer/${encodeURIComponent(name)}`
  );
  return data;
}

// ---------- Stats + Analytics ----------
export async function getStats(): Promise<Stats> {
  const { data } = await api.get<Stats>('/api/v1/stats');
  return data;
}

export async function getAnalytics(): Promise<Analytics> {
  const { data } = await api.get<Analytics>('/api/v1/stats/analytics');
  return data;
}

// ---------- News ----------
export async function getNews(query?: NewsQuery): Promise<Paginated<Article>> {
  const { data } = await api.get<Paginated<Article>>('/api/v1/news', {
    params: cleanParams(query as Record<string, unknown>),
  });
  return data;
}

// ---------- Sync ----------
export async function getSyncStatus(): Promise<SyncStatus> {
  const { data } = await api.get<SyncStatus>('/api/v1/sync/status');
  return data;
}

export async function getSyncLogs(): Promise<SyncLog[]> {
  const { data } = await api.get<SyncLog[]>('/api/v1/sync/logs');
  return data;
}

export async function retrySync(): Promise<{ requeued: number }> {
  const { data } = await api.post<{ requeued: number }>('/api/v1/sync/retry');
  return data;
}

// ---------- Settings ----------
export async function getSettings(): Promise<Settings> {
  const { data } = await api.get<Settings>('/api/v1/settings');
  return data;
}

export async function updateExportSettings(body: {
  spreadsheet_id?: string;
  worksheet_name?: string;
  auto_export?: boolean;
}): Promise<Settings> {
  const { data } = await api.put<Settings>('/api/v1/settings/export', body);
  return data;
}

export async function uploadCredentials(file: File): Promise<{ ok: boolean }> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await api.post('/api/v1/settings/credentials', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function getModels(): Promise<ModelsResponse> {
  const { data } = await api.get<ModelsResponse>('/api/v1/settings/models');
  return data;
}

// ---------- Assistant (RAG) ----------
export async function askAssistant(question: string): Promise<ChatAnswer> {
  // Local CPU generation can take a while — allow a generous timeout.
  const { data } = await api.post<ChatAnswer>(
    '/api/v1/chat/ask',
    { question },
    { timeout: 180000 },
  );
  return data;
}

// Set (or clear, by passing null) the optional OpenAI API key.
export async function updateOpenAiKey(
  key: string | null,
): Promise<Settings> {
  const { data } = await api.put<Settings>('/api/v1/settings/openai', {
    openai_api_key: key,
  });
  return data;
}

// ---------- Agents ----------
export async function runAgents(): Promise<{ queued: boolean; task_id: string }> {
  const { data } = await api.post('/api/v1/agents/run');
  return data;
}

export async function discoverAgents(): Promise<{
  queued: boolean;
  task_id: string;
}> {
  const { data } = await api.post('/api/v1/agents/discover');
  return data;
}
