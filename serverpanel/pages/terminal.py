import asyncio
import fcntl
import json
import os
import pty
import struct
import termios

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect

from ..system import helper_cmd
from ..web import current_user, render, ws_user

router = APIRouter()


@router.get("/terminal")
async def terminal_page(request: Request, user: str = Depends(current_user)):
    return render(request, "terminal.html", page="terminal", title="Terminal")


@router.websocket("/ws/terminal")
async def ws_terminal(ws: WebSocket):
    """Ett riktigt shell som den inloggade användaren, via en PTY.

    Protokoll: klienten skickar JSON {"t": "i", "d": text} för tangenttryck och
    {"t": "r", "c": kolumner, "r": rader} vid storleksändring. Servern skickar råa bytes.
    """
    user = ws_user(ws)
    if not user:
        await ws.close(code=4401)
        return
    await ws.accept()

    cmd = helper_cmd("terminal", user)
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.execvpe(cmd[0], cmd, {**os.environ, "TERM": "xterm-256color"})
        finally:
            os._exit(127)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    def on_readable():
        try:
            data = os.read(fd, 65536)
        except OSError:
            data = b""
        if not data:
            loop.remove_reader(fd)
            queue.put_nowait(None)
        else:
            queue.put_nowait(data)

    loop.add_reader(fd, on_readable)

    async def pump_output():
        while (data := await queue.get()) is not None:
            await ws.send_bytes(data)
        await ws.close()

    sender = asyncio.create_task(pump_output())
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("t") == "i":
                os.write(fd, str(msg.get("d", "")).encode())
            elif msg.get("t") == "r":
                cols, rows = int(msg["c"]), int(msg["r"])
                if 0 < cols < 1000 and 0 < rows < 1000:
                    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except (WebSocketDisconnect, RuntimeError, OSError, ValueError, KeyError):
        pass
    finally:
        sender.cancel()
        loop.remove_reader(fd)
        os.close(fd)  # ger SIGHUP till shellet
        try:
            await asyncio.wait_for(asyncio.to_thread(os.waitpid, pid, 0), 5)
        except (TimeoutError, ChildProcessError):
            pass
