"""Körning av kommandon, med och utan root-hjälparen."""

import asyncio
from asyncio.subprocess import DEVNULL, PIPE, STDOUT

from .config import DEV, HELPER, HELPER_PYTHON


def helper_cmd(action, *args):
    cmd = [str(HELPER_PYTHON), "-I", str(HELPER), action, *args]
    return cmd if DEV else ["sudo", "-n", *cmd]


async def run(cmd, input=None, timeout=120, merge_stderr=True):
    """Kör ett kommando och returnera (returkod, utdata)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=PIPE if input is not None else DEVNULL,
        stdout=PIPE,
        stderr=STDOUT if merge_stderr else DEVNULL,
    )
    try:
        out, _ = await asyncio.wait_for(
            proc.communicate(input.encode() if input is not None else None), timeout
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "Tidsgränsen överskreds"
    return proc.returncode, out.decode(errors="replace")


async def run_helper(action, *args, input=None, timeout=120):
    return await run(helper_cmd(action, *args), input=input, timeout=timeout)


async def stream(cmd, on_line):
    """Kör ett kommando och anropa `await on_line(rad)` för varje rad. Returnerar returkoden."""
    proc = await asyncio.create_subprocess_exec(*cmd, stdin=DEVNULL, stdout=PIPE, stderr=STDOUT)
    try:
        async for raw in proc.stdout:
            await on_line(raw.decode(errors="replace").rstrip("\n"))
        return await proc.wait()
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
