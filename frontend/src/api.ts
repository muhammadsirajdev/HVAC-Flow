// Typed client for the FastAPI backend (backend/src/backend/api).

const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "/api";

export type Status = "open" | "booked" | "needs_person" | "done" | "closed" | "cancelled";
export type Channel = "web" | "email" | "form" | "whatsapp" | string;

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("The server can't be reached. Check that the API is running on port 8000.", 0);
  }
  if (!res.ok) {
    const raw = await res.text();
    // The Vite dev proxy answers an empty 500 when nothing is listening on :8000.
    if (res.status >= 500 && !raw.trim()) {
      throw new ApiError("The API isn't running. Start it in backend/ with: uv run uvicorn backend.main:app --reload", 0);
    }
    let message = res.status >= 500
      ? "The API hit an error. The details are in the terminal running uvicorn."
      : `The server answered ${res.status}.`;
    try {
      const body = JSON.parse(raw);
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        const d = body.detail[0];
        message = `${d.loc?.slice(-1)[0] ?? "Field"}: ${d.msg}`;
      }
    } catch {
      /* not JSON */
    }
    if (res.status === 404 && message === "Not Found") {
      message = "This view is off. Set DEV_UI=true in backend/.env and restart the API.";
    }
    throw new ApiError(message, res.status);
  }
  return res.json() as Promise<T>;
}

const get = <T,>(path: string) => request<T>(path);
const post = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

// ---------- chat (Run A) ----------
export interface ChatReply {
  reply: string;
  intent: string | null;
  case_id: number | null;
  booked: boolean;
  fallback_form: boolean;
  emergency: boolean;
  trace: string[] | null;
}

export const sendChat = (session_id: string, text: string) =>
  post<ChatReply>("/chat?debug=true", { session_id, text });

export const sendChatFallback = (body: {
  session_id: string; name: string; phone: string; email: string; problem: string;
}) => post<{ case_id: number | null; message: string }>("/chat/fallback", body);

// ---------- website form answered by email (Run B) ----------
export interface EnquiryResult {
  case_id: number | null;
  sent: boolean;
  to: string;
  subject: string | null;
  body: string | null;
  message: string;
}

export const sendEnquiry = (body: { name: string; email: string; phone: string; message: string }) =>
  post<EnquiryResult>("/forms/enquiry", body);

// ---------- office view (CRM) ----------
export interface Customer {
  customer_id: number;
  name: string | null;
  email: string | null;
  phone: string | null;
}

export interface Visit {
  booking_id: number;
  service: string;
  address: string;
  active: boolean;
  starts_at: string | null;
  slot: string | null;
}

export interface CaseRow {
  case_id: number;
  status: Status;
  channel: Channel;
  note: string | null;
  created_at: string;
  updated_at: string;
  customer: Customer;
  visit: Visit | null;
  last_event: { to_status: Status; reason: string | null; at: string } | null;
  messages: number;
}

export interface Overview {
  business: { name: string; phone: string; tz: string; inbox: string };
  by_status: Record<Status, number>;
  by_channel: Record<string, number>;
  new_7d: number;
  visits_today: number;
  visits_tomorrow: number;
  open_slots: number;
  customers: number;
  next_visit: { case_id: number; service: string; name: string | null; starts_at: string; slot: string } | null;
}

export interface Booking {
  booking_id: number;
  service: string;
  address: string;
  problem: string | null;
  technician: string | null;
  active: boolean;
  reminded: boolean;
  created_at: string;
  confirmation_sent_at: string | null;
  slack_posted_at: string | null;
  starts_at: string;
  ends_at: string;
  slot: string;
}

export interface CaseEvent {
  event_id: number;
  from_status: Status | null;
  to_status: Status;
  reason: string | null;
  created_at: string;
}

export interface Message {
  message_id: number;
  channel: Channel;
  direction: "in" | "out";
  body: string;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface CaseDetail {
  case: {
    case_id: number; status: Status; channel: Channel; note: string | null; email_thread: boolean;
    created_at: string; updated_at: string; closed_at: string | null;
  };
  customer: Customer & { address: string | null; opted_out: boolean; since: string };
  bookings: Booking[];
  events: CaseEvent[];
  messages: Message[];
  other_cases: { case_id: number; status: Status; channel: Channel; created_at: string }[];
}

export type ActivityItem =
  | {
      kind: "event"; id: string; case_id: number; at: string; from_status: Status | null; to_status: Status;
      reason: string | null; channel: Channel; name: string | null; email: string | null; slot: string | null;
    }
  | {
      kind: "email"; id: string; case_id: number; at: string; direction: "in" | "out"; channel: Channel;
      name: string | null; email: string | null; subject: string | null; preview: string | null;
    };

export interface ScheduleSlot {
  slot_id: number;
  starts_at: string;
  ends_at: string;
  taken: boolean;
  case_id: number | null;
  service: string | null;
  name: string | null;
  status: Status | null;
  past: boolean;
}

export const getOverview = () => get<Overview>("/crm/overview");
export const getCases = (p: { status?: string; channel?: string; q?: string }) => {
  const qs = new URLSearchParams(Object.entries(p).filter(([, v]) => v) as [string, string][]).toString();
  return get<{ cases: CaseRow[] }>(`/crm/cases${qs ? `?${qs}` : ""}`);
};
export const getCase = (id: number) => get<CaseDetail>(`/crm/cases/${id}`);
export const getActivity = (limit = 40) => get<{ items: ActivityItem[] }>(`/crm/activity?limit=${limit}`);
export const getSchedule = (days = 7) => get<{ tz: string; slots: ScheduleSlot[] }>(`/crm/schedule?days=${days}`);
export const getHealth = () => get<{ status: string; database: string }>("/health");
