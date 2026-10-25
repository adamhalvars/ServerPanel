import os
import platform
import time

import psutil
from fastapi import APIRouter, Depends, Request

from ..web import current_user, render

router = APIRouter(dependencies=[Depends(current_user)])

psutil.cpu_percent(interval=None)  # första anropet ger alltid 0


def fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


def fmt_duration(seconds: float) -> str:
    d, rem = divmod(int(seconds), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return f"{d} d {h} h {m} min" if d else f"{h} h {m} min"


def system_info():
    try:
        os_name = platform.freedesktop_os_release().get("PRETTY_NAME", "Linux")
    except OSError:
        os_name = "Linux"
    return {
        "Operativsystem": os_name,
        "Kärna": platform.release(),
        "Arkitektur": platform.machine(),
        "CPU-kärnor": psutil.cpu_count(),
        "Startad": time.strftime("%Y-%m-%d %H:%M", time.localtime(psutil.boot_time())),
    }


def stats():
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disks, seen = [], set()
    for p in psutil.disk_partitions():
        if p.device in seen or p.mountpoint.startswith(("/snap", "/boot/efi")):
            continue
        seen.add(p.device)
        try:
            u = psutil.disk_usage(p.mountpoint)
        except OSError:
            continue
        disks.append({"mount": p.mountpoint, "pct": u.percent,
                      "text": f"{fmt_bytes(u.used)} av {fmt_bytes(u.total)}"})
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "load": " / ".join(f"{x:.2f}" for x in os.getloadavg()),
        "mem_pct": vm.percent,
        "mem_text": f"{fmt_bytes(vm.total - vm.available)} av {fmt_bytes(vm.total)}",
        "swap_pct": swap.percent,
        "swap_text": f"{fmt_bytes(swap.used)} av {fmt_bytes(swap.total)}",
        "uptime": fmt_duration(time.time() - psutil.boot_time()),
        "disks": disks,
    }


@router.get("/")
async def overview(request: Request):
    return render(request, "overview.html", page="overview", title="Översikt",
                  info=system_info(), s=stats())


@router.get("/partials/stats")
async def stats_partial(request: Request):
    return render(request, "_stats.html", s=stats())
