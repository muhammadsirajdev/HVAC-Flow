"""Partly hide contact details for the public demo's office view.

    name     "Maria Gonzalez"            -> "Maria G."
    email    "maria.gonzalez@gmail.com"  -> "ma•••@gmail.com"
    phone    "+13055550142"              -> "(•••) •••-0142"
    address  "1420 Coral Way, Miami, FL" -> "•••, Miami, FL"
    text     emails and phone numbers inside messages are hidden the same way
"""

from __future__ import annotations

import re

DOT = "•••"
_EMAIL = re.compile(r"[\w.+-]+@([\w-]+\.)+[\w-]{2,}")
_PHONE = re.compile(r"(?<![\w])\+?\d[\d\s().-]{6,}\d(?![\w])")
_STREET = re.compile(
    r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?(?:[A-Za-z0-9.']+\s+){0,4}"
    r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Ct|Court|Way|Pl|Place|Ter|Terrace"
    r"|Hwy|Highway|Pkwy|Parkway|Cir|Circle)\b", re.IGNORECASE)


def name(value: str | None) -> str | None:
    if not value or not value.strip():
        return value
    parts = value.split()
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0]}."


def email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return value
    local, _, domain = value.partition("@")
    return f"{local[:2]}{DOT}@{domain}"


def phone(value: str | None) -> str | None:
    if not value:
        return value
    digits = re.sub(r"\D", "", value)
    return f"({DOT}) {DOT}-{digits[-4:]}" if len(digits) >= 4 else DOT


def address(value: str | None) -> str | None:
    if not value or not value.strip():
        return value
    parts = [p.strip() for p in value.split(",")]
    return ", ".join([DOT, *parts[1:]]) if len(parts) > 1 else DOT


def text(value: str | None) -> str | None:
    if not value:
        return value
    value = _EMAIL.sub(lambda m: email(m.group(0)), value)
    value = _PHONE.sub(lambda m: phone(m.group(0)) if len(re.sub(r"\D", "", m.group(0))) >= 7 else m.group(0),
                       value)
    return _STREET.sub(f"{DOT} (address hidden)", value)
