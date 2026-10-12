import json
from pathlib import Path

from django.core.management import call_command


def test_export_contains_the_auth_endpoints_and_is_stable(tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"

    call_command("export_openapi", str(first))
    call_command("export_openapi", str(second))

    schema = json.loads(first.read_text(encoding="utf-8"))
    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/auth/me" in schema["paths"]
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
