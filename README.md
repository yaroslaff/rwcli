# rw-cli

Простой CLI для [Remnawave](https://github.com/remnawave/backend) поверх
[`rw-sdk`](https://pypi.org/project/rw-sdk/): список сквадов, список пользователей
(с фильтром и выбором полей), инфо по одному пользователю, создание и удаление.

## Быстрая установка из репозитория

```bash
pipx install git+https://github.com/yaroslaff/rwcli.git
```

Команда `rw-cli` сразу появится в `PATH`. Обновить: `pipx upgrade rw-cli`.

## Установка

Вариант 1 — без установки пакета, просто скрипт + зависимость:

```bash
pip install rw-sdk --break-system-packages
```

и запускать `python3 rwcli.py ...`.

Вариант 2 — установить как команду `rw-cli` в систему/venv:

```bash
pip install .          # из этой директории, где лежат pyproject.toml и rwcli.py
# или через pipx, если хотите изолированное окружение:
pipx install .
```

После этого доступна команда `rw-cli` вместо `python3 rwcli.py`.

## Настройка

Скрипт ищет `PANEL_URL` и `API_TOKEN` в таком порядке:

1. флаги `-u/--panel-url` и `-t/--token`;
2. переменные окружения `PANEL_URL` / `API_TOKEN`;
3. файл `.env` в текущей директории (или указанный через `-e/--env-file`).

Формат `.env`:

```env
PANEL_URL="https://rw.example.com"
API_TOKEN="eyJ...."
```

`API_TOKEN` — токен, созданный на странице *API Tokens* в панели.

## Команды

### `squads` — список сквадов

```bash
rw-cli squads
```

Выводит uuid, имя, число участников и теги инбаундов каждого сквада.

### `users` — список пользователей

```bash
rw-cli users
rw-cli users -q alice                       # фильтр по username (contains)
rw-cli users -f username,expire_at,status   # машиночитаемый вывод (TSV)
```

Без `-f` — человекочитаемая таблица. С `-f поле1,поле2,...` — построчный
TSV без заголовка (табуляция между полями), удобно для `awk`/`cut`/`while read`:

```bash
rw-cli users -f username,squad_uuids | awk -F'\t' '{print $1}'
```

Доступные поля:

`id, username, short_uuid, status, expire_at, traffic_limit_bytes,
traffic_used_bytes, traffic_limit_strategy, telegram_id, email, description,
tag, hwid_device_limit, squads, squad_uuids, subscription_url, vless_uuid,
trojan_password, ss_password, created_at`

`expire_at` / `created_at` в режиме `-f` отдаются в ISO 8601 UTC (не в
человеческом формате), чтобы с ними можно было сортировать/парсить без боли.

### `user <username>` — инфо по одному пользователю

```bash
rw-cli user john_doe
```

Полная карточка: id, статус, лимиты/расход трафика, сквады, ключи подключения
(VLESS uuid, Trojan/SS пароли), ссылка на подписку.

### `create <username>` — создать пользователя

```bash
rw-cli create john_doe -s Default-Squad -d 90 -g 100
```

| Флаг | Значение | По умолчанию |
|---|---|---|
| `-s, --squad` | uuid **или имя** сквада (можно указать несколько раз) | без сквада |
| `-d, --days` | срок действия в днях от текущего момента | `30` |
| `-g, --traffic-gb` | лимит трафика в GB, `0` = безлимит | `0` |
| `-D, --description` | описание | — |
| `-T, --telegram-id` | telegram id | — |
| `-n, --no-squad-prompt` | не выводить список сквадов, если `-s` не задан | выкл. |

Имя сквада резолвится в uuid автоматически (регистронезависимо). Если сквад
с таким именем не найден — скрипт покажет список доступных и остановится,
не создавая пользователя без доступа по ошибке.

### `delete <username>` — удалить пользователя

```bash
rw-cli delete john_doe          # спросит подтверждение
rw-cli delete john_doe -y       # без подтверждения
```

## Общие флаги

| Флаг | Значение |
|---|---|
| `-e, --env-file` | путь к файлу конфига (по умолчанию `.env`) |
| `-u, --panel-url` | переопределить `PANEL_URL` |
| `-t, --token` | переопределить `API_TOKEN` |

## Требования

- Python ≥ 3.10
- [`rw-sdk`](https://pypi.org/project/rw-sdk/) ≥ 3.3.2 (устанавливается автоматически как зависимость)

## Лицензия

MIT.
