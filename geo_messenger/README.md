# Geo Messenger (MVP)

Асинхронный Telegram-бот на Python 3.11+, который отправляет выбранному
контакту сообщение от имени владельца при входе владельца в заданный радиус.

## Установка и запуск

1. Создайте бота у [@BotFather](https://t.me/BotFather) командой `/newbot`
   и скопируйте выданный токен.
2. В каталоге `geo_messenger` скопируйте `.env.example` в `.env` и укажите токен:

   ```env
   BOT_TOKEN=ваш_токен_от_BotFather
   DATABASE_PATH=geo_messenger.sqlite3
   ```

3. Установите Python 3.11 или новее и зависимости:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

4. Запустите бота из каталога `geo_messenger`:

   ```powershell
   python main.py
   ```

## Использование

- Откройте бота и отправьте `/start`.
- Чтобы добавить получателя, перешлите ему пригласительную ссылку из ответа
  бота. Контакт должен открыть ссылку и нажать **Start**.
- Отправьте `/rule` и пройдите шаги: точка на карте → радиус в метрах →
  контакт → текст сообщения → подтверждение.
- Для отслеживания поделитесь геопозицией с ботом. Для непрерывного контроля
  отправьте live location; обновления live location обрабатываются, пока бот
  работает и получает Telegram updates.

Telegram не позволяет боту первым писать пользователю: получатель должен хотя
бы один раз запустить бота. Позиции Telegram кэшируются в памяти процесса;
история местоположений не сохраняется.

По умолчанию используется long polling. Для webhook укажите `USE_WEBHOOK=true`,
HTTPS-адрес `WEBHOOK_URL`, случайный `WEBHOOK_SECRET`, абсолютные пути к
сертификату и приватному ключу в `WEBHOOK_CERT_FILE` и `WEBHOOK_KEY_FILE`.
Webhook server слушает `WEBHOOK_HOST`/`WEBHOOK_PORT` (по умолчанию `0.0.0.0:443`).
Приватный ключ должен быть доступен `geobot`; см. [инструкции по безопасности](security/README_SECURITY.md).

## Развёртывание на Vercel

Vercel обслуживает webhook как ASGI-приложение (`main:app`); long polling там
не используется. В Vercel задайте Root Directory проекта `geo_messenger` и
добавьте переменные окружения:

- `BOT_TOKEN` — токен из BotFather.
- `DATABASE_URL` — PostgreSQL connection string из Supabase. Для serverless
  используйте рекомендуемый Supabase pooler connection string с SSL.
- `USE_WEBHOOK=true`.
- `WEBHOOK_URL` — HTTPS origin опубликованного проекта, например
  `https://<ваш-домен-vercel>`.
- `WEBHOOK_PATH=/api/webhook`.
- `WEBHOOK_SECRET` — случайная строка из букв, цифр, `_` и `-`.

Vercel предоставляет TLS, поэтому `WEBHOOK_CERT_FILE` и `WEBHOOK_KEY_FILE` там
не нужны. Таблицы создаются при запуске автоматически; у пользователя БД должны
быть права на создание таблиц. Переход на Supabase не переносит существующие
записи из локального SQLite-файла автоматически. Укажите в настройках Vercel
`USE_WEBHOOK=true`; платформа сама задаёт `VERCEL`, и приложение использует
ASGI webhook-вход без локальных TLS-файлов.

Получите PostgreSQL connection string в настройках Supabase и сохраните его
только как переменную `DATABASE_URL` в Vercel. Не вставляйте его в исходники
или чат. Supabase PostgreSQL хранит правила, FSM-состояние и счётчики rate
limit между вызовами serverless-функций.
Останавливайте VPS polling-процесс перед переключением этого же токена на
Vercel. Для Preview-окружений используйте отдельного тестового бота, иначе
Preview deployment может заменить webhook URL production-бота.

Для VPS база по умолчанию остаётся SQLite и используется long polling. Не
добавляйте `.env` с секретами в систему контроля версий.
