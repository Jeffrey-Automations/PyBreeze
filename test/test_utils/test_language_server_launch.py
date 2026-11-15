"""The action language server is the one JEditor's editors start for a JSON file."""
from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from je_editor.utils.lsp import language_servers

from pybreeze.extend.language_server import launch, packaged_entry, server_main
from test_utils.started_window import run_started_window


def test_the_command_starts_the_servers_entry_with_the_ides_own_interpreter():
    command = launch.server_command(None, "English")

    assert command[0] == sys.executable
    assert Path(command[1]).is_file() and Path(command[1]).name == "__main__.py"
    assert Path(command[1]).parent.name == "language_server"
    assert command[2:] == ["--language", "English"]


def test_the_entry_is_named_by_its_path_so_the_working_folder_is_not_on_the_servers_import_path():
    command = launch.server_command(None, "English")

    assert "-m" not in command
    assert Path(command[1]).is_absolute()


def test_the_interpreter_that_runs_the_scripts_is_passed_on_when_there_is_one():
    assert launch.server_command("C:/project/.venv/python", "Traditional_Chinese")[2:] == [
        "--language", "Traditional_Chinese", "--interpreter", "C:/project/.venv/python"]


def test_a_packaged_build_starts_itself_as_the_server(monkeypatch):
    # It has no interpreter to give a path to: sys.executable is the application
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert launch.server_command(None, "English") == [
        sys.executable, packaged_entry.SERVER_ARGUMENT, "--language", "English"]
    assert launch.server_command("C:/tools/python", "English")[2:] == [
        "--language", "English", "--interpreter", "C:/tools/python"]


def test_once_offered_the_server_is_what_jeditor_starts_for_a_json_file(monkeypatch):
    monkeypatch.setitem(language_servers.DEFAULT_SERVERS, launch.ACTION_SCRIPT_SUFFIX, ["some-other-server"])

    launch.offer_to_jeditor(None, "English")

    # JEditor's own lookup, which also checks that the command exists
    assert language_servers.server_command(".json") == launch.server_command(None, "English")
    assert language_servers.server_command(".JSON") == launch.server_command(None, "English")


def test_other_files_keep_the_server_jeditor_names_for_them(monkeypatch):
    before = {suffix: list(command) for suffix, command in language_servers.DEFAULT_SERVERS.items()}
    monkeypatch.setitem(language_servers.DEFAULT_SERVERS, launch.ACTION_SCRIPT_SUFFIX, ["some-other-server"])

    launch.offer_to_jeditor(None, "English")

    after = dict(language_servers.DEFAULT_SERVERS)
    assert {suffix: command for suffix, command in after.items() if suffix != ".json"} == {
        suffix: command for suffix, command in before.items() if suffix != ".json"}


_AN_EDITOR_ASKS_THE_SERVER = """
from pathlib import Path
from PySide6.QtCore import QEventLoop, QTimer
from je_editor import EditorWidget
from je_editor.utils.lsp.language_servers import DEFAULT_SERVERS

script = Path("script.json").resolve()
script.write_text('[["WR_quit"] ["WR_quit"]]', encoding="utf-8")
editors = [window.tab_widget.widget(index) for index in range(window.tab_widget.count())
           if isinstance(window.tab_widget.widget(index), EditorWidget)]
result = {"command": DEFAULT_SERVERS.get(".json"), "language": language_wrapper.language,
          "editors": len(editors), "started": False, "diagnostics": []}
if editors:
    code_edit = editors[0].code_edit
    received = []
    waiting = QEventLoop()
    code_edit.lsp_client.diagnostics_ready.connect(received.append)
    code_edit.lsp_client.diagnostics_ready.connect(waiting.quit)
    code_edit.current_file = str(script)
    code_edit.setPlainText(script.read_text(encoding="utf-8"))
    result["started"] = code_edit.start_language_server()
    if result["started"] and not received:
        QTimer.singleShot(30000, waiting.quit)
        waiting.exec()
    result["diagnostics"] = received[0] if received else []
    code_edit.lsp_client.stop()
"""


def test_the_started_ide_offers_the_server_and_an_editor_gets_diagnostics_from_it(tmp_path):
    seen = run_started_window(tmp_path, _AN_EDITOR_ASKS_THE_SERVER)

    assert seen["command"][1].endswith("__main__.py")
    assert seen["command"][2:4] == ["--language", seen["language"]]
    assert "--interpreter" in seen["command"]
    assert seen["editors"] >= 1
    assert seen["started"], "the editor did not start the language server for a .json file"
    assert len(seen["diagnostics"]) == 1, seen["diagnostics"]
    assert "JSON" in str(seen["diagnostics"][0])


