import pytest

from wfm.core.redirects import safe_next


@pytest.mark.parametrize("target", ["/roster", "/roster?week=2026-08-17", "/a/b/c"])
def test_same_site_paths_are_kept(target: str) -> None:
    assert safe_next(target) == target


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example/phish",
        "//evil.example",
        "/\\evil.example",
        "javascript:alert(1)",
        "roster",
        "",
        "/login?x=1",
        "/ok\r\nSet-Cookie: a=b",  # header splitting
        "/ok\x00",
    ],
)
def test_everything_else_falls_back(target: str) -> None:
    assert safe_next(target) == "/"


def test_non_strings_fall_back() -> None:
    assert safe_next(None) == "/"
    assert safe_next(["/a"]) == "/"


def test_the_fallback_can_be_chosen() -> None:
    assert safe_next("//evil", default="/my-schedule") == "/my-schedule"
