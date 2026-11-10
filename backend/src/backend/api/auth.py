"""Office sign-in for the frontend.

    GET  /auth/me       what this visitor may see: demo mode, sign-in needed, signed in
    POST /auth/login    {password} -> {token, expires_at}; the frontend sends it as a Bearer token
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.core import demo, ratelimit

router = APIRouter(prefix="/auth", tags=["auth"])


class Login(BaseModel):
    password: str = Field(min_length=1, max_length=200)


@router.get("/me")
def me(request: Request) -> dict:
    s = get_settings()
    signed_in = demo.token_valid(demo.bearer(request))
    return {
        "demo_mode": s.demo_mode,
        "login_enabled": bool(s.office_password),
        "signed_in": signed_in,
        # What the office shows this visitor: everything, partly hidden details, or nothing yet.
        "office": "full" if signed_in or not (s.demo_mode or s.office_password)
                  else "masked" if s.demo_mode else "locked",
    }


@router.post("/login")
def login(body: Login, request: Request) -> dict:
    if not get_settings().office_password:
        raise HTTPException(404, "Sign-in is not set up. Set OFFICE_PASSWORD on the server.")
    ratelimit.limit(f"login:{ratelimit.client_ip(request)}", 8, 900,
                    "Too many sign-in attempts. Please wait 15 minutes.")
    if not demo.password_ok(body.password):
        raise HTTPException(401, "That password isn't right.")
    token, expires = demo.make_token()
    return {"token": token, "expires_at": expires}
