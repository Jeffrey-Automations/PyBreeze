"""Have JEditor's editors start the action language server for JSON files.

JEditor's editor asks a language server about the file it holds, chosen by the
file's suffix from ``je_editor.utils.lsp.language_servers.DEFAULT_SERVERS``.
PyBreeze puts its own server there for ``.json``: the automation scripts are
JSON, and for any other JSON file the server says only whether it is JSON.
"""
from __future__ import annotations

import sys
from pathlib import Path

from je_editor.utils.lsp.language_servers import DEFAULT_SERVERS

from pybreeze.extend.language_server.packaged_entry import SERVER_ARGUMENT
from pybreeze.utils.packaged_build import is_packaged

# The files the server answers for
ACTION_SCRIPT_SUFFIX = ".json"
_ENTRY = Path(__file__).with_name("__main__.py")


def server_command(interpreter: str | None, language: str) -> list[str]:
    """The command that starts the server.

    From source the entry is named by its path rather than with ``-m``, which
    would put the folder the IDE is in first on the server's import path. A
    packaged build has no interpreter to give a path to: its own executable is
    started with the argument that makes it the server
    (``packaged_entry.served_instead``).

    :param interpreter: the Python that runs the scripts; the IDE's own when
        ``None`` (a packaged build then has none, and offers no keywords)
    :param language: the IDE's language, by JEditor's name for it
    """
    entry = SERVER_ARGUMENT if is_packaged() else str(_ENTRY)
    command = [sys.executable, entry, "--language", language]
    if interpreter:
        command += ["--interpreter", interpreter]
    return command


def offer_to_jeditor(interpreter: str | None, language: str) -> None:
    """Make the action language server the one JEditor's editors start for a JSON file."""
    DEFAULT_SERVERS[ACTION_SCRIPT_SUFFIX] = server_command(interpreter, language)
