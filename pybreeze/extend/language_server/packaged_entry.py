"""The packaged executable started as the action language server instead of the IDE.

From source the editor starts the server with the IDE's own interpreter and the
path of ``__main__.py``. A packaged build has no interpreter: ``sys.executable``
is the application. So the application has a second way in: started with
:data:`SERVER_ARGUMENT` first, it serves the protocol on its standard input and
output and never opens a window. The start scripts (``pybreeze/__main__.py``,
``exe/start_pybreeze.py``) ask :func:`served_instead` before they start the IDE.

Nothing here imports JEditor or Qt: the server needs neither, and a process
that is only a server should not pay for them.
"""
from __future__ import annotations

import sys

#: The first argument that makes the application the language server
SERVER_ARGUMENT = "--action-language-server"


def is_packaged() -> bool:
    """Whether this is a packaged build, whose ``sys.executable`` is the application and not a Python."""
    return bool(getattr(sys, "frozen", False))


def served_instead(arguments: list[str]) -> int | None:
    """Be the language server when *arguments* ask for it.

    :param arguments: the process's arguments, without the program's name
    :return: the server's exit code once the editor is done with it, or
        ``None`` when the arguments ask for the IDE
    """
    if not arguments or arguments[0] != SERVER_ARGUMENT:
        return None
    from pybreeze.extend.language_server.server_main import main

    return main(arguments[1:])
