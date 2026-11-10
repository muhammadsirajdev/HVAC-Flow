"""POST /forms/enquiry: a website enquiry form, answered by email (Run B's form path).

Enabled with DEV_UI=true for now: it sends a real email to the address typed in, so it needs the
DEMO_MODE rate limits before it is open to the public.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.graphs.run_b_email import poller
from backend.tools import notify
from backend.tools.booking import create_needs_person_case, to_needs_person
from backend.tools.validation import normalize_email, normalize_phone

log = logging.getLogger(__name__)
router = APIRouter(prefix="/forms", tags=["forms"])


class EnquiryForm(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    message: str = Field(min_length=1, max_length=4000)


class EnquiryResponse(BaseModel):
    case_id: int | None
    sent: bool                  # the AI's answer went out by email
    to: str
    subject: str | None = None
    body: str | None = None     # the email as sent, for the page to show
    message: str


@router.post("/enquiry", response_model=EnquiryResponse)
def enquiry(form: EnquiryForm) -> EnquiryResponse:
    s = get_settings()
    if not s.dev_ui:
        raise HTTPException(404)
    email = normalize_email(form.email)
    phone = normalize_phone(form.phone) if form.phone and form.phone.strip() else None
    if not email:
        raise HTTPException(422, "Please check the email address.")
    if form.phone and form.phone.strip() and not phone:
        raise HTTPException(422, "Please check the phone number, or leave it empty.")
    name = form.name.strip()

    try:
        out = poller.handle_form(name, email, phone, form.message.strip())
    except Exception:
        log.exception("website form from %s failed", email)
        out = {"ai_failed": True}

    if out.get("ai_failed"):            # model down or a crash: a person takes it, as with the chat form
        note = f"Website form (AI unavailable). Message: {form.message[:1500]}"
        case_id = out.get("case_id")
        if case_id:
            to_needs_person(case_id, note)
        else:
            case_id = create_needs_person_case(name, phone, email, None, note=note, channel="form")
        notify.post_needs_person(case_id, "website form, AI unavailable",
                                 {"Name": name, "Email": email, "Phone": phone or "-", "Message": form.message[:500]})
        return EnquiryResponse(case_id=case_id, sent=False, to=email, message=(
            f"Thanks, {name}. Our team will email you about Case #{case_id}, or call us at {s.business_phone}."))

    if out.get("status") == "needs_person" and not out.get("body"):
        return EnquiryResponse(case_id=out.get("case_id"), sent=False, to=email, message=(
            f"Thanks, {name}. Your case is already with our team, and they will reply to {email} shortly."))

    if not out.get("sent"):
        return EnquiryResponse(case_id=out.get("case_id"), sent=False, to=email, body=out.get("body"), message=(
            f"Your enquiry is saved as Case #{out.get('case_id')}, but the email could not be sent just now. "
            f"Our team will reply by hand."))

    return EnquiryResponse(case_id=out["case_id"], sent=True, to=email, subject=out.get("subject"),
                           body=out.get("body"), message=f"Answer sent to {email}.")
