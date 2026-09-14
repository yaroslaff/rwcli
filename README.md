# rwcli

Simple CLI for [Remnawave](https://github.com/remnawave/backend) built on
[`rw-sdk`](https://pypi.org/project/rw-sdk/): list squads, list users
(with filters and field selection), show a single user, create and delete users,
show subscription servers.

## Quick install from the repository

```bash
pipx install git+https://github.com/yaroslaff/rwcli.git
```

The `rwcli` command is available in `PATH` right away. Upgrade: `pipx upgrade rwcli`.

## Installation

Option 1 — no package install, just the script plus its dependency:

```bash
pip install rw-sdk --break-system-packages
```

then run `python3 rwcli.py ...`.

Option 2 — install as the `rwcli` command system-wide or into a venv:

```bash
pip install .          # from this directory (with pyproject.toml and rwcli.py)
# or with pipx for an isolated environment:
pipx install .
```

After that, use `rwcli` instead of `python3 rwcli.py`.

## Configuration

`PANEL_URL` and `API_TOKEN` are looked up in this order:

1. flags `-u/--panel-url` and `-t/--token`;
2. environment variables `PANEL_URL` / `API_TOKEN`;
3. the `.env` file in the current directory (or the one given with `-e/--env-file`).

`.env` format:

```env
PANEL_URL="https://rw.example.com"
API_TOKEN="eyJ...."
```

`API_TOKEN` is a token created on the *API Tokens* page of the panel.

## Commands

### `squads` — list squads

```bash
rwcli squads
```

Prints the uuid, name, member count and inbound tags of each squad.

### `users` — list users

```bash
rwcli users
rwcli users -q alice                       # filter by username (contains)
rwcli users -s TnnlsPromo                  # only users in a squad (uuid or name, repeatable: -s X -s Y)
rwcli users -f username,expire_at,status   # machine-readable output (TSV)
```

Without `-f` — a human-readable table. With `-f field1,field2,...` — one line
per user, TSV without a header (tab-separated), handy for `awk`/`cut`/`while read`:

```bash
rwcli users -f username,squad_uuids | awk -F'\t' '{print $1}'
```

Available fields:

`id, username, short_uuid, status, expire_at, traffic_limit_bytes,
traffic_used_bytes, traffic_limit_strategy, telegram_id, email, description,
tag, hwid_device_limit, squads, squad_uuids, subscription_url, vless_uuid,
trojan_password, ss_password, created_at`

In `-f` mode `expire_at` / `created_at` are printed as ISO 8601 UTC (not the
human-readable format), so they are easy to sort and parse.

### `user <username>` — show one user

```bash
rwcli user john_doe
```

Full card: id, status, traffic limit/usage, squads, connection credentials
(VLESS uuid, Trojan/SS passwords), subscription link.

### `create <username>` — create a user

```bash
rwcli create john_doe -s Default-Squad -d 90 -g 100
```

| Flag | Meaning | Default |
|---|---|---|
| `-s, --squad` | squad uuid **or name** (repeatable) | no squad |
| `-d, --days` | expires in N days from now | `30` |
| `-g, --traffic-gb` | traffic limit in GB, `0` = unlimited | `0` |
| `-D, --description` | description | — |
| `-T, --telegram-id` | telegram id | — |
| `-n, --no-squad-prompt` | don't list squads when `-s` is not given | off |

Squad names are resolved to uuids automatically (case-insensitive). If no squad
with that name exists, the script shows the available squads and stops, so a
user is never created without access by mistake.

### `delete <username>` — delete a user

```bash
rwcli delete john_doe          # asks for confirmation
rwcli delete john_doe -y       # no confirmation
```

### `servers <user>` — subscription servers

```bash
rwcli servers john_doe                              # by username
rwcli servers https://sub.example.com/AbC123        # by subscription URL
rwcli servers AbC123                                # by short_uuid
rwcli servers john_doe --raw                        # vless://... links, one per line
```

By default — a table: name (remark, with flag), protocol, `address:port`.
With `-r/--raw` — connection links, handy for pasting into a client or for scripts.

The token needs the `subscriptions:raw` scope (table) and
`subscriptions:by-short-uuid-protected` (`--raw`).

## Global flags

| Flag | Meaning |
|---|---|
| `-e, --env-file` | config file path (default `.env`) |
| `-u, --panel-url` | override `PANEL_URL` |
| `-t, --token` | override `API_TOKEN` |

## Requirements

- Python ≥ 3.10
- [`rw-sdk`](https://pypi.org/project/rw-sdk/) ≥ 3.3.2 (installed automatically as a dependency)

## Development

```bash
uv venv .venv && uv pip install --python .venv/bin/python -e '.[test]'
.venv/bin/pytest
```

Tests don't touch the network: the Remnawave client is mocked.

## License

MIT.
