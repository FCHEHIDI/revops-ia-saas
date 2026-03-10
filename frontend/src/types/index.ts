// ---------------------------------------------------------------------------
// Auth & User
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  email: string;
  full_name: string;
  tenant_id: string;
  is_active: boolean;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

// ---------------------------------------------------------------------------
// Chat & Messages
// ---------------------------------------------------------------------------

export type MessageRole = "user" | "assistant" | "tool";

export interface ToolCallData {
  tool: string;
  result: unknown;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  toolCalls?: ToolCallData[];
  isStreaming?: boolean;
  createdAt: Date;
}

export interface Conversation {
  id: string;
  tenant_id: string;
  title?: string;
  created_at: string;
  updated_at: string;
}

// SSE event payloads mirroring orchestrator/src/models.rs SseEventPayload
export type SseEvent =
  | { type: "token"; content: string }
  | { type: "tool_call"; tool: string; result: unknown }
  | { type: "done"; usage: UsageStats }
  | { type: "error"; message: string };

export interface UsageStats {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface ProcessRequest {
  tenant_id: string;
  conversation_id: string;
  message: string;
  user_id: string;
}

// ---------------------------------------------------------------------------
// CRM
// ---------------------------------------------------------------------------

export type ContactStatus = "active" | "inactive" | "lead" | "customer" | "churned";

export interface Contact {
  id: string;
  tenant_id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  company?: string;
  status: ContactStatus;
  created_at: string;
  updated_at: string;
}

export interface Company {
  id: string;
  tenant_id: string;
  name: string;
  domain?: string;
  industry?: string;
  size?: string;
  contact_count: number;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Billing
// ---------------------------------------------------------------------------

export type InvoiceStatus = "draft" | "pending" | "paid" | "overdue" | "cancelled";

export interface Invoice {
  id: string;
  tenant_id: string;
  number: string;
  customer_name: string;
  customer_email: string;
  amount: number;
  currency: string;
  status: InvoiceStatus;
  due_date: string;
  issued_at: string;
  paid_at?: string;
}

export interface Subscription {
  id: string;
  tenant_id: string;
  plan: string;
  status: "active" | "trialing" | "cancelled" | "past_due";
  current_period_start: string;
  current_period_end: string;
  amount: number;
  currency: string;
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export interface Metric {
  label: string;
  value: number | string;
  unit?: string;
  change?: number;
  changeType?: "increase" | "decrease" | "neutral";
  period?: string;
}

export interface ChartDataPoint {
  date: string;
  value: number;
  label?: string;
}

// ---------------------------------------------------------------------------
// Sequences
// ---------------------------------------------------------------------------

export type SequenceStatus = "draft" | "active" | "paused" | "completed";

export interface Sequence {
  id: string;
  tenant_id: string;
  name: string;
  description?: string;
  status: SequenceStatus;
  step_count: number;
  enrolled_count: number;
  completed_count: number;
  created_at: string;
  updated_at: string;
}

export interface SequenceStep {
  id: string;
  sequence_id: string;
  order: number;
  type: "email" | "linkedin" | "call" | "wait";
  subject?: string;
  body?: string;
  delay_days: number;
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export type DocumentStatus = "uploading" | "processing" | "indexed" | "error";

export interface Document {
  id: string;
  tenant_id: string;
  filename: string;
  size: number;
  mime_type: string;
  status: DocumentStatus;
  chunk_count?: number;
  uploaded_at: string;
  indexed_at?: string;
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export interface ApiError {
  detail: string;
  status?: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
