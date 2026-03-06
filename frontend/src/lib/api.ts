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
      const refreshed = await refreshSession();
      if (refreshed) {
        return this.request<T>(path, { ...options, skipRefresh: true });
      }
      if (typeof window !== "undefined") {
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

import type { User, LoginRequest } from "@/types";

export const authApi = {
  login: (data: LoginRequest) => api.post<User>("/auth/login", data),
  me: () => api.get<User>("/auth/me"),
  logout: () => api.post<{ message: string }>("/auth/logout"),
  refresh: () => api.post<{ message: string }>("/auth/refresh"),
};

// ---------------------------------------------------------------------------
// CRM endpoints
// ---------------------------------------------------------------------------

import type { Contact, Company, PaginatedResponse } from "@/types";

export const crmApi = {
  listContacts: (page = 1, pageSize = 20) =>
    api.get<PaginatedResponse<Contact>>(`/crm/contacts?page=${page}&page_size=${pageSize}`),
  getContact: (id: string) => api.get<Contact>(`/crm/contacts/${id}`),
  listCompanies: (page = 1, pageSize = 20) =>
    api.get<PaginatedResponse<Company>>(`/crm/companies?page=${page}&page_size=${pageSize}`),
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

export const analyticsApi = {
  getMetrics: () => api.get<Metric[]>("/analytics/metrics"),
};

// ---------------------------------------------------------------------------
// Sequences endpoints
// ---------------------------------------------------------------------------

import type { Sequence } from "@/types";

export const sequencesApi = {
  listSequences: (page = 1, pageSize = 20) =>
    api.get<PaginatedResponse<Sequence>>(`/sequences?page=${page}&page_size=${pageSize}`),
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
