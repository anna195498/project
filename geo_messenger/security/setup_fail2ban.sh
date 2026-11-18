#!/usr/bin/env bash
set -Eeuo pipefail

JAIL_FILE="/etc/fail2ban/jail.d/geo-messenger-sshd.local"

fail() {
    printf 'ОШИБКА: %s\n' "$*" >&2
    exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "Запустите скрипт от root: sudo bash security/setup_fail2ban.sh"
fi

if ! command -v fail2ban-client >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y fail2ban
fi

install -d -m 755 /etc/fail2ban/jail.d
if [[ -e "$JAIL_FILE" && ! -e "${JAIL_FILE}.before-geo-messenger" ]]; then
    cp -a "$JAIL_FILE" "${JAIL_FILE}.before-geo-messenger"
fi
cat > "$JAIL_FILE" <<'EOF'
[sshd]
enabled = true
maxretry = 5
bantime = 1h
EOF
chmod 644 "$JAIL_FILE"

systemctl enable --now fail2ban
fail2ban-client reload
systemctl is-active --quiet fail2ban \
    || fail "Сервис fail2ban не запущен"
fail2ban-client status sshd
printf 'PASS: fail2ban запущен, jail sshd активен.\n'
