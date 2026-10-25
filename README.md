# Serverpanel

En webbkonsol för Ubuntu-servrar, inspirerad av Fedoras Cockpit. Det här är en POC.

**Moduler:** översikt (CPU, minne, diskar), paket (apt), användare, tjänster (systemd),
brandvägg (ufw), loggar (journalctl, även live) och en terminal i webbläsaren.

## Arkitektur

```
Webbläsare ──HTTPS/WebSocket──> FastAPI (användaren serverpanel, ej root)
                                   │  läser: psutil, pwd/grp, systemctl, journalctl, apt-cache
                                   │
                                   └─ sudo -n ──> helper.py (root)
                                                  vitlistade åtgärder, regex-validerade
                                                  argument, inget shell
```

- **Inloggning:** PAM via hjälparen. Bara medlemmar i gruppen `sudo` släpps in.
- **Skydd:** signerad session-cookie (HttpOnly, SameSite=strict, Secure), CSRF-token på alla
  POST-anrop och kontroll av origin på alla WebSockets.
- **Frontend:** Jinja2 + htmx, utan byggsteg. xterm.js för terminalen.

| Fil | Innehåll |
|---|---|
| `serverpanel/helper.py` | Säkerhetsgränsen. Alla root-åtgärder finns här. |
| `serverpanel/pages/*.py` | En modul per sida. |
| `serverpanel/templates/_*.html` | Delmallar som htmx byter ut. |
| `deploy/` | sudoers, PAM, systemd-tjänst och installationsskript för Ubuntu. |

## Utveckla lokalt (DEV-läge)

DEV-läget fungerar på vilken Linux som helst. Allt som kräver root simuleras, paketdata är
låtsasdata när `apt` saknas, och terminalen startar ditt eget shell.

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
SERVERPANEL_DEV=1 .venv/bin/uvicorn serverpanel.main:app --reload --port 9090
```

Öppna http://127.0.0.1:9090 och logga in med valfritt användarnamn och lösenordet `dev`.

## Installera på Ubuntu

```bash
sudo ./deploy/install.sh
```

Skriptet skapar systemanvändaren `serverpanel`, installerar till `/opt/serverpanel` (ägt av root),
lägger in sudoers- och PAM-reglerna, skapar ett självsignerat certifikat och startar tjänsten på
https://<server>:9090.

## Kända begränsningar i POC:n

- Terminalen ger ett fullständigt shell som den inloggade användaren. Det är kraftfullt, men om
  någon stjäl en session är det också farligt. Kör helst panelen bakom VPN eller en brandvägg.
- Ingen gräns för antalet inloggningsförsök utöver 1 s fördröjning (fail2ban rekommenderas).
- `ufw-status` kräver root och går därför via hjälparen.
