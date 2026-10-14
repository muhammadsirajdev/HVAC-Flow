"""ChatRequest / ChatResponse."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=100)
    text: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str
    intent: str | None = None
    case_id: int | None = None
    booked: bool = False
    fallback_form: bool = False       # widget should show the short contact form
    emergency: bool = False
    trace: list[str] | None = None    # debug only: nodes visited this turn
    debug: dict | None = None         # debug only: state snapshot


class FallbackForm(BaseModel):
    session_id: str = Field(min_length=8, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=7, max_length=40)
    email: str = Field(min_length=3, max_length=200)
    problem: str = Field(min_length=1, max_length=2000)


class FallbackResponse(BaseModel):
    case_id: int | None
    message: str
