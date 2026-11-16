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
from importlib.metadata import packages_distributions
from pathlib import Path

_EXE_DIR = Path(__file__).resolve().parent
_ROOT = _EXE_DIR.parent
_BUILD_DIR = _EXE_DIR / "build"
_ICON = _ROOT / "pybreeze" / "pybreeze_ui" / "editor_main" / "pybreeze_icon.ico"
#: Where the executable lands
DIST_DIR = _BUILD_DIR / "start_pybreeze.dist"
#: The packages compiled to C: PyBreeze, the editor it is built on, and Qt's
#: bindings, which Nuitka's pyside6 plugin handles. Every other installed package
#: is shipped as bytecode (``bytecode_packages()``). Compiled, the 12,000 modules
#: they bring took longer than CI allows: a first build ran for nearly three hours
#: and failed on ``dropbox.team``, too large for MSVC's heap, and a second, with
#: only the API clients left as bytecode, was still compiling C after three hours.
COMPILED_PACKAGES = frozenset({"pybreeze", "je_editor", "PySide6", "shiboken6", "Shiboken", "nuitka"})
#: Packages Nuitka's own plugins attach code to as one of their modules loads
#: (``createPreModuleLoadCode`` / ``createPostModuleLoadCode`` in Nuitka 4.3.5, and
#: ``pre-import-code`` / ``post-import-code`` in its package configuration). Nuitka
#: builds that code as a module named after the one it belongs to, so in a package
#: shipped as bytecode it becomes an uncompiled module, and Nuitka 4.3.5 then fails
#: with ``AttributeError: 'UncompiledPythonModule' object has no attribute
#: 'getCompilationMode'``. They stay compiled.
LOAD_CODE_PACKAGES = frozenset({
    "gevent", "anyio", "pkg_resources", "matplotlib", "gi", "glfw", "pbr", "win32file", "win32ui",
    "PySide2", "scipy", "pyscf", "unstructured",
})


def bytecode_packages() -> list[str]:
    """The installed top-level packages that are shipped as bytecode: all but ``COMPILED_PACKAGES``."""
    return sorted(
        name for name in packages_distributions()
        if name.isidentifier() and not name.startswith("_") and name not in COMPILED_PACKAGES | LOAD_CODE_PACKAGES)


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
        *(f"--noinclude-custom-mode={package}:bytecode" for package in bytecode_packages()),
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
