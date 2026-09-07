# Telegram Archive Bot

Минимальный приватный Telegram-бот. Сейчас он отвечает владельцу на команду
`/start`, распознаёт пересланные публикации Telegram-каналов, определяет их
источник и показывает доступные метаданные. Telegram albums/media groups бот
объединяет в один логический материал. Архивирование будет добавлено позже.

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

Необязательная настройка `MEDIA_GROUP_DEBOUNCE_SECONDS` задаёт паузу для
сборки альбома и по умолчанию равна `1.5` секунды.

Запустите бота:

```bash
python -m app.main
```
