#!/usr/bin/env python3
"""
Simple CLI for Remnawave built on top of rw-sdk.

Install:
    pip install rw-sdk --break-system-packages   # or into a venv

Config (.env in the current directory, or -e path/-u URL/-t TOKEN):
    PANEL_URL="https://rw.example.com"
    API_TOKEN="eyJ...."

Commands:
    rwcli squads                                # list squads
    rwcli user ls [-q TEXT] [-s SQUAD] [-f F]   # list users (filter by username/squad)
    rwcli user show <username>                  # show one user
    rwcli user create <username> [options]      # create a user
    rwcli user update <username> [options]      # change a user (only the given fields)
    rwcli user delete <username> [-y]           # delete a user
    rwcli servers <user> [--raw]                # subscription servers (user: username/URL/short_uuid)
"""

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from rw_sdk import Remnawave, errors


# ---------- config ----------

def load_env(path: Path) -> dict:
    """Minimal KEY="value" parser for .env, no external dependencies."""
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
            f"PANEL_URL / API_TOKEN not found. Check {args.env_file}, "
            "environment variables or --panel-url/--token flags."
        )
    if panel_url.startswith("[") or "](" in panel_url:
        sys.exit(f"PANEL_URL looks broken (like a markdown link): {panel_url!r}")

    return Remnawave(panel_url, token=token)


# ---------- output helpers ----------

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
    """Traffic limit: 0 means unlimited in Remnawave."""
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
            sys.exit(f"Not found: {e.error_code} {e.error}")
        except errors.ValidationError as e:
            msgs = "; ".join(
                f"{'.'.join(str(p) for p in i.get('path', []))}: {i.get('message')}" for i in e.errors
            )
            sys.exit(f"Validation error: {msgs}")
        except errors.PermissionDeniedError:
            sys.exit("Permission denied: the token has no rights for this action.")
        except errors.APIConnectionError as e:
            sys.exit(f"Cannot connect to the panel: {e}")
        except errors.RemnawaveError as e:
            sys.exit(f"API error: {e}")
    return wrapper


# ---------- commands ----------

@die_on_api_error
def cmd_squads(rw: Remnawave, args):
    resp = rw.internal_squads.get_internal_squads()
    if not resp.internal_squads:
        print("No squads.")
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
def cmd_user_ls(rw: Remnawave, args):
    filters = None
    if args.query:
        from rw_sdk.models import TanstackQueryFilter
        filters = [TanstackQueryFilter(id="username", value=args.query)]

    fields = None
    if args.fields:
        fields = [f.strip() for f in args.fields.split(",") if f.strip()]
        unknown = [f for f in fields if f not in FIELDS]
        if unknown:
            sys.exit(f"Unknown fields: {', '.join(unknown)}. Available: {', '.join(FIELDS)}")

    squad_uuids = set(resolve_squads(rw, args.squad)) if args.squad else None

    found = False
    for u in rw.users.iter_users(filters=filters):
        user_squads = u.active_internal_squads or []
        if squad_uuids is not None and not squad_uuids & {s.uuid for s in user_squads}:
            continue
        found = True
        if fields:
            print("\t".join(FIELDS[f](u) for f in fields))
        else:
            squads = ", ".join(s.name for s in user_squads) or "-"
            print(f"{u.id:<6} {u.username:<20} {u.status:<10} "
                  f"traffic={fmt_bytes(u.user_traffic.used_traffic_bytes)}/"
                  f"{fmt_limit(u.traffic_limit_bytes)}  "
                  f"expire={fmt_dt(u.expire_at)}  squads=[{squads}]")
    if not found:
        print("No users found.", file=sys.stderr)


@die_on_api_error
def cmd_user_show(rw: Remnawave, args):
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
    """Takes a list of squad uuids and/or names, returns a list of uuids."""
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
        sys.exit(f"Squad(s) not found: {', '.join(unknown)}. Available: {available}")

    return result


@die_on_api_error
def cmd_user_create(rw: Remnawave, args):
    squad_uuids = resolve_squads(rw, args.squad or [])
    if not squad_uuids and not args.no_squad_prompt:
        # no squads given: show the list and hint how to assign one
        resp = rw.internal_squads.get_internal_squads()
        if resp.internal_squads:
            print("No squads given (--squad). Available squads:")
            for s in resp.internal_squads:
                print(f"  {s.uuid}  {s.name}")
            print("The user will be created without access to any inbound.")
            print("Pass --squad <uuid|name> (repeatable) to assign a squad.\n")

    expire_at = (
        datetime.now(timezone.utc) + timedelta(days=args.days)
        if args.days
        else datetime(2099, 1, 1, tzinfo=timezone.utc)
    )

    # optional fields are omitted entirely: rw-sdk sends None as an explicit null,
    # which the panel rejects
    kwargs = {}
    if squad_uuids:
        kwargs["active_internal_squads"] = squad_uuids
    if args.description:
        kwargs["description"] = args.description
    if args.telegram_id:
        kwargs["telegram_id"] = args.telegram_id

    user = rw.users.create_user(
        username=args.username,
        expire_at=expire_at,
        traffic_limit_bytes=args.traffic_gb * 1024 ** 3 if args.traffic_gb else 0,
        **kwargs,
    )
    print(f"Created user #{user.id} ({user.username})")
    print(f"  expire_at:    {fmt_dt(user.expire_at)}")
    print(f"  subscription: {user.subscription_url}")


