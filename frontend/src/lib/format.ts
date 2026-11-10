import type { ActivityItem, CaseDetail, Channel, Status } from "../api";

// Times are shown in the business time zone (Miami), whatever the viewer's clock says.
let TZ = "America/New_York";
export const setBusinessTz = (tz: string) => {
  TZ = tz || TZ;
};

const fmt = (opts: Intl.DateTimeFormatOptions) => (iso: string) =>
  new Intl.DateTimeFormat("en-US", { timeZone: TZ, ...opts }).format(new Date(iso));

export const time = fmt({ hour: "numeric", minute: "2-digit" });
export const dayShort = fmt({ weekday: "short", day: "numeric", month: "short" });
export const dayLong = fmt({ weekday: "long", day: "numeric", month: "long" });
export const dateTime = fmt({ weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
export const weekday = fmt({ weekday: "long" });
export const dayDate = fmt({ month: "long", day: "numeric" });
export const dayKey =fmt({ year: "numeric", month: "2-digit", day: "2-digit" });

export function ago(iso: string, now = Date.now()): string {
  const s = Math.round((now - new Date(iso).getTime()) / 1000);
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  if (d < 7) return `${d} d ago`;
  return dayShort(iso);
}

export function relativeDay(iso: string): string {
  const k = dayKey(iso);
  const today = dayKey(new Date().toISOString());
  const tomorrow = dayKey(new Date(Date.now() + 864e5).toISOString());
  const yesterday = dayKey(new Date(Date.now() - 864e5).toISOString());
  if (k === today) return "Today";
  if (k === tomorrow) return "Tomorrow";
  if (k === yesterday) return "Yesterday";
  return dayLong(iso);
}

export const STATUS: Record<Status, { label: string; hint: string }> = {
  open: { label: "Open", hint: "Talking with the customer, nothing booked yet" },
  booked: { label: "Booked", hint: "A technician visit is on the schedule" },
  needs_person: { label: "Needs a person", hint: "The AI stepped back; someone from the office replies" },
  done: { label: "Done", hint: "The technician finished the job" },
  closed: { label: "Closed", hint: "Thank-you sent, nothing left to do" },
  cancelled: { label: "Cancelled", hint: "The visit was called off" },
};

export const STATUS_ORDER: Status[] = ["needs_person", "open", "booked", "done", "closed", "cancelled"];

export const CHANNEL: Record<string, string> = {
  web: "Website chat",
  email: "Email",
  form: "Website form",
  whatsapp: "WhatsApp",
};
export const channelLabel = (c: Channel) => CHANNEL[c] ?? c;

export const displayName = (name: string | null | undefined, email?: string | null) =>
  name?.trim() || email?.split("@")[0] || "Unknown customer";

/** +13055550142 -> (305) 555-0142; other numbers are shown as stored. */
export function phone(p: string | null | undefined): string {
  const m = p?.match(/^\+1(\d{3})(\d{3})(\d{4})$/);
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : p ?? "";
}

export const sentence = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

/** A website-form email ("Name: ...\nEmail: ...\nMessage: ...") shown as just its message. */
export function formMessage(body: string): string {
  if (!/^\s*\**name\**\s*:/i.test(body)) return body;
  const m = body.match(/^\s*\**(message|comments?|enquiry|inquiry|details)\**\s*:\s*([\s\S]*)$/im);
  return m ? m[2].trim() : body;
}

export function initials(name: string | null | undefined, email?: string | null): string {
  const n = displayName(name, email).replace(/[^\p{L}\s]/gu, " ").trim().split(/\s+/);
  return ((n[0]?.[0] ?? "?") + (n.length > 1 ? n[n.length - 1][0] : "")).toUpperCase();
}

// Reasons written by code ("create_booking via web") say nothing a person needs; human ones are kept.
const MECHANICAL = /^(create_booking|change_booking|opened) via |^thank-you email sent$|^reported done/;
export const humanReason = (reason: string | null | undefined) =>
  reason && !MECHANICAL.test(reason) ? reason : null;

// A chat becomes a case only when it books or needs a person, so "opened" comes after the first messages.
const OPENED: Record<string, string> = {
  web: "became a case from the website chat",
  email: "emailed the office",
  form: "sent the website enquiry form",
  whatsapp: "messaged on WhatsApp",
};

/** What a status change means, in words: "booked a visit", "cancelled the visit"... */
export function eventVerb(e: { from_status: Status | null; to_status: Status; reason: string | null; channel?: Channel }): {
  verb: string;
  tone: Status;
} {
  const r = e.reason ?? "";
  switch (e.to_status) {
    case "open":
      if (e.from_status === "needs_person") return { verb: "was handed back to the AI", tone: "open" };
      return { verb: OPENED[e.channel ?? ""] ?? "got in touch", tone: "open" };
    case "booked":
      if (r.startsWith("change_booking")) return { verb: "moved the visit", tone: "booked" };
      return { verb: "booked a visit", tone: "booked" };
    case "needs_person":
      return { verb: e.from_status ? "was handed to a person" : "needs a person", tone: "needs_person" };
    case "cancelled":
      return { verb: "cancelled the visit", tone: "cancelled" };
    case "done":
      return { verb: "had the job marked done", tone: "done" };
    case "closed":
      return { verb: "got a thank-you, case closed", tone: "closed" };
  }
}

export function activitySentence(i: ActivityItem): { verb: string; tone: Status | "mail"; extra: string | null } {
  if (i.kind === "email") {
    return i.direction === "in"
      ? { verb: i.channel === "form" ? "wrote through the website form" : "sent an email", tone: "mail",
          extra: i.preview && formMessage(i.preview) }
      : { verb: "got an answer by email", tone: "mail", extra: i.subject };
  }
  const { verb, tone } = eventVerb(i);
  const reason = humanReason(i.reason);
  const extra = i.to_status === "booked" && i.slot ? `for ${i.slot}` : null;
  return { verb: reason && !extra ? `${verb}:` : verb, tone, extra: extra ?? reason };
}

// ---------- case journey: events, messages and notifications in one timeline ----------
export type JourneyItem =
  | { kind: "status"; at: string; key: string; from: Status | null; to: Status; reason: string | null; verb: string; slot?: string }
  | { kind: "message"; at: string; key: string; channel: Channel; direction: "in" | "out"; body: string; meta: Record<string, unknown> }
  | { kind: "notice"; at: string; key: string; text: string; icon: "mail" | "slack" | "bell" };

export function buildJourney(d: CaseDetail): { items: JourneyItem[]; toneAt: Status[] } {
  const items: JourneyItem[] = [];
  for (const e of d.events) {
    const { verb } = eventVerb({ ...e, channel: d.case.channel });
    const booking = e.to_status === "booked"
      ? [...d.bookings].reverse().find((b) => new Date(b.created_at).getTime() <= new Date(e.created_at).getTime() + 5000)
      : undefined;
    items.push({ kind: "status", at: e.created_at, key: `e${e.event_id}`, from: e.from_status, to: e.to_status,
      reason: humanReason(e.reason), verb, slot: booking?.slot });
  }
  for (const m of d.messages) {
    items.push({ kind: "message", at: m.created_at, key: `m${m.message_id}`, channel: m.channel,
      direction: m.direction, body: m.direction === "in" ? formMessage(m.body) : m.body, meta: m.meta });
  }
  for (const b of d.bookings) {
    if (b.confirmation_sent_at)
      items.push({ kind: "notice", at: b.confirmation_sent_at, key: `c${b.booking_id}`, icon: "mail",
        text: `Confirmation email sent for ${b.slot}` });
    if (b.slack_posted_at)
      items.push({ kind: "notice", at: b.slack_posted_at, key: `s${b.booking_id}`, icon: "slack",
        text: "Posted to the office in Slack" });
  }
  items.sort((a, b) => a.at.localeCompare(b.at) || order(a) - order(b));

  // A move rewrites the booking row, so only the time now on it is known: keep it on the latest booking step.
  const booked = items.filter((i): i is Extract<JourneyItem, { kind: "status" }> => i.kind === "status" && i.to === "booked");
  booked.slice(0, -1).forEach((i) => (i.slot = undefined));

  // The status in force at each item: it colours the journey line.
  const toneAt: Status[] = [];
  let tone: Status = "open";
  for (const it of items) {
    if (it.kind === "status") tone = it.to;
    toneAt.push(tone);
  }
  return { items, toneAt };
}

const order = (i: JourneyItem) => (i.kind === "message" ? (i.direction === "in" ? 0 : 1) : i.kind === "status" ? 2 : 3);

export function isBusinessDay(iso: string, offsetDays: number) {
  return dayKey(iso) === dayKey(new Date(Date.now() + offsetDays * 864e5).toISOString());
}
