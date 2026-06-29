"""Regression tests for the uv script entrypoint in src/backend/run.py."""

from pathlib import Path


RUN_SCRIPT = Path(__file__).resolve().parents[1] / "src/backend/run.py"


def _read_script_dependencies() -> list[str]:
    lines = RUN_SCRIPT.read_text().splitlines()

    in_dependencies = False
    dependencies: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == "# dependencies = [":
            in_dependencies = True
            continue
        if in_dependencies and stripped == "# ]":
            break
        if in_dependencies:
            dependencies.append(stripped.removeprefix("#").strip().strip('",'))

    return [dependency for dependency in dependencies if dependency]


def test_run_script_declares_dashboard_serve_dependencies() -> None:
    dependencies = _read_script_dependencies()

    assert "fastapi" in dependencies
    assert "uvicorn[standard]" in dependencies
