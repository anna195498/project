# Харденинг Geo Messenger на Ubuntu

Скрипты предназначены для ручного запуска администратором VPS от `root`.
Заранее убедитесь, что у вас есть доступ к консоли провайдера и рабочий вход
по SSH-ключу. Не запускайте настройку файервола или SSH в единственной
непроверенной SSH-сессии.

## Подготовка

Разместите код проекта в `/opt/geo-messenger`, создайте там `.env` на основе
`.env.example` и укажите секретный `BOT_TOKEN`. Не публикуйте `.env`.
`DATABASE_PATH` должен быть абсолютным путём внутри `/var/lib/geo-messenger`,
например `/var/lib/geo-messenger/geo_messenger.db`.
Для `USE_WEBHOOK=true` дополнительно положите TLS-сертификат и приватный ключ
внутрь `/var/lib/geo-messenger` и укажите их абсолютные пути в `.env`;
создайте `WEBHOOK_SECRET` и задайте публичный `WEBHOOK_URL`.

## Порядок применения

### 1. Пользователь и права

```bash
sudo bash /opt/geo-messenger/security/create_bot_user.sh
sudo -u geobot python3.11 -m venv /var/lib/geo-messenger/venv
sudo -u geobot /var/lib/geo-messenger/venv/bin/pip install \
  -r /opt/geo-messenger/requirements.txt
```

Скрипт создаёт системного пользователя `geobot` без shell, удаляет его из
привилегированных групп `sudo`/`wheel`, оставляет код доступным только для
чтения и устанавливает права `600` на `.env` и SQLite-файл.

### 2. Харденинг SSH

Узнайте свой внешний IP у администратора сети или провайдера. Проверьте вход
по ключу в отдельной SSH-сессии. Затем:

```bash
sudo bash /opt/geo-messenger/security/harden_ssh.sh
```

Скрипт сохраняет копию конфигурации, применяет drop-in, проверяет её командой
`sshd -t` и ждёт явного подтверждения reload. Не подтверждайте reload, пока
не проверили новый вход по ключу в отдельной сессии.

### 3. Fail2ban

```bash
sudo bash /opt/geo-messenger/security/setup_fail2ban.sh
```

Создаётся jail `sshd` с `maxretry=5` и `bantime=1h`.

### 4. Файервол

В `security/setup_firewall.sh` замените `SSH_ALLOWED_IP` на ваш внешний IP
(или CIDR вашей административной сети). Не используйте адрес из примера
буквально. При запуске скрипт предупредит о риске потерять SSH и запросит
подтверждение.

По умолчанию используется long polling: открывается SSH только для указанного
IP, входящая политика — deny, исходящая — allow. Для ограниченного исходящего
трафика запустите с `STRICT_OUTBOUND=true`; будут разрешены только DNS, HTTP(S)
и NTP, перечисленные в скрипте.

`USE_WEBHOOK` читается из `.env`. Если он равен `true`, перед запуском замените
плейсхолдер массива `TELEGRAM_WEBHOOK_CIDRS` в начале скрипта фактическими
диапазонами из официальной документации Telegram и проверьте их актуальность.
Скрипт не содержит готовых IP-диапазонов. Не включайте webhook-правило без
подтверждённых диапазонов и реально настроенного webhook endpoint. Процесс
слушает HTTPS-порт 443 от пользователя `geobot`; systemd выдаёт только
ограниченную capability для bind на привилегированный порт.

```bash
sudo bash /opt/geo-messenger/security/setup_firewall.sh
```

Скрипт не сбрасывает существующие правила UFW. До применения проверьте
`sudo ufw status numbered` и вручную уберите ненужные разрешающие правила,
иначе старые правила могут оставить дополнительные порты открытыми.

### 5. systemd

Создайте окружение и установите зависимости как `geobot` (если это не сделано
на шаге 1), затем установите unit:

```bash
sudo install -o root -g root -m 644 \
  /opt/geo-messenger/security/geo-messenger.service \
  /etc/systemd/system/geo-messenger.service
sudo systemctl daemon-reload
sudo systemctl enable --now geo-messenger.service
```

