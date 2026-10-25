"""Gemensamt för alla sidor: mallar, inloggningskrav och CSRF-skydd."""

import socket
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, Request, WebSocket
from fastapi.templating import Jinja2Templates

from .config import DEV

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

NAV = [
    ("overview", "/", "Översikt"),
    ("packages", "/packages", "Paket"),
    ("users", "/users", "Användare"),
    ("services", "/services", "Tjänster"),
    ("firewall", "/firewall", "Brandvägg"),
    ("logs", "/logs", "Loggar"),
    ("terminal", "/terminal", "Terminal"),
]


class LoginRequired(Exception):
    pass


def current_user(request: Request) -> str:
    user = request.session.get("user")
    if not user:
        raise LoginRequired
    return user


async def csrf_protect(request: Request):
    if request.method in ("GET", "HEAD"):
        return
    token = request.headers.get("x-csrf-token")
    if token is None:
        token = (await request.form()).get("csrf")
    if not token or token != request.session.get("csrf"):
        raise HTTPException(403, "Ogiltig CSRF-token")


def ws_user(ws: WebSocket) -> str | None:
    """Användaren för en WebSocket, eller None. Kräver samma origin (skydd mot CSWSH)."""
    origin = ws.headers.get("origin")
    if not origin or urlparse(origin).netloc != ws.headers.get("host"):
        return None
    return ws.session.get("user")


def render(request: Request, name: str, **ctx):
    return templates.TemplateResponse(
        request,
        name,
        {
            "user": request.session.get("user"),
            "csrf": request.session.get("csrf", ""),
            "nav": NAV,
            "dev": DEV,
            "hostname": socket.gethostname(),
            **ctx,
        },
    )


def result(request: Request, ok: bool, title: str, output: str = ""):
    """Svar på en åtgärd: visa en notis och be sidans tabeller ladda om."""
    resp = render(request, "_result.html", ok=ok, title=title, output=output.strip())
    resp.headers["HX-Trigger"] = "refresh"
    return resp
