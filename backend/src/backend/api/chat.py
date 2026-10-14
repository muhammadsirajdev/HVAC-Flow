"""POST /chat -> Run A (website widget); POST /chat/fallback for the model-down form."""

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.config import get_settings
from backend.graphs.run_a_chat import chat_turn
from backend.schemas.chat import ChatRequest, ChatResponse, FallbackForm, FallbackResponse
from backend.tools import notify
from backend.tools.booking import create_needs_person_case
from backend.tools.validation import normalize_email, normalize_phone

log = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest, debug: bool = Query(False)) -> ChatResponse:
    # Sync endpoint: FastAPI runs it in a worker thread, the graph is synchronous.
    try:
        out = chat_turn(req.session_id, req.text)
    except Exception:
        log.exception("Run A failed for session %s", req.session_id)
        phone = get_settings().business_phone
        return ChatResponse(reply=f"Sorry, something went wrong. Please leave your details in the "
                                  f"form or call us 24/7 at {phone}.", fallback_form=True)
    show = debug and get_settings().dev_ui
    return ChatResponse(reply=out["reply"], intent=out["intent"], case_id=out["case_id"], booked=out["booked"],
                        fallback_form=out["fallback_form"], emergency=out["emergency"],
                        trace=out["trace"] if show else None,
                        debug=jsonable(out["debug"]) if show else None)


def jsonable(value):
    """State snapshot -> JSON-safe (dates and other objects become strings)."""
    import json
    return json.loads(json.dumps(value, default=str))


@router.post("/fallback", response_model=FallbackResponse)
def fallback(form: FallbackForm) -> FallbackResponse:
    """The short form shown when the model is down: save a needs_person case, tell Slack."""
    phone, email = normalize_phone(form.phone), normalize_email(form.email)
    if not phone or not email:
        raise HTTPException(422, "Please check the phone number and email address.")
    case_id = create_needs_person_case(form.name, phone, email, None,
                                       note=f"Chat fallback form. Problem: {form.problem}")
    notify.post_needs_person(case_id, "website chat fallback form (AI unavailable)",
                             {"Name": form.name, "Phone": phone, "Email": email, "Problem": form.problem})
    return FallbackResponse(case_id=case_id, message=(
        f"Thanks, {form.name}. Our team will contact you shortly about Case #{case_id}."))
