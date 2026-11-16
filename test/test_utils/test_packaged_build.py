"""Knowing a packaged build, and the check CI runs on one (exe/check_build.py).

In a packaged build ``sys.executable`` is PyBreeze itself: started as a Python,
it would open a second IDE. PyInstaller marks such a build with ``sys.frozen``,
Nuitka with a ``__compiled__`` global whose ``standalone`` is true.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pybreeze.extend.language_server import packaged_entry, server_main
from pybreeze.utils import packaged_build
from pybreeze.utils.packaged_build import is_packaged

_EXE = Path(__file__).resolve().parents[2] / "exe"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"exe_{name}", _EXE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestKnowingAPackagedBuild:
    def test_run_from_source_it_is_not(self):
        assert is_packaged() is False

    def test_a_pyinstaller_build_is(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)

        assert is_packaged() is True

    def test_a_standalone_nuitka_build_is(self, monkeypatch):
        monkeypatch.setitem(packaged_build.__dict__, "__compiled__", SimpleNamespace(standalone=True))

        assert is_packaged() is True

    def test_a_nuitka_build_that_runs_under_a_python_is_not(self, monkeypatch):
        # Its sys.executable is a real Python
        monkeypatch.setitem(packaged_build.__dict__, "__compiled__", SimpleNamespace(standalone=False))

        assert is_packaged() is False

    def test_every_place_that_starts_sys_executable_asks_the_same_question(self):
        # A check of its own somewhere, on sys.frozen alone, missed a Nuitka build
        package = Path(packaged_build.__file__).resolve().parents[1]
        asking_alone = [path.name for path in package.rglob("*.py")
                        if path.name != "packaged_build.py" and "\"frozen\"" in path.read_text(encoding="utf-8")]

        assert asking_alone == []


class TestTheBuildSaysWhatItIs:
    def test_build_info_is_one_json_line_and_nothing_else_starts(self, monkeypatch, capsys):
        monkeypatch.setattr(server_main, "main", lambda _arguments: pytest.fail("the server was started"))
        monkeypatch.setitem(packaged_build.__dict__, "__compiled__", SimpleNamespace(standalone=True))

        assert packaged_entry.served_instead([packaged_entry.BUILD_INFO_ARGUMENT]) == 0

        said = json.loads(capsys.readouterr().out)
        assert said == {"packaged": True, "executable": sys.executable}


class TestTheCheckOfABuild:
    @pytest.fixture(scope="class")
    def check(self):
        return _load("check_build")

    def test_a_message_is_framed_and_read_back(self, check):
        framed = check._encode({"jsonrpc": "2.0", "id": 1, "result": {"ok": "是"}})

        assert check._read_message(io.BytesIO(framed)) == {"jsonrpc": "2.0", "id": 1, "result": {"ok": "是"}}

    def test_a_stream_that_ends_is_no_message(self, check):
        assert check._read_message(io.BytesIO(b"")) is None
        assert check._read_message(io.BytesIO(b"X-Other: 1\r\n\r\n")) is None

    def test_something_that_takes_too_long_is_a_timeout(self, check):
        import threading

        never = threading.Event()
        with pytest.raises(TimeoutError):
            check._in_time(never.wait, 0.05)
        never.set()

    def test_without_an_executable_it_says_how_to_run_it(self, check, capsys):
        assert check.main([]) == 2
        assert check.main(["no/such/PyBreeze.exe"]) == 2
        assert "usage" in capsys.readouterr().err

    def test_a_failed_check_fails_the_run_and_the_rest_still_run(self, check, monkeypatch, tmp_path, capsys):
        executable = tmp_path / "PyBreeze.exe"
        executable.write_bytes(b"")

        def failing(_executable):
            raise AssertionError("the build does not know it is packaged")

        monkeypatch.setattr(check, "CHECKS", (("first", failing), ("second", lambda _executable: "fine")))

        assert check.main([str(executable)]) == 1
        said = capsys.readouterr().out
        assert "[FAIL] first: the build does not know it is packaged" in said
        assert "[pass] second: fine" in said


class TestTheBuildCommand:
    @pytest.fixture(scope="class")
    def build(self):
        return _load("build_nuitka")

    def test_it_builds_the_start_script_standalone_with_both_packages(self, build):
        command = build.nuitka_command()

        assert command[1:3] == ["-m", "nuitka"]
        assert "--mode=standalone" in command
        assert {"--include-package=pybreeze", "--include-package=je_editor"} <= set(command)
        assert command[-1].endswith("start_pybreeze.py")

    def test_it_never_asks_a_question_ci_could_not_answer(self, build):
        assert "--assume-yes-for-downloads" in build.nuitka_command()

    def test_ci_checks_the_executable_where_the_build_puts_it(self, build):
        workflow = (_EXE.parent / ".github" / "workflows" / "dev.yml").read_text(encoding="utf-8")
        built = (build.DIST_DIR / "PyBreeze.exe").relative_to(_EXE.parent).as_posix()

        assert "--output-filename=PyBreeze" in build.nuitka_command()
        assert f"python exe/check_build.py {built}" in workflow
