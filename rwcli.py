#!/usr/bin/env python3
"""
Простой CLI для Remnawave поверх rw-sdk.

Установка:
    pip install rw-sdk --break-system-packages   # или в venv

Настройка (.env в текущем каталоге, или -e path/-u URL/-t TOKEN):
    PANEL_URL="https://rw.example.com"
    API_TOKEN="eyJ...."

Команды:
    rwcli squads                    # список сквадов
    rwcli users [-q TEXT] [-f F,..] # список юзеров (фильтр по username)
    rwcli user <username>           # инфо по одному юзеру
    rwcli create <username> [опции] # создать юзера
    rwcli delete <username> [-y]    # удалить юзера
"""

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from rw_sdk import Remnawave, errors


# ---------- конфиг ----------

def load_env(path: Path) -> dict:
    """Простой парсер KEY="value" из .env, без внешних зависимостей."""
    data = {}
    if not path.exists():
        return data
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def get_client(args) -> Remnawave:
    env = load_env(Path(args.env_file))
    panel_url = args.panel_url or os.getenv("PANEL_URL") or env.get("PANEL_URL")
    token = args.token or os.getenv("API_TOKEN") or env.get("API_TOKEN")

    if not panel_url or not token:
        sys.exit(
            f"Не найден PANEL_URL / API_TOKEN. Проверьте {args.env_file}, "
            "переменные окружения или флаги --panel-url/--token."
        )
    if panel_url.startswith("[") or "](" in panel_url:
        sys.exit(f"PANEL_URL выглядит битым (похоже на markdown-ссылку): {panel_url!r}")

    return Remnawave(panel_url, token=token)


# ---------- утилиты вывода ----------

def fmt_bytes(n) -> str:
    if n is None:
        return "-"
    if n == 0:
        return "0 B"
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < step:
            return f"{n:.1f} {unit}"
        n /= step
    return f"{n:.1f} PB"


def fmt_limit(n) -> str:
    """Лимит трафика: 0 в Remnawave означает безлимит."""
    return "∞" if n == 0 else fmt_bytes(n)


