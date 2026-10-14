"""Email and phone (E.164) validation. Code checks these, never the model."""

import re

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")


def normalize_email(value: str | None) -> str | None:
    """Lower-cased email, or None if it does not look valid."""
    if not value:
        return None
    email = value.strip().strip("<>.,;").lower()
    return email if EMAIL_RE.match(email) else None


def normalize_phone(value: str | None) -> str | None:
    """E.164 phone number, or None if it does not look valid.

    US numbers (the business is in Miami): 7867976193, (786) 797-6193, 1-786-797-6193.
    Pakistan mobiles (scope example): 03001234567 -> +923001234567.
    Anything typed with a leading + is kept if it has 8-15 digits.
    """
    if not value:
        return None
    raw = value.strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+") or raw.startswith("00"):
        digits = digits[2:] if raw.startswith("00") else digits
        return f"+{digits}" if 8 <= len(digits) <= 15 else None
    if len(digits) == 11 and digits.startswith("03"):
        return f"+92{digits[1:]}"
    if len(digits) == 10 and digits[0] in "23456789":
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1") and digits[1] in "23456789":
        return f"+{digits}"
    return None
