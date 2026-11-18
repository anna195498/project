#!/usr/bin/env bash
set -Eeuo pipefail

SSHD_CONFIG="/etc/ssh/sshd_config"
DROPIN_DIR="/etc/ssh/sshd_config.d"
DROPIN_FILE="${DROPIN_DIR}/00-geo-messenger-hardening.conf"
BACKUP_DIR="/var/backups/geo-messenger-ssh"

fail() {
    printf 'ОШИБКА: %s\n' "$*" >&2
    exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "Запустите скрипт от root: sudo bash security/harden_ssh.sh"
fi
[[ -f "$SSHD_CONFIG" ]] || fail "Не найден $SSHD_CONFIG"
grep -Eq '^[[:space:]]*Include[[:space:]]+/etc/ssh/sshd_config\.d/\*\.conf' \
    "$SSHD_CONFIG" || fail "В sshd_config нет стандартного Include для sshd_config.d"

install -d -m 700 "$BACKUP_DIR"
SSHD_BACKUP="${BACKUP_DIR}/sshd_config.before-geo-messenger"
DROPIN_BACKUP="${BACKUP_DIR}/00-hardening.before-geo-messenger.conf"
DROPIN_ABSENT_MARKER="${BACKUP_DIR}/00-hardening.was-absent"
[[ -e "$SSHD_BACKUP" ]] || cp -a "$SSHD_CONFIG" "$SSHD_BACKUP"
if [[ -e "$DROPIN_ABSENT_MARKER" ]]; then
    had_dropin=false
elif [[ -e "$DROPIN_FILE" ]]; then
    if [[ ! -e "$DROPIN_BACKUP" ]]; then
        cp -a "$DROPIN_FILE" "$DROPIN_BACKUP"
    fi
    had_dropin=true
else
    touch "$DROPIN_ABSENT_MARKER"
    had_dropin=false
fi

restore_on_error() {
    cp -a "$SSHD_BACKUP" "$SSHD_CONFIG"
    if [[ "$had_dropin" == "true" ]]; then
        cp -a "$DROPIN_BACKUP" "$DROPIN_FILE"
    else
        rm -f "$DROPIN_FILE"
    fi
}

install -d -m 755 "$DROPIN_DIR"
cat > "$DROPIN_FILE" <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
EOF
chmod 644 "$DROPIN_FILE"

if ! sshd -t -f "$SSHD_CONFIG"; then
    restore_on_error
    fail "sshd -t завершился ошибкой; восстановлена предыдущая конфигурация"
fi

if ! effective_config="$(sshd -T -f "$SSHD_CONFIG")"; then
    restore_on_error
    fail "Не удалось получить эффективную конфигурацию SSH; изменения отменены"
fi
for setting in \
    "passwordauthentication no" \
    "kbdinteractiveauthentication no" \
    "permitrootlogin no" \
    "pubkeyauthentication yes"; do
    grep -Fxq "$setting" <<<"$effective_config" || {
        restore_on_error
        fail "Эффективная конфигурация не содержит: $setting; изменения отменены"
    }
done

printf '%s\n' \
    "Конфигурация проверена командой sshd -t." \
    "Откройте отдельную SSH-сессию и подтвердите вход по ключу." \
    "Не закрывайте текущую сессию. Только после проверки подтвердите reload."
if [[ "${CONFIRM_SSH_RELOAD:-}" != "YES" ]]; then
    read -r -p "Введите YES, чтобы перечитать конфигурацию SSH: " confirmation
    [[ "$confirmation" == "YES" ]] || {
        printf 'Конфигурация сохранена, sshd не перезапускался.\n'
        exit 0
    }
fi

if systemctl list-unit-files ssh.service --no-legend | grep -q '^ssh\.service'; then
    systemctl reload ssh
else
    systemctl reload sshd
fi
printf 'PASS: sshd_config проверен; ограничения SSH применены.\n'
