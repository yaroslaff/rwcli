from argparse import Namespace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from rw_sdk import errors

import rwcli

SQUAD_UUID = "11111111-2222-3333-4444-555555555555"


def make_squad(name="Default", uuid=SQUAD_UUID):
    return SimpleNamespace(uuid=uuid, name=name, inbounds=[], info=SimpleNamespace(members_count=0))


def make_user(**kw):
    data = dict(
        id=1, username="alice", short_uuid="abc", status="ACTIVE",
        expire_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        traffic_limit_bytes=0, traffic_limit_strategy="NO_RESET",
        user_traffic=SimpleNamespace(used_traffic_bytes=2048),
        telegram_id=None, email=None, description=None, tag=None, hwid_device_limit=None,
        active_internal_squads=[make_squad()],
        subscription_url="https://sub/abc", vless_uuid="v", trojan_password="t", ss_password="s",
    )
    data.update(kw)
    return SimpleNamespace(**data)


def parse(*argv):
    return rwcli.build_parser().parse_args(list(argv))


# ---------- конфиг ----------

def test_load_env(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# comment\nPANEL_URL="https://rw.example.com"\n\nAPI_TOKEN=\'tok\'\nbroken\n')
    assert rwcli.load_env(f) == {"PANEL_URL": "https://rw.example.com", "API_TOKEN": "tok"}


def test_load_env_missing(tmp_path):
    assert rwcli.load_env(tmp_path / "nope") == {}


def test_get_client_precedence(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('PANEL_URL="https://file"\nAPI_TOKEN="file-tok"\n')
    monkeypatch.setenv("API_TOKEN", "env-tok")
    monkeypatch.delenv("PANEL_URL", raising=False)
    fake = MagicMock()
    monkeypatch.setattr(rwcli, "Remnawave", fake)

    rwcli.get_client(parse("-e", str(env), "-u", "https://flag", "squads"))
    fake.assert_called_once_with("https://flag", token="env-tok")


def test_get_client_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("PANEL_URL", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="PANEL_URL"):
        rwcli.get_client(parse("-e", str(tmp_path / "nope"), "squads"))


def test_get_client_markdown_url(monkeypatch):
    monkeypatch.setattr(rwcli, "Remnawave", MagicMock())
    with pytest.raises(SystemExit, match="битым"):
        rwcli.get_client(parse("-u", "[x](https://x)", "-t", "t", "squads"))


# ---------- утилиты ----------

@pytest.mark.parametrize("n, expected", [
    (None, "-"),
    (0, "0 B"),
    (512, "512.0 B"),
    (2048, "2.0 KB"),
    (5 * 1024 ** 3, "5.0 GB"),
])
def test_fmt_bytes(n, expected):
    assert rwcli.fmt_bytes(n) == expected


def test_fmt_limit():
    assert rwcli.fmt_limit(0) == "∞"
    assert rwcli.fmt_limit(2048) == "2.0 KB"


def test_users_table_zero_traffic(capsys):
    rw = MagicMock()
    rw.users.iter_users.return_value = [make_user(user_traffic=SimpleNamespace(used_traffic_bytes=0))]
    rwcli.cmd_users(rw, parse("users"))
    assert "traffic=0 B/∞" in capsys.readouterr().out


def test_fmt_dt():
    tz = timezone(timedelta(hours=3))
    assert rwcli.fmt_dt(datetime(2030, 1, 1, 3, 0, tzinfo=tz)) == "2030-01-01 00:00 UTC"
    assert rwcli.fmt_dt(None) == "-"


def test_is_uuid():
    assert rwcli.is_uuid(SQUAD_UUID)
    assert not rwcli.is_uuid("Default")


def test_resolve_squads_by_name_case_insensitive():
    rw = MagicMock()
    rw.internal_squads.get_internal_squads.return_value.internal_squads = [make_squad("Default")]
    assert rwcli.resolve_squads(rw, ["default"]) == [SQUAD_UUID]


def test_resolve_squads_uuids_skip_api():
    rw = MagicMock()
    assert rwcli.resolve_squads(rw, [SQUAD_UUID]) == [SQUAD_UUID]
    rw.internal_squads.get_internal_squads.assert_not_called()


def test_resolve_squads_unknown():
    rw = MagicMock()
    rw.internal_squads.get_internal_squads.return_value.internal_squads = [make_squad("Default")]
    with pytest.raises(SystemExit, match="nope"):
        rwcli.resolve_squads(rw, ["nope"])


def test_die_on_api_error_not_found():
    body = {"errorCode": "A063", "message": "User not found"}
    exc = errors.NotFoundError("not found", response=SimpleNamespace(status_code=404), body=body)

    @rwcli.die_on_api_error
    def boom():
        raise exc

    with pytest.raises(SystemExit, match="Не найдено: A063"):
        boom()


# ---------- команды ----------

def test_users_fields_tsv(capsys):
    rw = MagicMock()
    rw.users.iter_users.return_value = [make_user()]
    rwcli.cmd_users(rw, parse("users", "-f", "username,traffic_used_bytes,squads,expire_at"))
    assert capsys.readouterr().out == "alice\t2048\tDefault\t2030-01-01T00:00:00+00:00\n"


def test_users_unknown_field():
    with pytest.raises(SystemExit, match="Неизвестные поля: bogus"):
        rwcli.cmd_users(MagicMock(), parse("users", "-f", "username,bogus"))


def test_users_empty(capsys):
    rw = MagicMock()
    rw.users.iter_users.return_value = []
    rwcli.cmd_users(rw, parse("users"))
    assert "не найдены" in capsys.readouterr().err


def test_create(capsys):
    rw = MagicMock()
    rw.internal_squads.get_internal_squads.return_value.internal_squads = [make_squad("Default")]
    rw.users.create_user.return_value = make_user(username="bob")

    rwcli.cmd_create(rw, parse("create", "bob", "-s", "Default", "-d", "10", "-g", "2"))

    kw = rw.users.create_user.call_args.kwargs
    assert kw["username"] == "bob"
    assert kw["active_internal_squads"] == [SQUAD_UUID]
    assert kw["traffic_limit_bytes"] == 2 * 1024 ** 3
    delta = kw["expire_at"] - datetime.now(timezone.utc)
    assert timedelta(days=9, hours=23) < delta <= timedelta(days=10)
    assert "Создан пользователь" in capsys.readouterr().out


def test_delete_cancelled(monkeypatch):
    rw = MagicMock()
    rw.users.get_user_by_username.return_value = make_user()
    monkeypatch.setattr("builtins.input", lambda _: "n")
    rwcli.cmd_delete(rw, parse("delete", "alice"))
    rw.users.delete_user.assert_not_called()


def test_delete_yes():
    rw = MagicMock()
    rw.users.get_user_by_username.return_value = make_user(id=42)
    rwcli.cmd_delete(rw, parse("delete", "alice", "-y"))
    rw.users.delete_user.assert_called_once_with(42)