@die_on_api_error
def cmd_user_update(rw: Remnawave, args):
    # only the given flags are sent; everything else stays as it is on the panel
    kwargs = {}
    if args.squad is not None:
        kwargs["active_internal_squads"] = resolve_squads(rw, args.squad)
    if args.days is not None:
        kwargs["expire_at"] = datetime.now(timezone.utc) + timedelta(days=args.days)
    if args.traffic_gb is not None:
        kwargs["traffic_limit_bytes"] = int(args.traffic_gb * 1024 ** 3)
    if args.description is not None:
        kwargs["description"] = args.description
    if args.telegram_id is not None:
        kwargs["telegram_id"] = args.telegram_id
    if not kwargs:
        sys.exit("Nothing to update: pass at least one of -s/-d/-g/-D/-T")

    u = rw.users.update_user(username=args.username, **kwargs)
    squads = ", ".join(s.name for s in (u.active_internal_squads or [])) or "-"
    print(f"Updated user '{u.username}': "
          f"traffic={fmt_bytes(u.user_traffic.used_traffic_bytes)}/{fmt_limit(u.traffic_limit_bytes)}  "
          f"expire={fmt_dt(u.expire_at)}  squads=[{squads}]")


@die_on_api_error
def cmd_user_delete(rw: Remnawave, args):
    user = rw.users.get_user_by_username(args.username)
    if not args.yes:
        confirm = input(f"Delete user '{user.username}' (id={user.id})? [y/N] ")
        if confirm.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return
    rw.users.delete_user(user.id)
    print(f"User '{user.username}' deleted.")


def resolve_short_uuid(rw: Remnawave, value: str) -> str:
    """Takes a username, subscription URL or short_uuid, returns short_uuid."""
    if "/" in value:
        from urllib.parse import urlparse
        return urlparse(value).path.rstrip("/").rsplit("/", 1)[-1]
    try:
        return rw.users.get_user_by_username(value).short_uuid
    except errors.NotFoundError:
        return value


@die_on_api_error
def cmd_servers(rw: Remnawave, args):
    short_uuid = resolve_short_uuid(rw, args.user)
    if args.raw:
        for link in rw.subscriptions.get_subscription_by_short_uuid_protected(short_uuid).links:
            print(link)
        return

    configs = rw.subscriptions.get_raw_subscription_by_short_uuid(short_uuid).resolved_proxy_configs
    if not configs:
        print("No servers.", file=sys.stderr)
        return
    for item in configs:
        c = item.root
        protocol = getattr(c, "protocol", "-")
        protocol = getattr(protocol, "value", protocol)
        print(f"{c.final_remark:<20} {protocol:<8} {c.address}:{c.port}")


# ---------- argument parser ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CLI for Remnawave (built on rw-sdk)")
    p.add_argument("-e", "--env-file", default=".env", help="file with PANEL_URL/API_TOKEN (default: .env)")
    p.add_argument("-u", "--panel-url", help="override PANEL_URL")
    p.add_argument("-t", "--token", help="override API_TOKEN")

    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("squads", help="list squads").set_defaults(func=cmd_squads)

    p_user = sub.add_parser("user", help="manage users (ls, show, create, update, delete)")
    user_sub = p_user.add_subparsers(dest="action", required=True)

    p_ls = user_sub.add_parser("ls", help="list users")
    p_ls.set_defaults(func=cmd_user_ls)
    p_ls.add_argument("-q", "--query", help="filter by username (contains)")
    p_ls.add_argument("-s", "--squad", action="append", help="only users in this squad, uuid or name (repeatable: -s X -s Y)")
    p_ls.add_argument(
        "-f", "--fields",
        help="comma-separated fields for machine-readable output (TSV, no header). "
             "Available fields: " + ", ".join(FIELDS),
    )

    p_show = user_sub.add_parser("show", help="show one user")
    p_show.set_defaults(func=cmd_user_show)
    p_show.add_argument("username")

    p_create = user_sub.add_parser("create", help="create a user")
    p_create.set_defaults(func=cmd_user_create)
    p_create.add_argument("username")
    p_create.add_argument("-s", "--squad", action="append", help="squad uuid or name (repeatable: -s X -s Y)")
    p_create.add_argument("-d", "--days", type=int, default=30, help="expires in N days from now (default: 30)")
    p_create.add_argument("-g", "--traffic-gb", type=float, default=0, help="traffic limit in GB, 0 = unlimited (default)")
    p_create.add_argument("-D", "--description", help="description")
    p_create.add_argument("-T", "--telegram-id", type=int, help="telegram id")
    p_create.add_argument("-n", "--no-squad-prompt", action="store_true", help="don't list squads when --squad is not given")

    p_update = user_sub.add_parser("update", help="change a user (only the given fields)")
    p_update.set_defaults(func=cmd_user_update)
    p_update.add_argument("username")
    p_update.add_argument("-s", "--squad", action="append",
                          help="squad uuid or name (repeatable); REPLACES the user's squad list")
    p_update.add_argument("-d", "--days", type=int, help="expires in N days from now")
    p_update.add_argument("-g", "--traffic-gb", type=float, help="traffic limit in GB, 0 = unlimited")
    p_update.add_argument("-D", "--description", help="description")
    p_update.add_argument("-T", "--telegram-id", type=int, help="telegram id")

    p_delete = user_sub.add_parser("delete", help="delete a user")
    p_delete.set_defaults(func=cmd_user_delete)
    p_delete.add_argument("username")
    p_delete.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")

    p_servers = sub.add_parser("servers", help="subscription servers of a user")
    p_servers.set_defaults(func=cmd_servers)
    p_servers.add_argument("user", help="username, subscription URL or short_uuid")
    p_servers.add_argument("-r", "--raw", action="store_true", help="print connection links (vless://...)")

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    rw = get_client(args)
    args.func(rw, args)


if __name__ == "__main__":
    main()
