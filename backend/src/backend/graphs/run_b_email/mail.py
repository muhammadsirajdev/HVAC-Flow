"""Code-only email checks for Run B, applied before the AI sees anything (plan 6.2-6.3).

The Gmail MCP returns no raw headers, so auto-replies are recognised by sender and subject;
newsletters are already excluded by the poll query (Gmail categories).
"""

from __future__ import annotations

import re

from backend.tools.validation import normalize_email, normalize_phone

CASE_REF = re.compile(r"\[Case #(\d+)\]", re.I)
_AUTO_SENDER = re.compile(r"no-?reply|do-?not-?reply|mailer-daemon|postmaster|bounces?[@+.-]", re.I)
_AUTO_SUBJECT = re.compile(
    r"^(auto(matic)?[ -]?(reply|response)|auto:|out of (the )?office|ooo\b|away from|undeliverable|"
    r"delivery status notification|mail delivery (failed|subsystem)|returned mail)", re.I)
# Where the quoted earlier conversation starts in a reply.
_QUOTE_START = re.compile(r"^(On [^\n]{5,200}(\n[^\n]{0,100})?wrote:|-{2,} ?Original Message ?-{2,}|From: .+|"
                          r"_{8,}|--)\s*$", re.I | re.M)
_THANKS = re.compile(r"\b(thanks?|thank you|thx|appreciate|great|perfect|got it|ok(ay)?|noted)\b", re.I)
_REQUEST = re.compile(r"\?|\b(change|move|cancel|resched\w*|book|need|want|can|could|please|help|"
                      r"problem|issue|broken|not working|leak\w*)\b", re.I)

_FORM_LABELS = {
    "name": r"(full |your )?name",
    "email": r"(your )?e-?mail( address)?",
    "phone": r"(phone|telephone|mobile|cell)( number)?",
    "message": r"message|comments?|enquiry|inquiry|details|how can we help\??",
}
_FORM_LINE = re.compile(r"^\s*\**([A-Za-z -]{2,30}\??)\**\s*:\s*(.*)$")


def case_ref(subject: str) -> int | None:
    m = CASE_REF.search(subject or "")
    return int(m.group(1)) if m else None


def is_auto(sender: str, subject: str) -> bool:
    return bool(_AUTO_SENDER.search(sender or "") or _AUTO_SUBJECT.search((subject or "").strip()))


def strip_quoted(text: str, limit: int = 4000) -> str:
    """The new part of an email: drops the quoted conversation and '>' lines."""
    m = _QUOTE_START.search(text or "")
    text = (text or "")[: m.start()] if m else (text or "")
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith(">")]
    return "\n".join(lines).strip()[:limit]


def is_thanks_only(text: str) -> bool:
    """A short thank-you with no question or request: needs no reply."""
    t = (text or "").strip()
    return len(t) <= 120 and bool(_THANKS.search(t)) and not _REQUEST.search(t)


def parse_form(text: str) -> dict:
    """Customer details from a website enquiry-form email ("Name: ...", "Email: ...", ...).
    email/phone are normalized; an invalid one comes back as None."""
    found: dict[str, str] = {}
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        m = _FORM_LINE.match(line)
        if not m:
            continue
        label, value = m.group(1).strip().lower(), m.group(2).strip()
        key = next((k for k, pat in _FORM_LABELS.items() if k not in found and re.fullmatch(pat, label)), None)
        if key == "message":           # the message runs to the end (or to a signature line)
            value = strip_quoted("\n".join([value, *lines[i + 1:]]))
        if key:
            found[key] = value
    return {"name": found.get("name") or None, "email": normalize_email(found.get("email")),
            "phone": normalize_phone(found.get("phone")), "message": found.get("message") or ""}
