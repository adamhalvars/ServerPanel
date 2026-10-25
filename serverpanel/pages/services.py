from fastapi import APIRouter, Depends, Form, Request

from ..system import run, run_helper
from ..web import csrf_protect, current_user, render, result

router = APIRouter(dependencies=[Depends(current_user), Depends(csrf_protect)])

VERB_LABELS = {"start": "startades", "stop": "stoppades", "restart": "startades om",
               "enable": "aktiverades vid uppstart", "disable": "inaktiverades vid uppstart"}


async def list_services():
    _, units = await run(["systemctl", "list-units", "--type=service", "--all",
                          "--no-legend", "--plain", "--no-pager"], merge_stderr=False)
    _, files = await run(["systemctl", "list-unit-files", "--type=service",
                          "--no-legend", "--plain", "--no-pager"], merge_stderr=False)
    enabled = {}
    for line in files.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            enabled[parts[0]] = parts[1]
    services = []
    for line in units.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 4 or not parts[0].endswith(".service"):
            continue
        services.append({
            "unit": parts[0],
            "load": parts[1],
            "active": parts[2],
            "sub": parts[3],
            "desc": parts[4] if len(parts) > 4 else "",
            "enabled": enabled.get(parts[0], "-"),
        })
    return services


def apply_filter(services, q, state):
    q = q.lower().strip()
    if q:
        services = [s for s in services if q in s["unit"].lower() or q in s["desc"].lower()]
    if state == "running":
        services = [s for s in services if s["sub"] == "running"]
    elif state == "failed":
        services = [s for s in services if s["active"] == "failed"]
    elif state == "inactive":
        services = [s for s in services if s["active"] == "inactive"]
    return services


@router.get("/services")
async def services_page(request: Request):
    services = await list_services()
    return render(request, "services.html", page="services", title="Tjänster",
                  services=apply_filter(services, "", "running"),
                  failed=sum(s["active"] == "failed" for s in services))


@router.get("/services/table")
async def services_table(request: Request, q: str = "", state: str = "running"):
    return render(request, "_services_table.html",
                  services=apply_filter(await list_services(), q, state))


@router.post("/services/action")
async def service_action(request: Request, unit: str = Form(...), verb: str = Form(...)):
    rc, out = await run_helper("svc", verb, unit)
    if rc == 0:
        return result(request, True, f"{unit} {VERB_LABELS.get(verb, verb)}", out)
    return result(request, False, f"Misslyckades: systemctl {verb} {unit}", out)