def fmt_dt(dt) -> str:
    if dt is None:
        return "-"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def die_on_api_error(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except errors.NotFoundError as e:
            sys.exit(f"Не найдено: {e.error_code} {e.error}")
        except errors.ValidationError as e:
            msgs = "; ".join(f"{i['path']}: {i['message']}" for i in e.errors)
            sys.exit(f"Ошибка валидации: {msgs}")
        except errors.PermissionDeniedError:
            sys.exit("Доступ запрещён: у токена нет прав на это действие.")
        except errors.APIConnectionError as e:
            sys.exit(f"Не удалось подключиться к панели: {e}")
        except errors.RemnawaveError as e:
            sys.exit(f"Ошибка API: {e}")
    return wrapper


# ---------- команды ----------

@die_on_api_error
def cmd_squads(rw: Remnawave, args):
    resp = rw.internal_squads.get_internal_squads()
    if not resp.internal_squads:
        print("Сквадов нет.")
        return
    for s in resp.internal_squads:
        inbound_tags = ", ".join(ib.tag for ib in s.inbounds) or "-"
        print(f"{s.uuid}  {s.name:<20} members={s.info.members_count:<4} "
              f"inbounds=[{inbound_tags}]")


FIELDS = {
    "id": lambda u: str(u.id),
    "username": lambda u: u.username,
    "short_uuid": lambda u: u.short_uuid,
    "status": lambda u: u.status,
    "expire_at": lambda u: u.expire_at.astimezone(timezone.utc).isoformat() if u.expire_at else "",
    "traffic_limit_bytes": lambda u: str(u.traffic_limit_bytes),
    "traffic_used_bytes": lambda u: str(u.user_traffic.used_traffic_bytes),
    "traffic_limit_strategy": lambda u: u.traffic_limit_strategy,
    "telegram_id": lambda u: str(u.telegram_id) if u.telegram_id else "",
    "email": lambda u: u.email or "",
    "description": lambda u: u.description or "",
    "tag": lambda u: u.tag or "",
    "hwid_device_limit": lambda u: str(u.hwid_device_limit) if u.hwid_device_limit is not None else "",
    "squads": lambda u: ",".join(s.name for s in (u.active_internal_squads or [])),
    "squad_uuids": lambda u: ",".join(s.uuid for s in (u.active_internal_squads or [])),
    "subscription_url": lambda u: u.subscription_url or "",
    "vless_uuid": lambda u: u.vless_uuid or "",
    "trojan_password": lambda u: u.trojan_password or "",
    "ss_password": lambda u: u.ss_password or "",
    "created_at": lambda u: u.created_at.astimezone(timezone.utc).isoformat() if u.created_at else "",
}


@die_on_api_error
def cmd_users(rw: Remnawave, args):
    filters = None
    if args.query:
        from rw_sdk.models import TanstackQueryFilter
        filters = [TanstackQueryFilter(id="username", value=args.query)]

    fields = None
    if args.fields:
        fields = [f.strip() for f in args.fields.split(",") if f.strip()]
        unknown = [f for f in fields if f not in FIELDS]
        if unknown:
            sys.exit(f"Неизвестные поля: {', '.join(unknown)}. Доступные: {', '.join(FIELDS)}")

    found = False
    for u in rw.users.iter_users(filters=filters):
        found = True
        if fields:
            print("\t".join(FIELDS[f](u) for f in fields))
        else:
            squads = ", ".join(s.name for s in (u.active_internal_squads or [])) or "-"
            print(f"{u.id:<6} {u.username:<20} {u.status:<10} "
                  f"traffic={fmt_bytes(u.user_traffic.used_traffic_bytes)}/"
                  f"{fmt_limit(u.traffic_limit_bytes)}  "
                  f"expire={fmt_dt(u.expire_at)}  squads=[{squads}]")
    if not found:
        print("Юзеры не найдены.", file=sys.stderr)


@die_on_api_error
def cmd_user(rw: Remnawave, args):
    u = rw.users.get_user_by_username(args.username)
    squads = ", ".join(f"{s.name} ({s.uuid})" for s in (u.active_internal_squads or [])) or "-"
    print(f"id:              {u.id}")
    print(f"username:        {u.username}")
    print(f"short_uuid:      {u.short_uuid}")
    print(f"status:          {u.status}")
    print(f"expire_at:       {fmt_dt(u.expire_at)}")
    print(f"traffic:         {fmt_bytes(u.user_traffic.used_traffic_bytes)} / {fmt_limit(u.traffic_limit_bytes)} ({u.traffic_limit_strategy})")
    print(f"telegram_id:     {u.telegram_id or '-'}")
    print(f"email:           {u.email or '-'}")
    print(f"description:     {u.description or '-'}")
    print(f"hwid_limit:      {u.hwid_device_limit if u.hwid_device_limit is not None else '-'}")
    print(f"squads:          {squads}")
    print(f"vless_uuid:      {u.vless_uuid}")
    print(f"trojan_password: {u.trojan_password}")
    print(f"ss_password:     {u.ss_password}")
    print(f"subscription:    {u.subscription_url}")


def is_uuid(s: str) -> bool:
    import re
    return bool(re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", s
    ))


def resolve_squads(rw: Remnawave, values: list) -> list:
    """Принимает список uuid и/или имён сквадов, возвращает список uuid."""
    if not values:
        return []
    if all(is_uuid(v) for v in values):
        return values

    squads = rw.internal_squads.get_internal_squads().internal_squads
    by_name = {s.name: s.uuid for s in squads}
    by_name_ci = {s.name.lower(): s.uuid for s in squads}

    result = []
    unknown = []
    for v in values:
        if is_uuid(v):
            result.append(v)
        elif v in by_name:
            result.append(by_name[v])
        elif v.lower() in by_name_ci:
            result.append(by_name_ci[v.lower()])
        else:
            unknown.append(v)

    if unknown:
        available = ", ".join(s.name for s in squads) or "-"
        sys.exit(f"Сквад(ы) не найдены: {', '.join(unknown)}. Доступные: {available}")

    return result


