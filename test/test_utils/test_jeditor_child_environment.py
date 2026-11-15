"""The programs JEditor starts for the user get the IDE's ``child_environment()``.

PyBreeze's own runs always did. JEditor's Run Program, Run Debugger, shell,
terminal and test panel start processes themselves, and handed them the IDE's
environment as it was: with ``LOCUST_SKIP_MONKEY_PATCH`` in it, a locust script
run from the editor ran one user at a time.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import je_editor
import pytest

from pybreeze.pybreeze_ui.editor_main import main_ui
from pybreeze.utils.subprocess_util import IDE_ONLY, child_environment
from test_utils.started_window import run_started_window

_HAS_THE_HOOK = hasattr(je_editor, "set_child_environment_provider")
needs_the_hook = pytest.mark.skipif(not _HAS_THE_HOOK, reason="this JEditor has no child environment hook yet")


@pytest.fixture
def unregistered():
    """Leave JEditor as it was found: with no provider."""
    yield
    if _HAS_THE_HOOK:
        je_editor.set_child_environment_provider(None)


@needs_the_hook
def test_jeditor_is_given_the_ides_child_environment(unregistered, monkeypatch):
    monkeypatch.setenv("ONLY_FOR_THE_IDE", IDE_ONLY)
    monkeypatch.setenv("FOR_EVERY_PROGRAM", "kept")

    assert main_ui.give_jeditor_the_child_environment() is True

    given = je_editor.child_environment()
    assert "ONLY_FOR_THE_IDE" not in given
    assert given["FOR_EVERY_PROGRAM"] == "kept"
    assert given == child_environment()


@needs_the_hook
def test_a_variable_set_after_registering_is_seen_by_the_next_program(unregistered, monkeypatch):
    main_ui.give_jeditor_the_child_environment()

    monkeypatch.setenv("SET_LATER", "seen")

    assert je_editor.child_environment()["SET_LATER"] == "seen"


def test_a_jeditor_without_the_hook_is_left_as_it_is(monkeypatch):
    # 1.0.34 and earlier: the IDE must still start
    monkeypatch.delattr(je_editor, "set_child_environment_provider", raising=False)
    logged = []
    monkeypatch.setattr(main_ui.pybreeze_logger, "info", lambda *args: logged.append(args))

    assert main_ui.give_jeditor_the_child_environment() is False
    assert len(logged) == 1


_WHAT_A_PROGRAM_STARTED_FROM_THE_EDITOR_GETS = """
import os
import je_editor
given = je_editor.child_environment() if hasattr(je_editor, "child_environment") else None
result = {"has_hook": given is not None,
          "the_ide_has_it": "LOCUST_SKIP_MONKEY_PATCH" in os.environ,
          "a_child_gets_it": given is not None and "LOCUST_SKIP_MONKEY_PATCH" in given,
          "a_child_keeps_the_rest": given is not None and given.get("PATH") == os.environ.get("PATH")}
"""


def test_in_the_started_ide_locusts_switch_stays_out_of_what_the_editor_runs(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCUST_SKIP_MONKEY_PATCH", raising=False)

    seen = run_started_window(tmp_path, _WHAT_A_PROGRAM_STARTED_FROM_THE_EDITOR_GETS)

    assert seen["the_ide_has_it"]
    if not seen["has_hook"]:
        pytest.skip("this JEditor has no child environment hook yet")
    assert not seen["a_child_gets_it"]
    assert seen["a_child_keeps_the_rest"]
