"""Privilegierad hjälpare för Serverpanel.

Körs som root via sudo (se deploy/sudoers). Det här är säkerhetsgränsen:
bara åtgärderna i ACTIONS går att köra och varje argument valideras mot
en strikt regex. Inget skickas någonsin genom ett shell.

Användning: helper.py <åtgärd> [argument ...]

Får bara använda standardbiblioteket (plus python-pam för inloggning),
eftersom den startas med `python -I`.
"""

import os
import pwd
import re
import shlex
import subprocess
import sys
import time

PKG_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]{0,99}$")
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
UNIT_RE = re.compile(r"^[A-Za-z0-9@_.:\\\-]{1,200}\.service$")
PORT_RE = re.compile(r"^\d{1,5}(:\d{1,5})?(/(tcp|udp))?$")
RULE_NUM_RE = re.compile(r"^\d{1,4}$")

SVC_VERBS = {"start", "stop", "restart", "enable", "disable"}

# Simulera bara när vi uttryckligen är i DEV-läge OCH inte är root.
# sudo nollställer miljön, så variabeln kan inte smugglas in i produktion.
SIMULATE = os.geteuid() != 0 and os.environ.get("SERVERPANEL_DEV") == "1"

APT_ENV = {
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "DEBIAN_FRONTEND": "noninteractive",
    "LANG": "C.UTF-8",
}


class Refused(Exception):
    pass


def check(regex, values, what):
    if not values:
        raise Refused(f"Saknar {what}")
    for v in values:
        if not regex.match(v):
            raise Refused(f"Ogiltigt {what}: {v!r}")


def read_secret_lines(n):
    lines = [sys.stdin.readline().rstrip("\n") for _ in range(n)]
    if any("\r" in s for s in lines):
        raise Refused("Ogiltig indata")
    return lines


def execute(*cmds, env=None, stdin=None):
    """Kör kommandona i tur och ordning; avbryt vid första fel."""
    for cmd in cmds:
        print(f"$ {shlex.join(cmd)}", flush=True)
        if SIMULATE:
            simulate(cmd)
            continue
        rc = subprocess.run(cmd, env=env or APT_ENV, input=stdin, text=True).returncode
        if rc != 0:
            return rc
    return 0


def simulate(cmd):
    print("[DEV] simulerar, inget körs på riktigt", flush=True)
    if cmd[0] == "apt-get":
        for i in range(1, 6):
            time.sleep(0.4)
            print(f"[DEV] {cmd[1]}: steg {i}/5 ...", flush=True)
    print("[DEV] klart", flush=True)


def require_regular_user(name):
    try:
        pw = pwd.getpwnam(name)
    except KeyError:
        raise Refused(f"Användaren {name!r} finns inte")
    if pw.pw_uid < 1000 or pw.pw_uid == 65534:
        raise Refused("Systemanvändare får inte ändras härifrån")


# --- Åtgärder ---------------------------------------------------------------

AUTH_FAILED = 3  # skiljer fel lösenord från t.ex. sudo-fel (rc 1)


def a_auth(args):
    user, password = sys.stdin.readline().rstrip("\n"), sys.stdin.readline().rstrip("\n")
    check(USER_RE, [user], "användarnamn")
    if SIMULATE:
        return 0 if password == os.environ.get("SERVERPANEL_DEV_PASSWORD", "dev") else AUTH_FAILED
    import pam

    p = pam.pam()
    if p.authenticate(user, password, service="serverpanel"):
        return 0
    print(f"PAM: {p.reason}", file=sys.stderr)
    return AUTH_FAILED


def a_apt_update(args):
    return execute(["apt-get", "update"])


def a_apt_upgrade(args):
    return execute(["apt-get", "-y", "upgrade"])


def a_apt_install(args):
    check(PKG_RE, args, "paketnamn")
    return execute(["apt-get", "install", "-y", "--", *args])


def a_apt_remove(args):
    check(PKG_RE, args, "paketnamn")
    return execute(["apt-get", "remove", "-y", "--", *args])


def a_user_add(args):
    # args: <namn> [sudo]; lösenordet läses från stdin.
    if len(args) not in (1, 2) or (len(args) == 2 and args[1] != "sudo"):
        raise Refused("Användning: user-add <namn> [sudo]")
    name = args[0]
    check(USER_RE, [name], "användarnamn")
    (password,) = read_secret_lines(1)
    if not password:
        raise Refused("Lösenord krävs")
    cmds = [["useradd", "-m", "-s", "/bin/bash", "--", name]]
    if len(args) == 2:
        cmds.append(["usermod", "-aG", "sudo", "--", name])
    rc = execute(*cmds)
    if rc == 0:
        rc = execute(["chpasswd"], stdin=f"{name}:{password}\n")
    return rc


def a_user_del(args):
    check(USER_RE, args[:1], "användarnamn")
    if len(args) != 1:
        raise Refused("Användning: user-del <namn>")
    require_regular_user(args[0])
    return execute(["userdel", "-r", "--", args[0]])


def a_svc(args):
    if len(args) != 2 or args[0] not in SVC_VERBS:
        raise Refused(f"Användning: svc <{'|'.join(sorted(SVC_VERBS))}> <enhet>")
    check(UNIT_RE, args[1:], "enhet")
    return execute(["systemctl", args[0], "--", args[1]])


def a_ufw_status(args):
    if SIMULATE:
        print("Status: active\n")
        print("     To                         Action      From")
        print("     --                         ------      ----")
        print("[ 1] 22/tcp                     ALLOW IN    Anywhere")
        print("[ 2] 9090/tcp                   ALLOW IN    Anywhere")
        print("[ 3] 22/tcp (v6)                ALLOW IN    Anywhere (v6)")
        return 0
    return subprocess.run(["ufw", "status", "numbered"], env=APT_ENV).returncode


def a_ufw_enable(args):
    return execute(["ufw", "--force", "enable"])


def a_ufw_disable(args):
    return execute(["ufw", "disable"])


def a_ufw_rule(args):
    if len(args) != 2 or args[0] not in ("allow", "deny"):
        raise Refused("Användning: ufw-rule <allow|deny> <port[/proto]>")
    check(PORT_RE, args[1:], "port")
    return execute(["ufw", args[0], args[1]])


def a_ufw_delete(args):
    check(RULE_NUM_RE, args, "regelnummer")
    return execute(["ufw", "--force", "delete", args[0]])


def a_terminal(args):
    check(USER_RE, args, "användarnamn")
    if SIMULATE:
        shell = os.environ.get("SHELL", "/bin/bash")
        os.execvp(shell, [shell, "-l"])
    pwd.getpwnam(args[0])
    os.execvp("runuser", ["runuser", "-l", "--", args[0]])


ACTIONS = {
    "auth": a_auth,
    "apt-update": a_apt_update,
    "apt-upgrade": a_apt_upgrade,
    "apt-install": a_apt_install,
    "apt-remove": a_apt_remove,
    "user-add": a_user_add,
    "user-del": a_user_del,
    "svc": a_svc,
    "ufw-status": a_ufw_status,
    "ufw-enable": a_ufw_enable,
    "ufw-disable": a_ufw_disable,
    "ufw-rule": a_ufw_rule,
    "ufw-delete": a_ufw_delete,
    "terminal": a_terminal,
}


def main(argv):
    if len(argv) < 2 or argv[1] not in ACTIONS:
        print(f"Okänd åtgärd. Tillåtna: {', '.join(ACTIONS)}", file=sys.stderr)
        return 2
    try:
        return ACTIONS[argv[1]](argv[2:])
    except Refused as e:
        print(f"Nekad: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
