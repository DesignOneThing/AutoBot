# Avto.net Telegram Bot

Telegram-бот мониторит сохраненные поисковые URL с `avto.net`, запоминает уже виденные объявления в SQLite и присылает только новые.

## Возможности

- несколько поисков на один чат;
- параметры поиска задаются ссылкой с avto.net после настройки фильтров на сайте;
- первичный скан при добавлении поиска не отправляет старые объявления;
- ручной `/scan`;
- опциональная отметка хорошей цены относительно похожих объявлений в текущей выдаче.

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
cp .env.example .env
```

Заполните `.env`:

```bash
TELEGRAM_BOT_TOKEN=...
ADMIN_CHAT_ID=
```

`ADMIN_CHAT_ID` можно оставить пустым, тогда бот будет работать в любом чате, куда его добавили.

## Запуск

```bash
avtonet-bot
```

Или:

```bash
python -m avtonet_bot
```

## Деплой на Render

В репозитории есть `render.yaml` для Render Blueprint. Бот разворачивается как Background Worker, потому что Telegram polling не принимает HTTP-трафик и не нуждается в web-порте.

1. Откройте Render Dashboard.
2. Создайте новый Blueprint и выберите этот GitHub-репозиторий.
3. При создании Render попросит значения для `sync: false` переменных:
   - `TELEGRAM_BOT_TOKEN` — токен от BotFather.
   - `ADMIN_CHAT_ID` — можно оставить пустым, если бот должен работать в любом чате.
4. Примените Blueprint.

Blueprint создает persistent disk и хранит SQLite в `/data/avtonet_bot.sqlite3`. Без диска Render сбрасывает локальные файлы после redeploy, и бот может повторно увидеть старые объявления как новые.

Важно: Background Workers на Render не доступны на free plan. В `render.yaml` указан `starter`.

## Команды

```text
/add_search <имя> <url> [минуты] [deal=on|off]
/list_searches
/remove_search <id>
/scan [id]
```

Пример:

```text
/add_search golf https://www.avto.net/Ads/results.asp?... 5 deal=on
```

## Как работает оценка цены

Для нового объявления бот смотрит другие объявления в той же выдаче, выбирает похожие по словам в названии, году и пробегу, затем сравнивает цену с медианой. По умолчанию объявление считается хорошей ценой, если оно дешевле медианы минимум на 12%.

Настройки:

```bash
GOOD_PRICE_ENABLED=true
GOOD_PRICE_RATIO=0.88
```

`GOOD_PRICE_RATIO=0.90` будет помечать больше объявлений, `0.80` — только заметно более дешевые.

## Важно

Сканер делает обычные HTTP-запросы к страницам результатов. Держите разумный интервал проверки и соблюдайте правила сайта avto.net.
