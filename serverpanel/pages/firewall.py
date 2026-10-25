import re

from fastapi import APIRouter, Depends, Form, Request

from ..system import run_helper
from ..web import csrf_protect, current_user, render, result

router = APIRouter(dependencies=[Depends(current_user), Depends(csrf_protect)])

RULE_RE = re.compile(r"^\[\s*(\d+)\]\s+(.+?)\s{2,}(ALLOW|DENY|REJECT|LIMIT)(?: (IN|OUT|FWD))?\s+(.+)$")


def parse_status(out: str):
    active = "Status: active" in out
    rules = []
    for line in out.splitlines():
        m = RULE_RE.match(line.strip())
        if m:
            rules.append({"num": m[1], "to": m[2], "action": m[3],
                          "dir": m[4] or "IN", "src": m[5]})
    return active, rules


@router.get("/firewall")
async def firewall_page(request: Request):
    return render(request, "firewall.html", page="firewall", title="Brandvägg")


@router.get("/firewall/status")
async def firewall_status(request: Request):
    rc, out = await run_helper("ufw-status", timeout=20)
    if rc != 0:
        return render(request, "_fw_status.html", error=out or "ufw svarade inte", active=False, rules=[])
    active, rules = parse_status(out)
    return render(request, "_fw_status.html", error=None, active=active, rules=rules)


@router.post("/firewall/toggle")
async def firewall_toggle(request: Request, enable: bool = Form(...)):
    rc, out = await run_helper("ufw-enable" if enable else "ufw-disable")
    title = ("Brandväggen aktiverades" if enable else "Brandväggen stängdes av") if rc == 0 \
        else "Kunde inte ändra brandväggen"
    return result(request, rc == 0, title, out)


@router.post("/firewall/rule")
async def firewall_rule(request: Request, port: str = Form(...), action: str = Form(...)):
    rc, out = await run_helper("ufw-rule", action, port.strip())
    label = "tillåts" if action == "allow" else "blockeras"
    return result(request, rc == 0, f"Port {port} {label}" if rc == 0 else "Kunde inte lägga till regeln", out)


@router.post("/firewall/delete")
async def firewall_delete(request: Request, num: str = Form(...)):
    rc, out = await run_helper("ufw-delete", num)
    return result(request, rc == 0, f"Regel {num} togs bort" if rc == 0 else "Kunde inte ta bort regeln", out)
