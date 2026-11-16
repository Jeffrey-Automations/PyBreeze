"""Build the PyBreeze executable with Nuitka.

Run from the repository's root, in an environment that has PyBreeze's
requirements and ``dev_requirements.txt`` (which pins Nuitka)::

    python exe/build_nuitka.py

The result is a folder, ``exe/build/start_pybreeze.dist``, holding ``PyBreeze``
(``PyBreeze.exe`` on Windows) and everything it needs, and a compilation report
beside it. ``python exe/check_build.py <the executable>`` checks it; CI runs
both (the ``nuitka-build`` job of ``.github/workflows/dev.yml``).

Nuitka compiles the package to C, so a C compiler has to be there: on Windows
the Visual Studio build tools when installed, else a MinGW that Nuitka
downloads by itself (``--assume-yes-for-downloads``). Its cache
(``NUITKA_CACHE_DIR``) makes a second build much faster.

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
_BUILD_DIR = _EXE_DIR / "build"
_ICON = _ROOT / "pybreeze" / "pybreeze_ui" / "editor_main" / "pybreeze_icon.ico"
#: Where the executable lands
DIST_DIR = _BUILD_DIR / "start_pybreeze.dist"
#: Packages shipped as bytecode rather than compiled to C: the generated API
#: clients the automation packages and the AI panels bring. They hold thousands
#: of modules that gain nothing from compiling (they wait on the network), and
#: one of them, ``dropbox.team``, is so large that MSVC ran out of heap space on
#: it. Compiled, they were most of a build that took nearly three hours.
BYTECODE_PACKAGES = (
    "anthropic", "openai", "langsmith", "box_sdk_gen", "dropbox", "azure", "botocore", "boto3",
    "googleapiclient",
)


def nuitka_command() -> list[str]:
    """The Nuitka command line that builds the executable, as an argument list."""
    command = [
        sys.executable, "-m", "nuitka",
        "--mode=standalone",
        "--assume-yes-for-downloads",
        "--enable-plugin=pyside6",
        # Both are partly imported by name at run time (menus, plugins, lazy panels)
        "--include-package=pybreeze",
        "--include-package=je_editor",
        # The icons, themes, prompt templates and other files shipped inside them
        "--include-package-data=pybreeze",
        "--include-package-data=je_editor",
        "--output-filename=PyBreeze",
        f"--output-dir={_BUILD_DIR}",
        f"--report={_BUILD_DIR / 'compilation-report.xml'}",
        *(f"--noinclude-custom-mode={package}:bytecode" for package in BYTECODE_PACKAGES),
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