@die_on_api_error
def cmd_create(rw: Remnawave, args):
    squad_uuids = resolve_squads(rw, args.squad or [])
    if not squad_uuids and not args.no_squad_prompt:
        # если сквады не переданы, покажем список и попросим выбрать
        resp = rw.internal_squads.get_internal_squads()
        if resp.internal_squads:
            print("Сквады не указаны (--squad). Доступные сквады:")
            for s in resp.internal_squads:
                print(f"  {s.uuid}  {s.name}")
            print("Пользователь будет создан без доступа ни к одному инбаунду.")
            print("Передайте --squad <uuid> (можно несколько раз), чтобы назначить сквад.\n")

    expire_at = (
        datetime.now(timezone.utc) + timedelta(days=args.days)
        if args.days
        else datetime(2099, 1, 1, tzinfo=timezone.utc)
    )

    user = rw.users.create_user(
        username=args.username,
        expire_at=expire_at,
        traffic_limit_bytes=args.traffic_gb * 1024 ** 3 if args.traffic_gb else 0,
        active_internal_squads=squad_uuids or None,
        description=args.description or None,
        telegram_id=args.telegram_id or None,
    )
    print(f"Создан пользователь #{user.id} ({user.username})")
    print(f"  expire_at:    {fmt_dt(user.expire_at)}")
    print(f"  subscription: {user.subscription_url}")


@die_on_api_error
def cmd_delete(rw: Remnawave, args):
    user = rw.users.get_user_by_username(args.username)
    if not args.yes:
        confirm = input(f"Удалить пользователя '{user.username}' (id={user.id})? [y/N] ")
        if confirm.strip().lower() not in ("y", "yes", "д", "да"):
            print("Отменено.")
            return
    rw.users.delete_user(user.id)
    print(f"Пользователь '{user.username}' удалён.")


# ---------- парсер аргументов ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CLI для Remnawave (на базе rw-sdk)")
    p.add_argument("-e", "--env-file", default=".env", help="путь к файлу с PANEL_URL/API_TOKEN (по умолчанию: .env)")
    p.add_argument("-u", "--panel-url", help="переопределить PANEL_URL")
    p.add_argument("-t", "--token", help="переопределить API_TOKEN")

    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("squads", help="список сквадов")

    p_users = sub.add_parser("users", help="список пользователей")
    p_users.add_argument("-q", "--query", help="фильтр по username (contains)")
    p_users.add_argument(
        "-f", "--fields",
        help="список полей через запятую для машиночитаемого вывода (TSV, без заголовка). "
             "Доступные поля: " + ", ".join(FIELDS),
    )

    p_user = sub.add_parser("user", help="инфо по одному пользователю")
    p_user.add_argument("username")

    p_create = sub.add_parser("create", help="создать пользователя")
    p_create.add_argument("username")
    p_create.add_argument("-s", "--squad", action="append", help="uuid или имя сквада (можно несколько раз: -s X -s Y)")
    p_create.add_argument("-d", "--days", type=int, default=30, help="срок действия в днях от текущего момента (по умолчанию 30)")
    p_create.add_argument("-g", "--traffic-gb", type=float, default=0, help="лимит трафика в GB, 0 = безлимит (по умолчанию)")
    p_create.add_argument("-D", "--description", help="описание")
    p_create.add_argument("-T", "--telegram-id", type=int, help="telegram id")
    p_create.add_argument("-n", "--no-squad-prompt", action="store_true", help="не выводить список сквадов, если --squad не задан")

    p_delete = sub.add_parser("delete", help="удалить пользователя")
    p_delete.add_argument("username")
    p_delete.add_argument("-y", "--yes", action="store_true", help="не спрашивать подтверждение")

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    rw = get_client(args)

    commands = {
        "squads": cmd_squads,
        "users": cmd_users,
        "user": cmd_user,
        "create": cmd_create,
        "delete": cmd_delete,
    }
    commands[args.command](rw, args)


if __name__ == "__main__":
    main()
