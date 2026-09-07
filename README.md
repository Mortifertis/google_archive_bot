# Telegram Archive Bot

Минимальный приватный Telegram-бот. Текущая версия:

- принимает пересланные публикации Telegram-каналов;
- объединяет Telegram albums/media groups;
- сохраняет text-only posts в Google Drive;
- импортирует DOCX как native Google Docs;
- возвращает владельцу ссылку на созданный документ.

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

## Google Drive setup

Перед архивированием необходимо один раз отдельно авторизовать Google Drive.
Отсутствие авторизации не мешает запуску бота, но текстовый пост нельзя будет
сохранить до выполнения `python -m app.google_auth`.

1. Создайте или выберите проект в Google Cloud Console.
2. Включите **Google Drive API**.
3. Настройте Google Auth Platform (OAuth consent). Для личного приложения с
   обычным Google-аккаунтом выберите аудиторию **External**.
4. Если приложение имеет статус Testing и консоль запрашивает тестовых
   пользователей, добавьте собственный Google-аккаунт в **Test users**.
5. Создайте OAuth Client с типом приложения **Desktop app**.
6. Скачайте JSON и сохраните его в корне проекта под именем
   `google_credentials.json`.
7. Запустите авторизацию:

   ```bash
   python -m app.google_auth
   ```

8. Завершите авторизацию в открывшемся браузере. После успеха приложение
   сохранит `google_token.json`, найдёт или создаст папку `Telegram Archive` и
   выведет её ID и URL. Копировать ID папки в настройки вручную не нужно.

Повторный запуск использует сохранённый token и обновляет истёкший access
token через refresh token. Папка определяется по закрытым `appProperties`, а
не только по имени, поэтому повторный запуск не создаёт её заново.

Не коммитьте OAuth client credentials. Файл token содержит refresh token и
также не должен попадать в Git. Стандартные имена обоих файлов и варианты
`*.credentials.json` / `*.token.json` добавлены в `.gitignore`. При утечке
credentials или token отзовите доступ в Google Account / Google Cloud Console
и перевыпустите соответствующие данные.

Пути и имя папки можно переопределить в `.env`:

```dotenv
GOOGLE_CREDENTIALS_PATH=google_credentials.json
GOOGLE_TOKEN_PATH=google_token.json
GOOGLE_ARCHIVE_FOLDER_NAME=Telegram Archive
```

Используется минимальный OAuth scope `drive.file`: приложение получает доступ
только к файлам и папкам, созданным им или явно открытым через приложение.


## Известные ограничения

Posts containing images are recognized but not archived yet. Бот не создаёт
для них неполный документ. Видео, аудио и документы пока также не архивируются.
