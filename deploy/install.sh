#!/usr/bin/env bash
# Installerar Serverpanel på Ubuntu. Kör som root från projektets rotkatalog:
#   sudo ./deploy/install.sh
set -euo pipefail

PREFIX=/opt/serverpanel
CONF=/etc/serverpanel

[[ $EUID -eq 0 ]] || { echo "Kör som root (sudo)"; exit 1; }

apt-get update
apt-get install -y python3-venv ufw openssl

id serverpanel &>/dev/null || useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin serverpanel

# Koden ägs av root så att tjänstanvändaren inte kan ändra hjälparen.
install -d -o root -g root -m 755 "$PREFIX"
cp -r serverpanel pyproject.toml "$PREFIX"/
chown -R root:root "$PREFIX"
chmod -R go-w "$PREFIX"
python3 -m venv "$PREFIX/.venv"
"$PREFIX/.venv/bin/pip" install --quiet -e "$PREFIX"  # editable: koden körs från $PREFIX/serverpanel, som sudo-regeln pekar på

install -m 644 deploy/pam-serverpanel /etc/pam.d/serverpanel
install -m 440 deploy/sudoers /etc/sudoers.d/serverpanel
visudo -cf /etc/sudoers.d/serverpanel

install -d -o root -g serverpanel -m 750 "$CONF"
if [[ ! -f $CONF/env ]]; then
    echo "SERVERPANEL_SECRET=$(openssl rand -hex 32)" > "$CONF/env"
    chmod 640 "$CONF/env"; chgrp serverpanel "$CONF/env"
fi
if [[ ! -f $CONF/cert.pem ]]; then
    openssl req -x509 -newkey rsa:3072 -nodes -days 825 -subj "/CN=$(hostname -f)" \
        -keyout "$CONF/key.pem" -out "$CONF/cert.pem"
    chgrp serverpanel "$CONF/key.pem"; chmod 640 "$CONF/key.pem"
fi

install -m 644 deploy/serverpanel.service /etc/systemd/system/serverpanel.service
systemctl daemon-reload
systemctl enable --now serverpanel

echo
echo "Klart! Öppna https://$(hostname -I | awk '{print $1}'):9090"
echo "Logga in med en användare som är med i gruppen sudo."
echo "Tips: om ufw är aktivt, kör 'ufw allow 9090/tcp' först."
