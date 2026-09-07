# Telegram Archive Bot

Минимальный приватный Telegram-бот. Сейчас он отвечает владельцу на команду
`/start`, распознаёт пересланные публикации Telegram-каналов и показывает
доступные метаданные исходного сообщения. Архивирование будет добавлено позже.

## Требования

- Python 3.12 или новее
- Telegram Bot Token

## Установка и запуск

Создайте и активируйте виртуальное окружение:

```bash
python -m venv .venv
source .venv/bin/activate
```

Установите зависимости:

```bash
pip install -r requirements.txt
```

Создайте файл с настройками:

```bash
cp .env.example .env
```

Получите токен у [@BotFather](https://t.me/BotFather) и укажите его в
`TELEGRAM_BOT_TOKEN`. Узнать свой Telegram user ID можно у информационного
бота, например [@userinfobot](https://t.me/userinfobot); запишите ID в
`OWNER_TELEGRAM_USER_ID`.

Запустите бота:

```bash
python -m app.main
```
