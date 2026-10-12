import pytest

from config.settings._env import broker_url_from_env, database_from_env


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("valkey://:pw@localhost:6379", "redis://:pw@localhost:6379"),
        ("valkeys://:pw@host:6380/1", "rediss://:pw@host:6380/1"),
        ("redis://localhost:6379/0", "redis://localhost:6379/0"),
    ],
)
def test_broker_url_accepts_valkey_schemes(
    monkeypatch: pytest.MonkeyPatch, given: str, expected: str
) -> None:
    monkeypatch.setenv("WFM_BROKER_URL", given)
    assert broker_url_from_env() == expected


def test_database_url_is_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://wfm:p%40ss@db.internal:5433/wfmdb")
    assert database_from_env() == {
        "NAME": "wfmdb",
        "USER": "wfm",
        "PASSWORD": "p@ss",
        "HOST": "db.internal",
        "PORT": "5433",
    }
