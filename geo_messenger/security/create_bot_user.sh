#!/usr/bin/env bash
set -Eeuo pipefail

BOT_USER="geobot"
APP_DIR="${APP_DIR:-/opt/geo-messenger}"
DATA_DIR="/var/lib/geo-messenger"
ENV_FILE="${APP_DIR}/.env"

fail() {
    printf 'ОШИБКА: %s\n' "$*" >&2
    exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
    fail "Запустите скрипт от root: sudo bash security/create_bot_user.sh"
fi
[[ -f "${APP_DIR}/main.py" ]] || fail "Сначала разместите проект в ${APP_DIR}"
[[ -f "$ENV_FILE" ]] || fail "Создайте ${ENV_FILE} из .env.example и укажите BOT_TOKEN"

if ! getent group "$BOT_USER" >/dev/null 2>&1; then
    groupadd --system "$BOT_USER"
fi
if ! id "$BOT_USER" >/dev/null 2>&1; then
    useradd --system --gid "$BOT_USER" --home-dir "$DATA_DIR" \
        --shell /usr/sbin/nologin "$BOT_USER"
fi
[[ "$(id -u "$BOT_USER")" -ne 0 ]] || fail "Отказ: geobot уже имеет UID 0"
usermod --groups "$BOT_USER" --gid "$BOT_USER" --home "$DATA_DIR" \
    --shell /usr/sbin/nologin "$BOT_USER"
if [[ "$(passwd -S "$BOT_USER" | awk '{print $2}')" != "L" ]]; then
    passwd --lock "$BOT_USER"
fi
if getent group sudo >/dev/null 2>&1 \
    && id -nG "$BOT_USER" | tr ' ' '\n' | grep -Fxq sudo; then
    gpasswd -d "$BOT_USER" sudo
fi
if id -nG "$BOT_USER" | tr ' ' '\n' | grep -Fxq wheel; then
    if getent group wheel >/dev/null 2>&1; then
        gpasswd -d "$BOT_USER" wheel
    fi
fi

install -d -o root -g "$BOT_USER" -m 750 "$APP_DIR"
chown -R root:"$BOT_USER" "$APP_DIR"
find "$APP_DIR" -type d -exec chmod 750 {} +
find "$APP_DIR" -type f -exec chmod 640 {} +
chown "$BOT_USER":"$BOT_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"

db_path="$(
    sed -n 's/^[[:space:]]*DATABASE_PATH[[:space:]]*=[[:space:]]*//p' \
        "$ENV_FILE" | tail -n 1 | sed -E 's/^["'\'']|["'\'']$//g'
)"
[[ -n "$db_path" ]] || fail "Укажите DATABASE_PATH в ${ENV_FILE}"
[[ "$db_path" == "${DATA_DIR}/"* ]] \
    || fail "DATABASE_PATH должен быть абсолютным путём внутри ${DATA_DIR}"
db_path="$(realpath -m -- "$db_path")"
[[ "$db_path" == "${DATA_DIR}/"* ]] \
    || fail "DATABASE_PATH не должен выходить за пределы ${DATA_DIR}"
db_dir="$(dirname "$db_path")"
install -d -o "$BOT_USER" -g "$BOT_USER" -m 700 "$db_dir"
if [[ ! -e "$db_path" ]]; then
    install -o "$BOT_USER" -g "$BOT_USER" -m 600 /dev/null "$db_path"
else
    chown "$BOT_USER":"$BOT_USER" "$db_path"
    chmod 600 "$db_path"
fi

use_webhook="$(
    sed -n 's/^[[:space:]]*USE_WEBHOOK[[:space:]]*=[[:space:]]*//p' \
        "$ENV_FILE" | tail -n 1 | tr -d "\"'[:space:]"
)"
if [[ "${use_webhook,,}" == "true" ]]; then
    cert_file="$(
        sed -n 's/^[[:space:]]*WEBHOOK_CERT_FILE[[:space:]]*=[[:space:]]*//p' \
            "$ENV_FILE" | tail -n 1 | sed -E 's/^["'\'']|["'\'']$//g'
    )"
    key_file="$(
        sed -n 's/^[[:space:]]*WEBHOOK_KEY_FILE[[:space:]]*=[[:space:]]*//p' \
            "$ENV_FILE" | tail -n 1 | sed -E 's/^["'\'']|["'\'']$//g'
    )"
    [[ "$cert_file" == "${DATA_DIR}/"* && -f "$cert_file" ]] \
        || fail "WEBHOOK_CERT_FILE должен существовать внутри ${DATA_DIR}"
    [[ "$key_file" == "${DATA_DIR}/"* && -f "$key_file" ]] \
        || fail "WEBHOOK_KEY_FILE должен существовать внутри ${DATA_DIR}"
    chown "$BOT_USER":"$BOT_USER" "$cert_file" "$key_file"
    chmod 600 "$cert_file" "$key_file"
fi

[[ "$(stat -c '%a' "$ENV_FILE")" == "600" ]] \
    || fail "Права .env должны быть 600"
[[ "$(stat -c '%a' "$db_path")" == "600" ]] \
    || fail "Права файла БД должны быть 600"
! id -nG "$BOT_USER" | tr ' ' '\n' | grep -Eq '^(sudo|wheel)$' \
    || fail "Пользователь ${BOT_USER} входит в привилегированную группу"
printf 'PASS: %s без sudo; .env и БД имеют права 600.\n' "$BOT_USER"
