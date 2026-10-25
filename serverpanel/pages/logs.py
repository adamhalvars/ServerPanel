import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, Request, WebSocket

from ..system import run, stream
from ..web import current_user, render, ws_user

router = APIRouter()

UNIT_RE = re.compile(r"^[A-Za-z0-9@_.:\\\-]{1,200}$")
PRIORITIES = [(0, "emerg"), (1, "alert"), (2, "crit"), (3, "err"),
              (4, "warning"), (5, "notice"), (6, "info"), (7, "debug")]


def journal_args(unit: str, priority: int) -> list[str] | None:
    args = ["--no-pager", "-o", "json", f"--priority={max(0, min(priority, 7))}"]
    unit = unit.strip()
    if unit:
        if not UNIT_RE.match(unit):
            return None
        args.append(f"--unit={unit}")
    return args


def parse_entry(line: str):
    try:
        e = json.loads(line)
    except ValueError:
        return None
    msg = e.get("MESSAGE", "")
    if isinstance(msg, list):  # binärt meddelande
        msg = bytes(msg).decode(errors="replace")
    ts = int(e.get("__REALTIME_TIMESTAMP", 0)) / 1_000_000
    return {
        "time": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
        "prio": int(e.get("PRIORITY", 6)),
        "ident": e.get("SYSLOG_IDENTIFIER") or e.get("_COMM") or "?",
        "msg": msg or "",
    }


@router.get("/logs")
async def logs_page(request: Request, user: str = Depends(current_user)):
    return render(request, "logs.html", page="logs", title="Loggar", priorities=PRIORITIES)


@router.get("/logs/entries")
async def log_entries(request: Request, unit: str = "", priority: int = 6, lines: int = 200,
                      user: str = Depends(current_user)):
    args = journal_args(unit, priority)
    if args is None:
        return render(request, "_log_entries.html", entries=[], error="Ogiltigt enhetsnamn")
    lines = max(10, min(lines, 2000))
    rc, out = await run(["journalctl", "-r", "-n", str(lines), *args], merge_stderr=False, timeout=30)
    entries = [e for e in map(parse_entry, out.splitlines()) if e]
    return render(request, "_log_entries.html", entries=entries, error=None if entries or rc == 0
                  else "Kunde inte läsa journalen (är tjänstanvändaren med i gruppen systemd-journal?)")


@router.websocket("/ws/logs")
async def ws_logs(ws: WebSocket, unit: str = "", priority: int = 6):
    """Följ journalen live."""
    args = journal_args(unit, priority)
    if not ws_user(ws) or args is None:
        await ws.close(code=4401)
        return
    await ws.accept()

    async def send(line):
        entry = parse_entry(line)
        if entry:
            await ws.send_json(entry)

    await stream(["journalctl", "-f", "-n", "0", *args], send)
