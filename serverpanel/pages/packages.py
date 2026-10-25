import re
import shutil

from fastapi import APIRouter, Depends, Request, WebSocket

from ..system import helper_cmd, run, stream
from ..web import current_user, render, ws_user

router = APIRouter()

HAS_APT = shutil.which("apt-cache") is not None
QUERY_RE = re.compile(r"^[A-Za-z0-9+.\-]{2,64}$")
STREAM_ACTIONS = {"apt-update", "apt-upgrade", "apt-install", "apt-remove"}

# Låtsasdata när vi kör DEV-läge på en maskin utan apt.
FAKE = [
    ("htop", "3.3.0-4", "interactive processes viewer", True),
    ("nginx", "1.24.0-2ubuntu7", "small, powerful, scalable web/proxy server", False),
    ("curl", "8.5.0-2ubuntu10", "command line tool for transferring data with URL syntax", True),
    ("git", "1:2.43.0-1ubuntu7", "fast, scalable, distributed revision control system", True),
    ("postgresql", "16+257build1", "object-relational SQL database (supported version)", False),
    ("fail2ban", "1.0.2-3ubuntu0.1", "ban hosts that cause multiple authentication errors", False),
    ("neovim", "0.9.5-6ubuntu2", "heavily refactored vim fork", False),
    ("docker.io", "24.0.7-0ubuntu4", "Linux container runtime", False),
]
FAKE_UPGRADES = [
    ("openssl", "3.0.13-0ubuntu3.4", "3.0.13-0ubuntu3.5"),
    ("linux-generic", "6.8.0.45.45", "6.8.0.47.47"),
    ("curl", "8.5.0-2ubuntu10.4", "8.5.0-2ubuntu10.5"),
]


async def installed() -> dict[str, str]:
    rc, out = await run(["dpkg-query", "-W", "-f", "${Package}\t${Version}\t${db:Status-Abbrev}\n"],
                        merge_stderr=False)
    pkgs = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[2].startswith("ii"):
            pkgs[parts[0]] = parts[1]
    return pkgs


async def search(q: str):
    if not HAS_APT:
        return [{"name": n, "version": v, "desc": d, "installed": i}
                for n, v, d, i in FAKE if q.lower() in n or q.lower() in d]
    inst = await installed()
    _, out = await run(["apt-cache", "search", "--names-only", "--", q], merge_stderr=False)
    results = []
    for line in out.splitlines()[:100]:
        name, _, desc = line.partition(" - ")
        results.append({"name": name, "desc": desc, "installed": name in inst,
                        "version": inst.get(name, "")})
    results.sort(key=lambda p: (p["name"] != q, not p["name"].startswith(q), p["name"]))
    return results


async def upgradable():
    if not HAS_APT:
        return [{"name": n, "old": o, "new": v} for n, o, v in FAKE_UPGRADES]
    _, out = await run(["apt", "list", "--upgradable"], merge_stderr=False)
    pkgs = []
    for line in out.splitlines():
        m = re.match(r"^([^/\s]+)/\S+\s+(\S+)\s+\S+\s+\[upgradable from: ([^\]]+)\]", line)
        if m:
            pkgs.append({"name": m[1], "new": m[2], "old": m[3]})
    return pkgs


@router.get("/packages")
async def packages_page(request: Request, user: str = Depends(current_user)):
    count = sum(p[3] for p in FAKE) if not HAS_APT else len(await installed())
    return render(request, "packages.html", page="packages", title="Paket", installed_count=count)


@router.get("/packages/upgradable")
async def upgradable_partial(request: Request, user: str = Depends(current_user)):
    return render(request, "_pkg_upgradable.html", pkgs=await upgradable())


@router.get("/packages/search")
async def search_partial(request: Request, q: str = "", user: str = Depends(current_user)):
    q = q.strip()
    if not q:
        return render(request, "_pkg_search.html", results=None, error=None)
    if not QUERY_RE.match(q):
        return render(request, "_pkg_search.html", results=None,
                      error="Sök med minst 2 tecken: bokstäver, siffror, + . -")
    return render(request, "_pkg_search.html", results=await search(q), error=None)


@router.websocket("/ws/run")
async def ws_run(ws: WebSocket):
    """Kör en apt-åtgärd och strömma utdata rad för rad."""
    if not ws_user(ws):
        await ws.close(code=4401)
        return
    await ws.accept()
    req = await ws.receive_json()
    action, args = req.get("action"), req.get("args") or []
    if action not in STREAM_ACTIONS or not isinstance(args, list) or len(args) > 20 \
            or not all(isinstance(a, str) for a in args):
        await ws.send_json({"line": "Ogiltig begäran", "done": 2})
        await ws.close()
        return

    async def send(line):
        await ws.send_json({"line": line})

    rc = await stream(helper_cmd(action, *args), send)
    await ws.send_json({"done": rc})
    await ws.close()
