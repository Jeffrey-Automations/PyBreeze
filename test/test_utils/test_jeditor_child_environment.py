"""The programs JEditor starts for the user get the IDE's ``child_environment()``.

PyBreeze's own runs always did. JEditor's Run Program, Run Debugger, shell,
terminal and test panel start processes themselves, and handed them the IDE's
environment as it was: with ``LOCUST_SKIP_MONKEY_PATCH`` in it, a locust script
run from the editor ran one user at a time.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_utils.started_window import run_started_window

_WHAT_A_PROGRAM_STARTED_FROM_THE_EDITOR_GETS = """
import os
import je_editor
os.environ["SET_AFTER_THE_WINDOW_WAS_BUILT"] = "seen"
given = je_editor.child_environment()
result = {"the_ide_has_it": "LOCUST_SKIP_MONKEY_PATCH" in os.environ,
          "a_child_gets_it": "LOCUST_SKIP_MONKEY_PATCH" in given,
          "a_child_keeps_the_rest": given.get("PATH") == os.environ.get("PATH"),
          "set_later": given.get("SET_AFTER_THE_WINDOW_WAS_BUILT")}
"""


def test_in_the_started_ide_locusts_switch_stays_out_of_what_the_editor_runs(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCUST_SKIP_MONKEY_PATCH", raising=False)

    seen = run_started_window(tmp_path, _WHAT_A_PROGRAM_STARTED_FROM_THE_EDITOR_GETS)

    assert seen["the_ide_has_it"]
    assert not seen["a_child_gets_it"]
    assert seen["a_child_keeps_the_rest"]
    # Asked for every program: the environment as it is when the program starts
    assert seen["set_later"] == "seen"


def test_a_variable_the_user_set_is_passed_on(tmp_path, monkeypatch):
    # Only the value the IDE put there itself is kept out
    monkeypatch.setenv("LOCUST_SKIP_MONKEY_PATCH", "1")

    seen = run_started_window(tmp_path, _WHAT_A_PROGRAM_STARTED_FROM_THE_EDITOR_GETS)

    assert seen["a_child_gets_it"]
