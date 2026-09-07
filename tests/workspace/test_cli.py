from __future__ import annotations

import builtins

import pytest

from evalops.cli import _build_parser, main


def test_workspace_help_exposes_only_supported_options(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit) as result:
        parser.parse_args(["workspace", "--help"])

    assert result.value.code == 0
    help_text = capsys.readouterr().out
    assert "--root" in help_text
    assert "--port" in help_text
    assert "--no-open" in help_text
    assert "--host" not in help_text


def test_workspace_parser_accepts_root_port_and_no_open_without_host() -> None:
    parser = _build_parser()

    args = parser.parse_args(
        ["workspace", "--root", "C:/tmp/evalops", "--port", "8123", "--no-open"]
    )

    assert args.root.as_posix() == "C:/tmp/evalops"
    assert args.port == 8123
    assert args.no_open is True


def test_workspace_dependency_error_is_actionable_and_has_no_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_import = builtins.__import__

    def missing_workspace_dependency(name: str, *args: object, **kwargs: object) -> object:
        if name == "fastapi":
            raise ModuleNotFoundError("No module named 'fastapi'", name="fastapi")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_workspace_dependency)

    exit_code = main(["workspace", "--no-open"])
    captured = capsys.readouterr()

    assert exit_code != 0
    assert 'pip install "evalops-lab[workspace]"' in captured.err
    assert "Traceback" not in captured.err
