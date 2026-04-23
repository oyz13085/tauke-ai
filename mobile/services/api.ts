/**
 * Tauke.AI API client.
 * Base URL reads from the environment variable or falls back to localhost for dev.
 * For phone testing, replace with your machine's LAN IP (e.g. http://192.168.1.x:8000).
 */

const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

export const SHOP_ID_KEY = "tauke_shop_id";

// ── Types ─────────────────────────────────────────────────────────────────────

export type ProcessingStatus = "pending" | "processing" | "done" | "failed" | "needs_review";
export type RecType = "reorder" | "stockout_warning" | "spoilage_warning" | "price_increase" | "price_decrease" | "no_action";
export type RecStatus = "active" | "dismissed" | "acted_on" | "expired";

export interface Invoice {
  id:                string;
  shop_id:           string;
  supplier_name?:    string;
  invoice_date?:     string;
  total_amount?:     number;
  currency:          string;
  processing_status: ProcessingStatus;
  ocr_confidence?:   number;
  created_at:        string;
}

export interface InventoryItem {
  id:            string;
  shop_id:       string;
  product_id:    string;
  batch_ref?:    string;
  current_qty:   number;
  unit:          string;
  cost_price?:   number;
  purchase_date?: string;
  expiry_date?:  string;
  is_depleted:   boolean;
  last_updated:  string;
}

export interface ReasoningTrace {
  base_demand_daily:     number;
  adjusted_demand_daily: number;
  multipliers_applied:   { weather: number; event: number; dow: number };
  safety_stock:          number;
  usable_stock:          number;
  current_stock:         number;
  spoilage_at_lead_time: number;
  target_order_qty:      number;
  confidence_components: {
    data_recency:          number;
    data_volume:           number;
    ocr_quality:           number;
    context_availability:  number;
  };
  confidence_final:      number;
  risk_of_inaction_myr:  number;
  expected_gain_myr:     number;
  decision:              string;
  context_signals_active: string[];
}

export interface GLMExplanation {
  headline:             string;
  explanation:          string;
  money_impact:         string;
  confidence_statement: string;
  next_step:            string;
}

export interface Recommendation {
  id:                  string;
  shop_id:             string;
  product_id?:         string;
  recommendation_type: RecType;
  status:              RecStatus;
  recommended_action:  string;
  target_quantity?:    number;
  target_price?:       number;
  confidence_score:    number;
  risk_of_inaction?:   number;
  expected_gain?:      number;
  reasoning_trace:     ReasoningTrace;
  external_factors?:   { signals: string[] };
  glm_explanation?:    string;      // JSON string of GLMExplanation
  created_at:          string;
}

export interface Shop {
  id:        string;
  owner_id:  string;
  name:      string;
  shop_type: string;
  city:      string;
  is_halal:  boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── API methods ───────────────────────────────────────────────────────────────

export const api = {
  // Shops
  createShop: (body: {
    owner_email: string;
    owner_name:  string;
    shop_name:   string;
    shop_type?:  string;
    city?:       string;
  }) => request<Shop>("/api/shops", { method: "POST", body: JSON.stringify(body) }),

  getShop: (shopId: string) => request<Shop>(`/api/shops/${shopId}`),

  updatePushToken: (shopId: string, token: string) =>
    request<{ ok: boolean }>(`/api/shops/${shopId}/push-token?token=${encodeURIComponent(token)}`, {
      method: "PATCH",
    }),

  // Invoices
  uploadInvoice: (shopId: string, imageUri: string, filename: string, mimeType: string) => {
    const form = new FormData();
    form.append("shop_id", shopId);
    form.append("file", { uri: imageUri, name: filename, type: mimeType } as unknown as Blob);
    return fetch(`${BASE_URL}/api/invoices/upload`, {
      method: "POST",
      body: form,
    }).then(async (res) => {
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      return res.json() as Promise<Invoice>;
    });
  },

  getInvoice: (invoiceId: string) => request<Invoice>(`/api/invoices/${invoiceId}`),

  // Inventory
  listInventory: (shopId: string, includeDepleted = false) =>
    request<InventoryItem[]>(
      `/api/inventory?shop_id=${shopId}&include_depleted=${includeDepleted}`
    ),

  adjustInventory: (itemId: string, qtyDelta: number) =>
    request<InventoryItem>(`/api/inventory/${itemId}?qty_delta=${qtyDelta}`, { method: "PATCH" }),

  // Recommendations
  listRecommendations: (shopId: string, status: RecStatus = "active") =>
    request<Recommendation[]>(
      `/api/recommendations?shop_id=${shopId}&status=${status}`
    ),

  submitFeedback: (recId: string, rating: number, note?: string) =>
    request<Recommendation>(`/api/recommendations/${recId}/feedback`, {
      method:  "PATCH",
      body:    JSON.stringify({ rating, note }),
    }),

  dismissRecommendation: (recId: string) =>
    request<Recommendation>(`/api/recommendations/${recId}/dismiss`, { method: "PATCH" }),

  // Context
  contextPreview: (shopId: string) =>
    request<{
      date:                 string;
      weather_condition:    string;
      active_events:        string[];
      context_availability: number;
    }>(`/api/context/preview?shop_id=${shopId}`),
};

// ── Helpers ───────────────────────────────────────────────────────────────────

export function parseGlmExplanation(jsonStr?: string): GLMExplanation | null {
  if (!jsonStr) return null;
  try {
    return JSON.parse(jsonStr) as GLMExplanation;
  } catch {
    return null;
  }
}

export function confidenceColor(score: number): string {
  if (score >= 0.80) return "#22c55e";   // green
  if (score >= 0.60) return "#f59e0b";   // amber
  return "#ef4444";                       // red
}

export function decisionEmoji(type: RecType): string {
  const map: Record<RecType, string> = {
    reorder:          "📦",
    stockout_warning: "🚨",
    spoilage_warning: "⏰",
    price_increase:   "📈",
    price_decrease:   "📉",
    no_action:        "✅",
  };
  return map[type] ?? "💡";
}
