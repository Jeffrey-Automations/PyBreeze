"""Whether PyBreeze runs as a packaged executable rather than from a Python.

It matters wherever the IDE starts ``sys.executable``: in a packaged build that
is the application itself, so a command meant for a Python (``-c``, ``-m``, a
script's path) would start a second IDE instead.

PyInstaller marks its builds with ``sys.frozen``. Nuitka, which builds
PyBreeze's executable (``exe/build_nuitka.py``), gives every compiled module a
``__compiled__`` global instead, whose ``standalone`` says the build carries
its own runtime. A Nuitka build that is not standalone runs under a real
Python, whose ``sys.executable`` is a Python, so it does not count.
"""
from __future__ import annotations

import sys


def is_packaged() -> bool:
    """Whether ``sys.executable`` is the PyBreeze application rather than a Python."""
    if getattr(sys, "frozen", False):
        return True
    compiled = globals().get("__compiled__")
    return bool(getattr(compiled, "standalone", False))