# ----------------------------------------------------------------------
# The application as its own server (a packaged build)
# ----------------------------------------------------------------------

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("arguments", [
    [], ["--debug"], ["script.json"], ["--language", packaged_entry.SERVER_ARGUMENT]])
def test_arguments_that_do_not_ask_for_the_server_are_the_ides(monkeypatch, arguments):
    monkeypatch.setattr(server_main, "main", lambda _arguments: pytest.fail("the server was started"))

    assert packaged_entry.served_instead(arguments) is None


def test_the_servers_argument_first_makes_the_process_the_server(monkeypatch):
    given: list[list[str]] = []
    monkeypatch.setattr(server_main, "main", lambda arguments: given.append(arguments) or 3)

    code = packaged_entry.served_instead([packaged_entry.SERVER_ARGUMENT, "--language", "English"])

    assert code == 3
    assert given == [["--language", "English"]]


@pytest.mark.parametrize("start", ["module", "packaged script"])
def test_a_start_script_serves_instead_of_opening_the_ide(monkeypatch, start):
    import pybreeze

    started: list = []
    monkeypatch.setattr(pybreeze, "start_editor", lambda: started.append("started"))
    monkeypatch.setattr(server_main, "main", lambda _arguments: 0)
    monkeypatch.setattr(sys, "argv", ["PyBreeze", packaged_entry.SERVER_ARGUMENT, "--language", "English"])

    with pytest.raises(SystemExit) as ended:
        if start == "module":
            runpy.run_module("pybreeze.__main__", run_name="__main__")
        else:
            runpy.run_path(str(_REPOSITORY_ROOT / "exe" / "start_pybreeze.py"), run_name="__main__")

    assert ended.value.code == 0
    assert started == []


def test_the_packaged_start_script_opens_the_ide_otherwise(monkeypatch):
    import pybreeze

    started: list = []
    monkeypatch.setattr(pybreeze, "start_editor", lambda: started.append("started"))
    monkeypatch.setattr(sys, "argv", ["PyBreeze"])

    runpy.run_path(str(_REPOSITORY_ROOT / "exe" / "start_pybreeze.py"), run_name="__main__")

    assert started == ["started"]


def _child_environment() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": os.pathsep.join(
        filter(None, [str(_REPOSITORY_ROOT), os.environ.get("PYTHONPATH")]))}


def test_a_process_that_is_only_the_server_loads_neither_qt_nor_jeditor(tmp_path):
    done = subprocess.run(  # noqa: S603 — fixed argv: this interpreter and a literal script
        [sys.executable, "-c",
         "import sys\n"
         "import pybreeze.extend.language_server.packaged_entry\n"
         "print('PySide6' in sys.modules, 'je_editor' in sys.modules)"],
        cwd=tmp_path, env=_child_environment(), capture_output=True, timeout=60, check=False, shell=False)

    assert done.stdout.decode().strip() == "False False", done.stderr.decode(errors="replace")


def test_started_with_the_servers_argument_the_application_speaks_the_protocol(tmp_path):
    from pybreeze.utils.language_service.lsp_server import encode, read_message

    server = subprocess.Popen(  # noqa: S603 — fixed argv: this interpreter running PyBreeze's own start script
        [sys.executable, "-m", "pybreeze", packaged_entry.SERVER_ARGUMENT, "--language", "English"],
        cwd=tmp_path, env=_child_environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, shell=False)
    try:
        server.stdin.write(encode({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                   "params": {"processId": None, "rootUri": None, "capabilities": {}}}))
        server.stdin.flush()
        reply = read_message(server.stdout)
        server.stdin.write(encode({"jsonrpc": "2.0", "id": 2, "method": "shutdown"}))
        server.stdin.write(encode({"jsonrpc": "2.0", "method": "exit"}))
        server.stdin.flush()
        code = server.wait(60)
    finally:
        if server.poll() is None:
            server.kill()
        server.stdin.close()
        server.stdout.close()

    assert reply["id"] == 1 and "capabilities" in reply["result"]
    assert code == 0


def test_a_packaged_build_with_no_python_asks_no_framework_by_starting_itself(monkeypatch):
    # sys.executable is the IDE there: run as "the interpreter" it would open another one
    from pybreeze.utils.exception.exception_tags import language_probe_no_interpreter_error
    from pybreeze.utils.exception.exceptions import LanguageServiceException
    from pybreeze.utils.language_service import metadata_probe
    from pybreeze.utils.language_service.framework_profiles import PROFILES

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(metadata_probe.subprocess, "run", lambda *_a, **_k: pytest.fail("a process was started"))

    with pytest.raises(LanguageServiceException) as refused:
        metadata_probe.read_metadata(PROFILES[0], None)

    assert str(refused.value) == language_probe_no_interpreter_error.format(framework=PROFILES[0].framework)


