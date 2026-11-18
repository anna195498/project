#!/usr/bin/env bash
set -Eeuo pipefail

# IP администратора для SSH. Замените на свой внешний IP или передайте
# SSH_ALLOWED_IP при запуске; узнайте адрес у своего провайдера/VPN.
SSH_ALLOWED_IP="${SSH_ALLOWED_IP:-<ТВОЙ_IP>}"
STRICT_OUTBOUND="${STRICT_OUTBOUND:-false}"
USE_WEBHOOK="${USE_WEBHOOK:-}"
PROJECT_ENV_FILE="${PROJECT_ENV_FILE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env}"

# Сверить диапазоны с официальной документацией Telegram перед применением.
# Заполните фактическими CIDR только если USE_WEBHOOK=true.
TELEGRAM_WEBHOOK_CIDRS=("<ЗАМЕНИТЬ_НА_CIDR_ИЗ_ДОКУМЕНТАЦИИ_TELEGRAM>")

fail() {
    printf 'ОШИБКА: %s\n' "$*" >&2
    exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "Запустите скрипт от root: sudo bash security/setup_firewall.sh"
fi

if [[ -z "$USE_WEBHOOK" && -f "$PROJECT_ENV_FILE" ]]; then
    USE_WEBHOOK="$(
        sed -n 's/^[[:space:]]*USE_WEBHOOK[[:space:]]*=[[:space:]]*//p' \
            "$PROJECT_ENV_FILE" | tail -n 1 | tr -d "\"'[:space:]"
    )"
fi
USE_WEBHOOK="${USE_WEBHOOK:-false}"

case "${USE_WEBHOOK,,}" in
    true|false) ;;
    *) fail "USE_WEBHOOK должен быть true или false" ;;
esac
case "${STRICT_OUTBOUND,,}" in
    true|false) ;;
    *) fail "STRICT_OUTBOUND должен быть true или false" ;;
esac

[[ "$SSH_ALLOWED_IP" != *"<"* && "$SSH_ALLOWED_IP" != *">"* ]] \
    || fail "Замените плейсхолдер SSH_ALLOWED_IP в начале скрипта или передайте его через окружение"
python3 -c 'import ipaddress,sys; ipaddress.ip_network(sys.argv[1], strict=False)' \
    "$SSH_ALLOWED_IP" \
    || fail "SSH_ALLOWED_IP должен быть IP-адресом или CIDR-сетью"

if [[ "${USE_WEBHOOK,,}" == "true" ]]; then
    for cidr in "${TELEGRAM_WEBHOOK_CIDRS[@]}"; do
        [[ "$cidr" != *"<"* && "$cidr" != *">"* ]] \
            || fail "Заполните TELEGRAM_WEBHOOK_CIDRS подтвержденными CIDR из документации Telegram"
        python3 -c 'import ipaddress,sys; ipaddress.ip_network(sys.argv[1], strict=False)' \
            "$cidr" || fail "Некорректный CIDR в TELEGRAM_WEBHOOK_CIDRS"
    done
fi

if ! command -v ufw >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y ufw
fi

printf '%s\n' \
    "ВНИМАНИЕ: включение UFW может закрыть текущий SSH-доступ." \
    "Убедитесь, что SSH_ALLOWED_IP — ваш внешний IP и есть доступ к консоли VPS." \
    "Проверьте вход по SSH в отдельной сессии до продолжения."
if [[ "${CONFIRM_FIREWALL:-}" != "YES" ]]; then
    read -r -p "Введите YES, чтобы настроить и включить файервол: " confirmation
    [[ "$confirmation" == "YES" ]] || fail "Операция отменена"
fi

# Настраиваем разрешающие правила до включения UFW, чтобы не потерять SSH.
ufw default deny incoming
if [[ "${STRICT_OUTBOUND,,}" == "true" ]]; then
    ufw default deny outgoing
    ufw allow out 443/tcp
    ufw allow out 80/tcp
    ufw allow out 53/tcp
    ufw allow out 53/udp
    ufw allow out 123/udp
else
    ufw default allow outgoing
fi

ufw allow from "$SSH_ALLOWED_IP" to any port 22 proto tcp
if [[ "${USE_WEBHOOK,,}" == "true" ]]; then
    for cidr in "${TELEGRAM_WEBHOOK_CIDRS[@]}"; do
        ufw allow from "$cidr" to any port 443 proto tcp
    done
fi

ufw logging on
ufw --force enable
ufw status verbose