Unit запускает бота от `geobot`, ограничивает запись каталогом данных и
перезапускает процесс при ошибке.

### 6. Проверка

```bash
sudo bash /opt/geo-messenger/security/verify_security.sh
sudo systemctl status geo-messenger.service --no-pager
sudo ufw status verbose
```

Все проверки должны завершиться `PASS`. С внешнего хоста проверьте доступность
через `nmap`: должны быть открыты максимум SSH/22 и, только при webhook,
HTTPS/443. Проверяйте с хоста, чей IP разрешён для SSH; webhook-порт должен
быть доступен только из актуальных диапазонов Telegram.

## Замена плейсхолдеров

- `SSH_ALLOWED_IP`: ваш реальный внешний IPv4/IPv6 или CIDR административной
  сети; получить его можно у провайдера, сетевого администратора или через
  корпоративный VPN. Скрипт откажется работать с плейсхолдером.
- `TELEGRAM_WEBHOOK_CIDRS`: актуальные диапазоны сверяйте только с официальной
  документацией Telegram непосредственно перед применением.
- `WEBHOOK_SECRET`: создайте случайное значение из букв, цифр, `_` и `-`
  длиной от 1 до 256 символов. TLS-ключ должен быть доступен только `geobot`.
- Пути `/opt/geo-messenger` и `/var/lib/geo-messenger` должны соответствовать
  размещению кода и данным. Если меняете их, синхронно измените пути в скрипте
  создания пользователя, systemd-unit и скрипте проверки.

## Откат

Перед откатом убедитесь в наличии доступа к консоли VPS.

- **Пользователь/права:** остановите сервис, выполните
  `sudo systemctl stop geo-messenger.service`, затем
  `sudo userdel geobot` (не добавляйте `-r`, если нужно сохранить БД).
  Каталоги приложения и данных удаляйте или меняйте владельца вручную только
  после резервного копирования.
- **SSH:** в `/var/backups/geo-messenger-ssh` выберите сохранённые копии.
  Восстановите `sshd_config.before-geo-messenger` и прежний drop-in
  `00-hardening.before-geo-messenger.conf` (если он существовал до настройки),
  либо удалите `00-geo-messenger-hardening.conf`, если drop-in изначально не
  существовал, затем выполните
  `sudo sshd -t && sudo systemctl reload ssh` (либо `sshd` на системе с таким
  именем службы). Не закрывайте текущую сессию до проверки нового входа.
- **Fail2ban:** восстановите
  `/etc/fail2ban/jail.d/geo-messenger-sshd.local.before-geo-messenger`, если он
  существовал, иначе удалите
  `/etc/fail2ban/jail.d/geo-messenger-sshd.local`, и выполните
  `sudo systemctl restart fail2ban`. Пакет можно удалить отдельно командой
  `sudo apt remove fail2ban`, если другие jail не используются.
- **UFW:** восстановите сохранённые до настройки правила администратора.
  Если UFW до этого не использовался и SSH-доступ через консоль подтверждён,
  отключите его командой `sudo ufw disable`. Не выполняйте `ufw reset`
  удалённо без консольного доступа.
- **systemd:** выполните `sudo systemctl disable --now geo-messenger.service`,
  удалите `/etc/systemd/system/geo-messenger.service` и выполните
  `sudo systemctl daemon-reload`. Код и данные сохраняются.

## Итоговый чек-лист

- [ ] Вход по SSH-ключу проверен; парольный вход и root login отключены.
- [ ] UFW активен, входящая политика deny, разрешены только необходимые
      правила и адреса.
- [ ] Fail2ban активен, jail `sshd` включён.
- [ ] `.env` и файл БД принадлежат `geobot` и имеют права `600`.
- [ ] `geo-messenger.service` работает от `geobot`, не от root.
- [ ] Внешнее сканирование показывает максимум порт 22; порт 443 появляется
      только при настроенном webhook и разрешён только источникам Telegram.
