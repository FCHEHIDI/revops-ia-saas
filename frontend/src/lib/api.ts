import { refreshSession } from "./auth";
import type { ApiError } from "@/types";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  skipRefresh?: boolean;
};

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { body, skipRefresh = false, ...rest } = options;

    const res = await fetch(`${this.baseUrl}${path}`, {
      ...rest,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(rest.headers ?? {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (res.status === 401 && !skipRefresh) {
      // Don't attempt refresh for auth endpoints — avoids redirect loops
      const isAuthPath = path.startsWith("/auth/");
      if (!isAuthPath) {
        const refreshed = await refreshSession();
        if (refreshed) {
          return this.request<T>(path, { ...options, skipRefresh: true });
        }
      }
      // Only redirect if not already on the login page
      if (
        typeof window !== "undefined" &&
        !window.location.pathname.startsWith("/login")
      ) {
        window.location.href = "/login";
      }
      throw new Error("Unauthorized");
    }

    if (!res.ok) {
      let errorDetail = "An unexpected error occurred";
      try {
        const errorBody = (await res.json()) as ApiError;
        errorDetail = errorBody.detail ?? errorDetail;
      } catch {
        // ignore parse error
      }
      throw new Error(errorDetail);
    }

    if (res.status === 204 || res.headers.get("content-length") === "0") {
      return undefined as T;
    }

    return res.json() as Promise<T>;
  }

  get<T>(path: string, options?: RequestOptions) {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  post<T>(path: string, body?: unknown, options?: RequestOptions) {
    return this.request<T>(path, { ...options, method: "POST", body });
  }

  put<T>(path: string, body?: unknown, options?: RequestOptions) {
    return this.request<T>(path, { ...options, method: "PUT", body });
  }

  patch<T>(path: string, body?: unknown, options?: RequestOptions) {
    return this.request<T>(path, { ...options, method: "PATCH", body });
  }

  delete<T>(path: string, options?: RequestOptions) {
    return this.request<T>(path, { ...options, method: "DELETE" });
  }
}

export const api = new ApiClient(BACKEND_URL);

// ---------------------------------------------------------------------------
// Auth endpoints
// ---------------------------------------------------------------------------

import type { User, LoginRequest, RegisterRequest } from "@/types";

export const authApi = {
  login: (data: LoginRequest) => api.post<User>("/auth/login", data),
  register: (data: RegisterRequest) => api.post<User>("/auth/register", data),
  me: () => api.get<User>("/auth/me"),
  logout: () => api.post<{ message: string }>("/auth/logout"),
  refresh: () => api.post<{ message: string }>("/auth/refresh"),
};

// ---------------------------------------------------------------------------
// CRM endpoints  (public CRUD — /api/v1/crm/*)
// ---------------------------------------------------------------------------

import type { Contact, Account, Deal, PaginatedResponse } from "@/types";

export const crmApi = {
  // Contacts
  listContacts: (params?: { query?: string; account_id?: string; page?: number; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.query)      p.set("query", params.query);
    if (params?.account_id) p.set("account_id", params.account_id);
    p.set("page",  String(params?.page  ?? 1));
    p.set("limit", String(params?.limit ?? 20));
    return api.get<PaginatedResponse<Contact>>(`/crm/contacts?${p}`);
  },
  getContact: (id: string) => api.get<Contact>(`/crm/contacts/${id}`),

  // Accounts
  listAccounts: (params?: { query?: string; industry?: string; page?: number; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.query)    p.set("query", params.query);
    if (params?.industry) p.set("industry", params.industry);
    p.set("page",  String(params?.page  ?? 1));
    p.set("limit", String(params?.limit ?? 20));
    return api.get<PaginatedResponse<Account>>(`/crm/accounts?${p}`);
  },
  getAccount: (id: string) => api.get<Account>(`/crm/accounts/${id}`),

  // Deals
  listDeals: (params?: { stage?: string; owner_id?: string; page?: number; limit?: number }) => {
    const p = new URLSearchParams();
    if (params?.stage)    p.set("stage", params.stage);
    if (params?.owner_id) p.set("owner_id", params.owner_id);
    p.set("page",  String(params?.page  ?? 1));
    p.set("limit", String(params?.limit ?? 20));
    return api.get<PaginatedResponse<Deal>>(`/crm/deals?${p}`);
  },
  getDeal: (id: string) => api.get<Deal>(`/crm/deals/${id}`),

  /** @deprecated Utiliser listAccounts */
  listCompanies: (page = 1, pageSize = 20) =>
    api.get<PaginatedResponse<Account>>(`/crm/accounts?page=${page}&limit=${pageSize}`),
};

// ---------------------------------------------------------------------------
// Billing endpoints
// ---------------------------------------------------------------------------

import type { Invoice, Subscription } from "@/types";

export const billingApi = {
  listInvoices: (page = 1, pageSize = 20) =>
    api.get<PaginatedResponse<Invoice>>(`/billing/invoices?page=${page}&page_size=${pageSize}`),
  getSubscription: () => api.get<Subscription>("/billing/subscription"),
};

// ---------------------------------------------------------------------------
// Analytics endpoints
// ---------------------------------------------------------------------------

import type { Metric } from "@/types";

// MCP proxy call shape
export interface McpCallResponse<T = unknown> {
  result: T;
}

export const analyticsApi = {
  getMetrics: () => api.get<Metric[]>("/analytics/metrics"),

  // MCP proxy calls
  getMrrTrend: (months = 12) =>
    api.post<McpCallResponse<{
      data_points: Array<{ month: string; mrr: string; new_mrr: string; churned_mrr: string; net_new_mrr: string }>;
      current_mrr: string;
      mom_growth_rate: number;
    }>>("/analytics/call", { tool: "get_mrr_trend", params: { months } }),

  getFunnelAnalysis: () =>
    api.post<McpCallResponse<{
      stages: Array<{ stage: string; entered: number; exited: number; converted: number; conversion_rate: number; avg_time_days: number }>;
      overall_conversion: number;
      bottleneck_stage: string | null;
    }>>("/analytics/call", { tool: "get_funnel_analysis", params: {} }),

  getChurnRate: () =>
    api.post<McpCallResponse<{
      churn_rate: number;
      churned_count: number;
      starting_count: number;
      net_revenue_retention: number;
    }>>("/analytics/call", { tool: "compute_churn_rate", params: {} }),
};

// ---------------------------------------------------------------------------
// Sequences endpoints
// ---------------------------------------------------------------------------

import type { Sequence } from "@/types";

export interface SequenceStepInput {
  step_type: "email" | "linkedin_message" | "call" | "task" | "wait";
  delay_days: number;
  delay_hours: number;
  subject?: string;
  body_template?: string;
}

export const sequencesApi = {
  listSequences: (page = 1, pageSize = 20) =>
    api.get<PaginatedResponse<Sequence>>(`/sequences?page=${page}&page_size=${pageSize}`),

  createSequence: (params: {
    tenant_id: string;
    user_id: string;
    name: string;
    description?: string;
    steps: SequenceStepInput[];
    tags?: string[];
  }) =>
    api.post<McpCallResponse<{ sequence_id: string; steps_count: number; created_at: string }>>(
      "/sequences/call",
      { tool: "create_sequence", params: { ...params, exit_conditions: [], tags: params.tags ?? [] } }
    ),

  updateSequenceStatus: (params: {
    tenant_id: string;
    user_id: string;
    sequence_id: string;
    status: "active" | "paused" | "draft" | "archived";
  }) =>
    api.post<McpCallResponse<unknown>>(
      "/sequences/call",
      { tool: "update_sequence", params }
    ),
};

// ---------------------------------------------------------------------------
// Documents endpoints
// ---------------------------------------------------------------------------

import type { Document } from "@/types";

export const documentsApi = {
  listDocuments: () => api.get<Document[]>("/rag/documents"),
  uploadDocument: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return fetch(`${BACKEND_URL}/rag/documents`, {
      method: "POST",
      credentials: "include",
      body: formData,
    }).then((r) => r.json() as Promise<Document>);
  },
  deleteDocument: (id: string) => api.delete(`/rag/documents/${id}`),
};
