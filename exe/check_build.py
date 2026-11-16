"""Check an executable that exe/build_nuitka.py built, the way CI does after the build.

    python exe/check_build.py exe/build/start_pybreeze.dist/PyBreeze.exe

Three checks, each starting the executable afresh:

1. ``--build-info``: the build knows it is packaged. If it did not, the IDE
   would start ``sys.executable`` (itself) as a Python for the language server,
   the regex worker and the keyword probe, and open a second IDE each time.
2. ``--action-language-server``: it answers ``initialize`` and ends on ``exit``,
   without opening a window.
3. With no arguments the IDE starts (on Qt's offscreen platform) and is still
   running after a while; it is then stopped with everything it started.

Standard library only: it runs in a plain Python, beside the build.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess  # nosec B404 — fixed argument lists, never a shell
import sys
import tempfile
import threading
import time
from pathlib import Path

# A packaged build imports a great deal on its first start, on a cold runner
_ANSWER_SECONDS = 180
# How long the IDE has to stay up to count as started
_IDE_UP_SECONDS = 60
_POLL_SECONDS = 1
_STOP_SECONDS = 30
_LAST_LINES = 30


def _encode(message: dict) -> bytes:
    """*message* framed as the Language Server Protocol frames it."""
    body = json.dumps(message).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body


def _read_message(stream) -> dict | None:
    """The next framed message on *stream*, or ``None`` when it ends first."""
    length = None
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        name, _separator, value = line.decode("ascii", errors="replace").partition(":")
        if name.strip().lower() == "content-length":
            length = int(value.strip())
    if length is None:
        return None
    return json.loads(stream.read(length).decode("utf-8"))


def _require(holds: bool, why: str) -> None:
    """Fail the check with *why* unless *holds*; a plain ``assert`` would vanish under ``python -O``."""
    if not holds:
        raise AssertionError(why)


def _in_time(work, seconds: float):
    """Run *work* on a thread; its result, or ``TimeoutError`` when it takes longer than *seconds*."""
    results: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: results.put(work()), daemon=True).start()
    try:
        return results.get(timeout=seconds)
    except queue.Empty:
        raise TimeoutError(f"no answer in {seconds} s") from None


def check_build_info(executable: Path) -> str:
    """The build says it is packaged; what it said, or ``AssertionError``."""
    done = subprocess.run(  # nosec B603  # nosemgrep — fixed argument list, no shell
        [str(executable), "--build-info"], capture_output=True, timeout=_ANSWER_SECONDS,
        check=False, shell=False)
    lines = [line for line in done.stdout.decode("utf-8", errors="replace").splitlines() if line.startswith("{")]
    _require(done.returncode == 0 and lines, f"exit {done.returncode}: {_tail(done.stderr)}")
    info = json.loads(lines[-1])
    _require(info.get("packaged") is True, f"the build does not know it is packaged: {info}")
    return f"packaged, sys.executable is {info.get('executable')}"


def check_language_server(executable: Path) -> str:
    """The build answers as the language server and ends on ``exit``; the server's name, or ``AssertionError``."""
    server = subprocess.Popen(  # nosec B603  # nosemgrep — fixed argument list, no shell
        [str(executable), "--action-language-server", "--language", "English"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False)
    try:
        server.stdin.write(_encode({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                    "params": {"processId": None, "rootUri": None, "capabilities": {}}}))
        server.stdin.flush()
        reply = _in_time(lambda: _read_message(server.stdout), _ANSWER_SECONDS)
        _require(reply and reply.get("id") == 1 and "capabilities" in reply.get("result", {}), f"answered {reply}")
        server.stdin.write(_encode({"jsonrpc": "2.0", "id": 2, "method": "shutdown"}))
        server.stdin.write(_encode({"jsonrpc": "2.0", "method": "exit"}))
        server.stdin.flush()
        code = server.wait(_ANSWER_SECONDS)
        _require(code == 0, f"ended with {code}")
        return str(reply["result"].get("serverInfo", {}).get("name", "answered"))
    finally:
        if server.poll() is None:
            server.kill()
        server.stdin.close()
        server.stdout.close()


def check_ide_starts(executable: Path) -> str:
    """The IDE starts and stays up; how long it was watched, or ``AssertionError``."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as home:
        log = Path(home) / "stderr.txt"
        environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "USERPROFILE": home, "HOME": home}
        with log.open("wb") as errors:
            ide = subprocess.Popen(  # nosec B603  # nosemgrep — fixed argument list, no shell
                [str(executable)], cwd=home, env=environment, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=errors, shell=False)
            try:
                deadline = time.monotonic() + _IDE_UP_SECONDS
                while time.monotonic() < deadline and ide.poll() is None:
                    time.sleep(_POLL_SECONDS)
                code = ide.poll()
            finally:
                _stop_tree(ide)
        _require(code is None, f"the IDE ended with {code}: {_tail(log.read_bytes())}")
    return f"still running after {_IDE_UP_SECONDS} s"


def _stop_tree(process: subprocess.Popen) -> None:
    """Stop *process* and every process it started."""
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
        subprocess.run(  # nosec B603  # nosemgrep — fixed argument list, no shell
            [str(taskkill), "/T", "/F", "/PID", str(process.pid)], capture_output=True,
            timeout=_STOP_SECONDS, check=False, shell=False)
    # taskkill can be refused, and on other systems there is no tree to end: the process itself then
    if process.poll() is None:
        process.kill()
    process.wait(_STOP_SECONDS)


def _tail(output: bytes | None) -> str:
    """The last lines of what a process wrote, for a failure message."""
    lines = (output or b"").decode("utf-8", errors="replace").splitlines()
    return "\n".join(lines[-_LAST_LINES:])


CHECKS = (("build info", check_build_info), ("language server", check_language_server),
          ("IDE start", check_ide_starts))


def main(arguments: list[str]) -> int:
    """Run every check on the executable named in *arguments*; 0 when all pass."""
    if len(arguments) != 1 or not Path(arguments[0]).is_file():
        sys.stderr.write("usage: python exe/check_build.py <the built executable>\n")
        return 2
    executable = Path(arguments[0]).resolve()
    failed = 0
    for name, check in CHECKS:
        try:
            sys.stdout.write(f"[pass] {name}: {check(executable)}\n")
        except (AssertionError, TimeoutError, OSError, subprocess.SubprocessError, ValueError) as error:
            failed += 1
            sys.stdout.write(f"[FAIL] {name}: {error}\n")
        sys.stdout.flush()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
