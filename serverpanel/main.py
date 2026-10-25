import asyncio
import grp
import logging
import pwd
import re
import secrets

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from starlette.middleware.sessions import SessionMiddleware

from .config import ADMIN_GROUPS, COOKIE_SECURE, DEV, SECRET_KEY
from .pages import firewall, logs, overview, packages, services, terminal, users
from .system import run_helper
from .web import LoginRequired, csrf_protect, render

USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
AUTH_FAILED = 3  # samma som i helper.py

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Serverpanel", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="serverpanel",
    max_age=8 * 3600,
    same_site="strict",
    https_only=COOKIE_SECURE,
)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

for module in (overview, packages, users, services, firewall, logs, terminal):
    app.include_router(module.router)


@app.exception_handler(LoginRequired)
async def login_required(request: Request, exc: LoginRequired):
    if request.headers.get("hx-request"):
        return Response(status_code=401, headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)


def is_admin(username: str) -> bool:
    try:
        primary = grp.getgrgid(pwd.getpwnam(username).pw_gid).gr_name
    except KeyError:
        return False
    groups = {g.gr_name for g in grp.getgrall() if username in g.gr_mem} | {primary}
    return bool(groups & ADMIN_GROUPS)


@app.get("/login")
async def login_page(request: Request):
    return render(request, "login.html", error=None)


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    error = None
    if not USER_RE.match(username) or "\n" in password:
        error = "Fel användarnamn eller lösenord"
    else:
        rc, out = await run_helper("auth", input=f"{username}\n{password}\n", timeout=15)
        if rc == AUTH_FAILED:
            log.info("Misslyckad inloggning för %s: %s", username, out.strip())
            error = "Fel användarnamn eller lösenord"
        elif rc != 0:
            log.error("Hjälparen kunde inte köras (rc=%s): %s", rc, out.strip())
            error = "Internt fel vid inloggning, se: journalctl -u serverpanel"
        elif not DEV and not is_admin(username):
            error = "Användaren måste vara med i gruppen sudo"
    if error:
        await asyncio.sleep(1)  # bromsa gissningsattacker
        return render(request, "login.html", error=error, username=username)
    request.session.clear()
    request.session.update(user=username, csrf=secrets.token_hex(16))
    return RedirectResponse("/", status_code=303)


@app.post("/logout", dependencies=[Depends(csrf_protect)])
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
