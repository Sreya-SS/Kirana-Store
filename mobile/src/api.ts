/**
 * Tiny typed API client. Every call surfaces a clear Error message so screens
 * can show it to the user instead of failing silently.
 */
import { API_BASE_URL } from './config';

export type Item = {
  id: number;
  name: string;
  unit: string;
  current_stock: number;
  reorder_level: number;
  low_stock: boolean;
};

export type ForecastPoint = { date: string; qty: number };

export type Metrics = {
  wape_baseline: number;
  wape_lightgbm: number;
  wape_baseline_pct: number;
  wape_lightgbm_pct: number;
  backtest_days: number;
  note: string;
};

export type ForecastResponse = {
  item_id: number;
  item_name: string;
  unit: string;
  horizon: number;
  forecast: ForecastPoint[];
  baseline: ForecastPoint[];
  metrics: Metrics;
};

export type ParsedLine = { item: string; quantity: number; unit: string; matched_item_id: number | null };

export type TranscribeResponse = { transcript: string; parsed: ParsedLine[] };

export type Alert = {
  id: number;
  item_id: number;
  item_name: string;
  message: string;
  created_at: string;
  resolved: boolean;
  useful: boolean | null;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
  } catch (e) {
    throw new Error(
      `[v2] Could not connect to ${API_BASE_URL} — confirm this URL includes :8000 and the backend is running.`,
    );
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>('/health'),

  // Inventory
  getItems: () => request<Item[]>('/items'),
  updateStock: (id: number, current_stock: number) =>
    request<Item>(`/items/${id}/stock`, { method: 'PUT', body: JSON.stringify({ current_stock }) }),
  bulkUpsert: (lines: { item: string; quantity: number; unit: string }[]) =>
    request<{ updated: Item[]; created: Item[] }>('/items/bulk', {
      method: 'POST',
      body: JSON.stringify({ lines }),
    }),

  // Forecast
  getForecast: (id: number) => request<ForecastResponse>(`/forecast/${id}`),
  getMetrics: () => request<Metrics>('/metrics'),

  // Voice
  transcribeText: (text: string) =>
    request<TranscribeResponse>('/voice/parse-text', { method: 'POST', body: JSON.stringify({ text }) }),
  // Audio upload uses FormData, so it bypasses the JSON helper above.
  transcribeAudio: async (uri: string): Promise<TranscribeResponse> => {
    const form = new FormData();
    form.append('file', { uri, name: 'recording.m4a', type: 'audio/m4a' } as any);
    let res: Response;
    try {
      res = await fetch(`${API_BASE_URL}/voice/transcribe`, { method: 'POST', body: form });
    } catch {
      throw new Error(`Can't reach the backend at ${API_BASE_URL}. Is it running?`);
    }
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const body = await res.json();
        if (body?.detail) detail = body.detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    return res.json();
  },

  // Alerts
  getAlerts: () => request<Alert[]>('/alerts'),
  runAlertCheck: () => request<{ created: number; alerts: Alert[] }>('/alerts/run', { method: 'POST' }),
  setAlertFeedback: (id: number, useful: boolean) =>
    request<Alert>(`/alerts/${id}/feedback`, { method: 'POST', body: JSON.stringify({ useful }) }),
};
