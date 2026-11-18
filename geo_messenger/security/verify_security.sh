#!/usr/bin/env bash
set -uo pipefail

APP_DIR="${APP_DIR:-/opt/geo-messenger}"
DATA_DIR="/var/lib/geo-messenger"
ENV_FILE="${APP_DIR}/.env"
SERVICE_NAME="geo-messenger.service"
USE_WEBHOOK="${USE_WEBHOOK:-}"
passed=0
failed=0

report() {
    local label="$1"
    local result="$2"
    if [[ "$result" == "true" ]]; then
        printf 'PASS: %s\n' "$label"
        passed=$((passed + 1))
    else
        printf 'FAIL: %s\n' "$label"
        failed=$((failed + 1))
    fi
}

read_env_value() {
    local key="$1"
    local file="$2"
    sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$file" \
        | tail -n 1 | sed -E 's/^["'\'']|["'\'']$//g' | tr -d '\r'
}

if [[ -z "$USE_WEBHOOK" && -f "$ENV_FILE" ]]; then
    USE_WEBHOOK="$(read_env_value USE_WEBHOOK "$ENV_FILE")"
fi
USE_WEBHOOK="${USE_WEBHOOK:-false}"

ufw_status="$(ufw status verbose 2>/dev/null || true)"
report "UFW активен" "$(grep -q '^Status: active' <<<"$ufw_status" && echo true || echo false)"
report "Политика входящих соединений — deny" \
    "$(grep -Eiq 'Default:[[:space:]]+deny \(incoming\)' <<<"$ufw_status" && echo true || echo false)"

printf '\nСлушающие порты (ss -tulpn):\n'
ss_output="$(ss -tulpn 2>/dev/null || true)"
printf '%s\n' "$ss_output"
expected_ports=(22)
if [[ "${USE_WEBHOOK,,}" == "true" ]]; then
    expected_ports+=(443)
fi
unexpected_port=false
observed_ports=()
while IFS= read -r line; do
    [[ "$line" == Netid* || -z "$line" ]] && continue
    local_endpoint="$(awk '{print $5}' <<<"$line")"
    port="${local_endpoint##*:}"
    [[ "$port" =~ ^[0-9]+$ ]] || continue
    observed_ports+=("$port")
    allowed=false
    for expected in "${expected_ports[@]}"; do
        [[ "$port" == "$expected" ]] && allowed=true
    done
    [[ "$allowed" == "true" ]] || unexpected_port=true
done <<<"$ss_output"
missing_expected_port=false
for expected in "${expected_ports[@]}"; do
    found=false
    for observed in "${observed_ports[@]}"; do
        [[ "$expected" == "$observed" ]] && found=true
    done
    [[ "$found" == "true" ]] || missing_expected_port=true
done
report "Слушают только ожидаемые порты (${expected_ports[*]})" \
    "$([[ "$unexpected_port" == "false" && "$missing_expected_port" == "false" ]] && echo true || echo false)"

sshd_effective="$(sshd -T 2>/dev/null || true)"
report "SSH: PasswordAuthentication отключён" \
    "$(grep -Fxq 'passwordauthentication no' <<<"$sshd_effective" && echo true || echo false)"
report "SSH: PermitRootLogin отключён" \
    "$(grep -Fxq 'permitrootlogin no' <<<"$sshd_effective" && echo true || echo false)"
report "Fail2ban запущен" \
    "$(systemctl is-active --quiet fail2ban && echo true || echo false)"

db_path=""
if [[ -f "$ENV_FILE" ]]; then
    db_path="$(read_env_value DATABASE_PATH "$ENV_FILE")"
fi
env_permissions=false
if [[ -f "$ENV_FILE" ]] \
    && [[ "$(stat -c '%a:%U' "$ENV_FILE" 2>/dev/null)" == "600:geobot" ]]; then
    env_permissions=true
fi
report ".env принадлежит geobot и имеет права 600" "$env_permissions"

db_permissions=false
if [[ -n "$db_path" && -f "$db_path" ]] \
    && [[ "$(stat -c '%a:%U' "$db_path" 2>/dev/null)" == "600:geobot" ]]; then
    db_permissions=true
fi
report "Файл БД принадлежит geobot и имеет права 600" "$db_permissions"

service_user="$(systemctl show -p User --value "$SERVICE_NAME" 2>/dev/null || true)"
service_active="$(systemctl is-active --quiet "$SERVICE_NAME" && echo true || echo false)"
service_pid="$(systemctl show -p MainPID --value "$SERVICE_NAME" 2>/dev/null || true)"
process_user=""
if [[ "$service_pid" =~ ^[1-9][0-9]*$ ]]; then
    process_user="$(ps -o user= -p "$service_pid" 2>/dev/null | tr -d '[:space:]')"
fi
report "Сервис активен и настроен не от root" \
    "$([[ "$service_user" == "geobot" && "$process_user" == "geobot" && "$service_active" == "true" ]] && echo true || echo false)"

printf '\nИтог: PASS=%s FAIL=%s\n' "$passed" "$failed"
[[ "$failed" -eq 0 ]]
