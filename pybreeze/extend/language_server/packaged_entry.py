"""The packaged executable started as the action language server instead of the IDE.

From source the editor starts the server with the IDE's own interpreter and the
path of ``__main__.py``. A packaged build has no interpreter: ``sys.executable``
is the application. So the application has a second way in: started with
:data:`SERVER_ARGUMENT` first, it serves the protocol on its standard input and
output and never opens a window; with :data:`BUILD_INFO_ARGUMENT` it prints
what it is (:func:`build_info`) and ends. The start scripts (``pybreeze/__main__.py``,
``exe/start_pybreeze.py``) ask :func:`served_instead` before they start the IDE.

Nothing here imports JEditor or Qt: the server needs neither, and a process
that is only a server should not pay for them.
"""
from __future__ import annotations

import json
import sys

from pybreeze.utils.packaged_build import is_packaged

#: The first argument that makes the application the language server
SERVER_ARGUMENT = "--action-language-server"
#: The first argument that makes the application say what it is and end, for the
#: check CI runs on a build (``exe/check_build.py``)
BUILD_INFO_ARGUMENT = "--build-info"


def build_info() -> dict:
    """What a build says of itself: whether it counts as packaged, and what ``sys.executable`` is."""
    return {"packaged": is_packaged(), "executable": sys.executable}


def served_instead(arguments: list[str]) -> int | None:
    """Be the language server, or say what this build is, when *arguments* ask for it.

    :param arguments: the process's arguments, without the program's name
    :return: the server's exit code once the editor is done with it, or
        ``None`` when the arguments ask for the IDE
    """
    if arguments and arguments[0] == BUILD_INFO_ARGUMENT:
        sys.stdout.write(json.dumps(build_info()) + "\n")
        return 0
    if not arguments or arguments[0] != SERVER_ARGUMENT:
        return None
    from pybreeze.extend.language_server.server_main import main

    return main(arguments[1:])
