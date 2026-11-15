from __future__ import annotations

import multiprocessing
import sys

from pybreeze import start_editor
from pybreeze.extend.language_server.packaged_entry import served_instead

# Guarded: in the packaged executable the regex tester runs its worker as a
# spawned process, which re-runs the main script in the child, and an unguarded
# start_editor() there would open a second IDE; freeze_support() lets the child
# start as a worker. (From source, the worker is a plain script and needs neither.)
# The packaged executable is also its own language server: started with that
# argument it serves the editor on standard input and output, and opens no window.
if __name__ == "__main__":
    multiprocessing.freeze_support()
    server_exit_code = served_instead(sys.argv[1:])
    if server_exit_code is not None:
        raise SystemExit(server_exit_code)
    start_editor()
