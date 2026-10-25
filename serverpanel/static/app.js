"use strict";

function wsUrl(path) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${path}`;
}

// --- Strömmade åtgärder (apt) -----------------------------------------------
// Knappar med data-action="apt-install" data-args="htop" kör åtgärden via
// /ws/run och visar utdatan live i #console.

let running = false;

document.addEventListener("click", (ev) => {
  const btn = ev.target.closest("[data-action]");
  if (!btn || running) return;
  if (btn.dataset.confirm && !confirm(btn.dataset.confirm)) return;
  const args = btn.dataset.args ? btn.dataset.args.split(" ") : [];
  runAction(btn.dataset.action, args);
});

function runAction(action, args) {
  const out = document.getElementById("console");
  running = true;
  document.querySelectorAll("[data-action]").forEach((b) => (b.disabled = true));
  out.hidden = false;
  out.textContent = `▶ ${action} ${args.join(" ")}\n`;
  out.className = "console";

  const ws = new WebSocket(wsUrl("/ws/run"));
  ws.onopen = () => ws.send(JSON.stringify({ action, args }));
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.line !== undefined) {
      out.textContent += msg.line + "\n";
      out.scrollTop = out.scrollHeight;
    }
    if (msg.done !== undefined) {
      const ok = msg.done === 0;
      out.textContent += ok ? "\n✓ Klart\n" : `\n✗ Misslyckades (kod ${msg.done})\n`;
      out.classList.add(ok ? "ok" : "err");
      out.scrollTop = out.scrollHeight;
    }
  };
  ws.onclose = () => {
    running = false;
    document.querySelectorAll("[data-action]").forEach((b) => (b.disabled = false));
    htmx.trigger(document.body, "refresh");
  };
}

// --- Loggar: följ live --------------------------------------------------------

function initLogFollow() {
  const btn = document.getElementById("follow");
  if (!btn) return;
  let ws = null;

  const stop = () => {
    if (ws) ws.close();
    ws = null;
    btn.textContent = "▶ Följ live";
    btn.classList.remove("primary");
  };

  btn.addEventListener("click", () => {
    if (ws) return stop();
    const form = new FormData(document.getElementById("log-filter"));
    const qs = new URLSearchParams({ unit: form.get("unit"), priority: form.get("priority") });
    ws = new WebSocket(wsUrl(`/ws/logs?${qs}`));
    btn.textContent = "■ Sluta följa";
    btn.classList.add("primary");
    ws.onmessage = (ev) => {
      const e = JSON.parse(ev.data);
      const tr = document.createElement("tr");
      tr.className = `p${e.prio} fresh`;
      for (const [val, cls] of [[e.time, "nowrap muted"], [e.prio, ""], [e.ident, "nowrap"], [e.msg, "msg"]]) {
        const td = document.createElement("td");
        td.textContent = val;
        td.className = cls;
        tr.appendChild(td);
      }
      document.getElementById("log-body").prepend(tr);
    };
    ws.onclose = () => { if (ws) stop(); };
  });
  document.getElementById("log-filter").addEventListener("change", stop);
}

// --- Terminal -----------------------------------------------------------------

function initTerminal() {
  const el = document.getElementById("term");
  if (!el || !window.Terminal) return;
  const term = new Terminal({
    cursorBlink: true,
    fontFamily: "ui-monospace, 'JetBrains Mono', Menlo, monospace",
    fontSize: 14,
    theme: { background: "#11141a" },
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(el);
  fit.fit();

  const ws = new WebSocket(wsUrl("/ws/terminal"));
  ws.binaryType = "arraybuffer";
  const send = (obj) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(obj));
  const resize = () => { fit.fit(); send({ t: "r", c: term.cols, r: term.rows }); };

  ws.onopen = () => { resize(); term.focus(); };
  ws.onmessage = (ev) => term.write(new Uint8Array(ev.data));
  ws.onclose = () => term.write("\r\n\x1b[33m[Sessionen avslutades]\x1b[0m\r\n");
  term.onData((d) => send({ t: "i", d }));
  window.addEventListener("resize", resize);
}

document.addEventListener("DOMContentLoaded", () => {
  initLogFollow();
  initTerminal();
});
