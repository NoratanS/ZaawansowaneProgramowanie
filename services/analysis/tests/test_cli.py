import re

import jwt
import pytest

from analysis_service.cli import generate_keys, issue_token

pytestmark = pytest.mark.unit


def test_issue_token_prints_a_30_day_client_token(
    monkeypatch, capsys, jwt_keys, read_token
):
    monkeypatch.setenv("JWT_PRIVATE_KEY", jwt_keys.private)

    issue_token(["--sub", "alice"])

    claims = read_token(capsys.readouterr().out.strip(), "analysis-service")
    assert claims["sub"] == "alice"
    assert claims["exp"] - claims["iat"] == 30 * 24 * 3600


def test_issue_token_ttl_is_in_seconds(monkeypatch, capsys, jwt_keys, read_token):
    monkeypatch.setenv("JWT_PRIVATE_KEY", jwt_keys.private)

    issue_token(["--sub", "bob", "--ttl", "3600"])

    claims = read_token(capsys.readouterr().out.strip(), "analysis-service")
    assert claims["exp"] - claims["iat"] == 3600


def test_issue_token_requires_a_sub(monkeypatch, jwt_keys):
    monkeypatch.setenv("JWT_PRIVATE_KEY", jwt_keys.private)

    with pytest.raises(SystemExit):
        issue_token([])


def _env_value(text, name):
    [value] = re.findall(rf'^{name}="(.*?)"$', text, flags=re.M | re.S)
    return value


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path / ".env"


def test_generate_keys_appends_a_working_quoted_pem_pair(in_tmp, capsys):
    in_tmp.write_text("POSTGRES_PASSWORD=dev\n")

    generate_keys([])

    text = in_tmp.read_text()
    assert text.startswith("POSTGRES_PASSWORD=dev\n")
    private = _env_value(text, "JWT_PRIVATE_KEY")
    public = _env_value(text, "JWT_PUBLIC_KEY")
    assert private.startswith("-----BEGIN PRIVATE KEY-----\n")
    assert public.startswith("-----BEGIN PUBLIC KEY-----\n")
    token = jwt.encode({"sub": "x"}, private, algorithm="RS256")
    assert jwt.decode(token, public, algorithms=["RS256"])["sub"] == "x"
    assert "PRIVATE KEY" not in capsys.readouterr().out


def test_generate_keys_creates_a_missing_env_file(in_tmp):
    generate_keys([])

    assert _env_value(in_tmp.read_text(), "JWT_PUBLIC_KEY")


def test_generate_keys_replaces_the_empty_placeholders(in_tmp):
    # .env.example ships the two keys empty.
    in_tmp.write_text('JWT_PRIVATE_KEY=\nLOG_LEVEL=INFO\nJWT_PUBLIC_KEY=""\n')

    generate_keys([])

    text = in_tmp.read_text()
    assert text.count("JWT_PRIVATE_KEY=") == 1
    assert text.count("JWT_PUBLIC_KEY=") == 1
    assert "LOG_LEVEL=INFO\n" in text


@pytest.mark.parametrize("name", ["JWT_PRIVATE_KEY", "JWT_PUBLIC_KEY"])
def test_generate_keys_refuses_when_a_key_is_present(in_tmp, capsys, name):
    in_tmp.write_text(f'{name}="-----BEGIN KEY-----\nabc\n-----END KEY-----\n"\n')
    before = in_tmp.read_text()

    with pytest.raises(SystemExit) as exit_info:
        generate_keys([])

    assert exit_info.value.code != 0
    assert name in capsys.readouterr().err
    assert in_tmp.read_text() == before


@pytest.mark.parametrize("existing", [False, True], ids=["new", "existing"])
def test_generate_keys_leaves_env_readable_only_by_its_owner(in_tmp, existing):
    if existing:
        in_tmp.write_text("LOG_LEVEL=INFO\n")
        in_tmp.chmod(0o644)

    generate_keys([])

    assert in_tmp.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "placeholder",
    ["JWT_PRIVATE_KEY= ", "export JWT_PRIVATE_KEY=", "JWT_PRIVATE_KEY= # set me"],
    ids=["trailing-space", "export", "comment"],
)
def test_generate_keys_replaces_other_empty_forms(in_tmp, placeholder):
    in_tmp.write_text(f"{placeholder}\nLOG_LEVEL=INFO\n")

    generate_keys([])

    text = in_tmp.read_text()
    assert text.count("JWT_PRIVATE_KEY") == 1
    assert "LOG_LEVEL=INFO\n" in text


@pytest.mark.parametrize("ttl", ["0", "-60", "nan", "inf"])
def test_issue_token_ttl_must_be_positive_and_finite(monkeypatch, jwt_keys, ttl):
    monkeypatch.setenv("JWT_PRIVATE_KEY", jwt_keys.private)

    with pytest.raises(SystemExit):
        issue_token(["--sub", "alice", "--ttl", ttl])
