import os
import secrets
import sys
from pathlib import Path

# DEV-läge: inget sudo, alla ändringar simuleras av hjälparen och
# inloggning sker med SERVERPANEL_DEV_PASSWORD (default "dev").
DEV = os.environ.get("SERVERPANEL_DEV") == "1"

SECRET_KEY = os.environ.get("SERVERPANEL_SECRET") or secrets.token_hex(32)

# Session-cookien skickas bara över HTTPS, utom i DEV-läge.
COOKIE_SECURE = os.environ.get("SERVERPANEL_COOKIE_SECURE", "0" if DEV else "1") == "1"

# Den som loggar in måste vara med i någon av dessa grupper.
ADMIN_GROUPS = {"sudo", "admin"}

HELPER = Path(__file__).with_name("helper.py")

# Måste matcha sudoers-regeln exakt. sys.executable duger inte: den beror på
# hur processen startades (uvicorn-skriptet använder t.ex. bin/python3).
HELPER_PYTHON = Path(sys.prefix) / "bin" / "python3"
