"""Build the PyBreeze executable with Nuitka.

Run from the repository's root, in an environment that has PyBreeze's
requirements and ``dev_requirements.txt`` (which pins Nuitka)::

    python exe/build_nuitka.py

The result is a folder, ``exe/build/start_pybreeze.dist``, holding ``PyBreeze``
(``PyBreeze.exe`` on Windows) and everything it needs. Nuitka compiles the
package to C, so a C compiler has to be there; on Windows Nuitka offers to
download one the first time.

The executable is a console program on purpose: started with
``--action-language-server`` it is the language server of the action scripts,
which speaks on its standard input and output
(``pybreeze/extend/language_server/packaged_entry.py``).
"""
from __future__ import annotations

import os
import subprocess  # nosec B404 — a fixed argument list, never a shell
import sys
from pathlib import Path

_EXE_DIR = Path(__file__).resolve().parent
_ROOT = _EXE_DIR.parent
_ICON = _ROOT / "pybreeze" / "pybreeze_ui" / "editor_main" / "pybreeze_icon.ico"


def nuitka_command() -> list[str]:
    """The Nuitka command line that builds the executable, as an argument list."""
    command = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        # The packages are imported by name at run time (the automation menus, the plugins)
        "--include-package=pybreeze",
        # The icon, the prompt templates and the other files shipped inside the package
        "--include-package-data=pybreeze",
        "--output-filename=PyBreeze",
        f"--output-dir={_EXE_DIR / 'build'}",
    ]
    if sys.platform == "win32":
        command.append(f"--windows-icon-from-ico={_ICON}")
    command.append(str(_EXE_DIR / "start_pybreeze.py"))
    return command


def main() -> int:
    """Run the build and return Nuitka's exit code."""
    completed = subprocess.run(  # nosec B603  # nosemgrep — fixed argument list, no shell
        nuitka_command(), cwd=_ROOT, env=dict(os.environ), check=False, shell=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
