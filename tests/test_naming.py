"""D-016: the project was renamed AgentProof -> RegressAgent (the old PyPI name belongs to another
project, D-013). Keep the old name out of code, tests, examples and package metadata."""
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = "agentproof"
# Files that legitimately talk about the old name (history / warnings).
ALLOWED = {"test_naming.py", "test_packaging.py"}


def scanned_files():
    for folder in ("src", "scripts", "examples", "tests"):
        for path in sorted((ROOT / folder).rglob("*")):
            if (
                path.is_file()
                and path.name not in ALLOWED
                and path.suffix in {".py", ".toml", ".json", ".sh", ".md"}
                and "__pycache__" not in path.parts
                and ".egg-info" not in str(path)
            ):
                yield path


def test_old_name_is_gone_from_code_tests_and_examples():
    offenders = [str(p.relative_to(ROOT)) for p in scanned_files() if OLD in p.read_text(encoding="utf-8", errors="ignore").lower()]
    assert offenders == []


def test_package_and_command_use_the_new_name():
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert meta["name"] == "regressagent"
    assert meta["scripts"] == {"regressagent": "regressagent.cli:main"}
    assert (ROOT / "src" / "regressagent" / "cli.py").is_file()
    assert not (ROOT / "src" / OLD).exists()
    assert (ROOT / "examples" / "regressagent.example.toml").is_file()


def test_old_environment_variable_and_defaults_are_not_used():
    from regressagent import cli

    text = Path(cli.__file__).read_text(encoding="utf-8")
    assert "REGRESSAGENT_DB" in text and "regressagent.db" in text
    assert "AGENTPROOF" not in text