# ----------------------------------------------------------------------
# Another interpreter chosen while the IDE is open
# ----------------------------------------------------------------------

def _window_class():
    from pybreeze.pybreeze_ui.editor_main.main_ui import PyBreezeMainWindow

    return PyBreezeMainWindow


class _Window:
    """Stands in for the main window: the property and what it calls, without a window."""

    def __init__(self) -> None:
        self.offers: list[str | None] = []

    def _offer_language_server(self) -> None:
        self._language_server_offered = True
        self.offers.append(self.python_compiler)


@pytest.fixture
def window():
    _Window.python_compiler = _window_class().python_compiler
    return _Window()


def test_no_interpreter_is_chosen_to_begin_with(window):
    assert window.python_compiler is None


def test_an_interpreter_set_while_the_window_is_being_built_offers_nothing_yet(window):
    # JEditor sets it in its own __init__, before there are menus or tabs
    window.python_compiler = "C:/project/.venv/python"

    assert window.python_compiler == "C:/project/.venv/python"
    assert window.offers == []


def test_another_interpreter_chosen_later_offers_the_server_again(window):
    window._offer_language_server()

    window.python_compiler = "C:/project/.venv/python"
    window.python_compiler = None

    assert window.offers == [None, "C:/project/.venv/python", None]


def test_the_same_interpreter_set_again_changes_nothing(window):
    window.python_compiler = "C:/project/.venv/python"
    window._offer_language_server()

    window.python_compiler = "C:/project/.venv/python"

    assert window.offers == ["C:/project/.venv/python"]


def test_the_chosen_interpreter_is_the_one_the_server_asks(monkeypatch):
    from pybreeze.pybreeze_ui.editor_main import main_ui

    monkeypatch.setattr(main_ui, "default_interpreter", lambda: pytest.fail("the default was looked for"))

    chosen = _window_class()._script_interpreter(SimpleNamespace(python_compiler="C:/project/.venv/python"))

    assert chosen == "C:/project/.venv/python"


def test_with_none_chosen_it_is_the_default(monkeypatch):
    from pybreeze.pybreeze_ui.editor_main import main_ui

    monkeypatch.setattr(main_ui, "default_interpreter", lambda: "C:/default/python")

    assert _window_class()._script_interpreter(SimpleNamespace(python_compiler=None)) == "C:/default/python"


def test_a_packaged_build_that_finds_no_python_still_offers_the_server(monkeypatch):
    from je_editor import JEditorExecException

    from pybreeze.pybreeze_ui.editor_main import main_ui

    def none_found():
        raise JEditorExecException("no Python on PATH")

    monkeypatch.setattr(main_ui, "default_interpreter", none_found)

    assert _window_class()._script_interpreter(SimpleNamespace(python_compiler=None)) is None


_ANOTHER_INTERPRETER_IS_CHOSEN = """
import sys
from pathlib import Path
from PySide6.QtCore import QEventLoop, QTimer
from je_editor import EditorWidget
from je_editor.utils.lsp.language_servers import DEFAULT_SERVERS

script = Path("script.json").resolve()
script.write_text('[["WR_quit"]]', encoding="utf-8")
editor = next(window.tab_widget.widget(index) for index in range(window.tab_widget.count())
              if isinstance(window.tab_widget.widget(index), EditorWidget))
code_edit = editor.code_edit
code_edit.current_file = str(script)
code_edit.setPlainText(script.read_text(encoding="utf-8"))
code_edit.start_language_server()
before = list(code_edit.lsp_client._server_command)

# Chosen the way JEditor's Python Env menu does it: a plain assignment
# The same Python under another spelling: a different choice that still runs
chosen = str(Path(sys.executable).parent) + "/./" + Path(sys.executable).name
window.python_compiler = chosen

received = []
waiting = QEventLoop()
code_edit.lsp_client.diagnostics_ready.connect(received.append)
code_edit.lsp_client.diagnostics_ready.connect(waiting.quit)
QTimer.singleShot(30000, waiting.quit)
waiting.exec()
result = {"chosen": chosen, "before": before, "offered": DEFAULT_SERVERS.get(".json"),
          "after": list(code_edit.lsp_client._server_command), "running": code_edit.lsp_client.running,
          "answered": bool(received)}
code_edit.lsp_client.stop()
"""


def test_choosing_another_interpreter_moves_the_open_json_editors_to_a_server_for_it(tmp_path):
    seen = run_started_window(tmp_path, _ANOTHER_INTERPRETER_IS_CHOSEN)

    assert seen["offered"][-2:] == ["--interpreter", seen["chosen"]]
    assert seen["after"] == seen["offered"]
    assert seen["before"] != seen["after"]
    assert seen["running"]
    assert seen["answered"], "the editor heard nothing from the new server"

