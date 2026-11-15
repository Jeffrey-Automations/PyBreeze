"""An AI panel may send to this machine or the private network, once the user has seen the address.

The three AI panels refused every address that is not public, which kept them
from a model served locally. They ask instead; the tests here are about what is
asked, what a yes covers, and that a no (or no answer at all) sends nothing.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from pybreeze.extend_multi_language.update_language_dict import update_language_dict
from pybreeze.pybreeze_ui import local_endpoint
from pybreeze.pybreeze_ui.local_endpoint import LocalEndpointGate, has_ended, host_of

_WAIT_SECONDS = 10


@pytest.fixture(scope="module", autouse=True)
def app():
    instance = QApplication.instance() or QApplication([])
    update_language_dict()
    return instance


@pytest.fixture(autouse=True)
def no_proxy(monkeypatch):
    """A proxy set on this machine must not stand between the panel and the listener."""
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")


class _Server:
    """A model server on loopback: answers every request with ``reviewed``, and counts them."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        requests_seen = self.requests

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                requests_seen.append(f"{self.command} {self.headers.get('Host')}")
                body = b"reviewed"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = do_PUT = do_DELETE = _answer

            def log_message(self, *_args) -> None:
                """Keep the test output quiet."""

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/review"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(5)


@pytest.fixture
def server():
    made = _Server()
    yield made
    made.close()


class _Answers:
    """Stands in for the question: records what was asked, and answers from a list."""

    def __init__(self, monkeypatch, *answers: bool) -> None:
        self.asked: list[tuple[str, tuple[str, ...]]] = []
        self._answers = list(answers)
        monkeypatch.setattr(LocalEndpointGate, "_ask", self._ask)

    def _ask(self, host: str, addresses: tuple[str, ...]) -> bool:
        self.asked.append((host, addresses))
        return self._answers.pop(0)


def _until(app, done) -> None:
    """Run the event loop until *done* says so."""
    deadline = time.monotonic() + _WAIT_SECONDS
    while not done():
        assert time.monotonic() < deadline, "the panel never got there"
        app.processEvents()
        time.sleep(0.01)


def _idle(panel) -> bool:
    """Whether *panel* has no request out and may send again."""
    thread = panel.request_thread
    return thread is not None and thread.isFinished() and panel.send_button.isEnabled()


class TestTheGate:
    @pytest.fixture
    def gate(self, app):
        panel = QWidget()
        yield LocalEndpointGate(panel)
        panel.deleteLater()

    def test_nothing_is_allowed_before_the_user_is_asked(self, gate):
        assert gate.allowed_for("http://localhost:11434/api") == frozenset()

    def test_nothing_refused_means_nothing_to_ask(self, gate, monkeypatch):
        answers = _Answers(monkeypatch)

        assert gate.confirm_pending() is False
        assert answers.asked == []

    def test_a_yes_allows_exactly_the_addresses_shown_for_that_host(self, gate, monkeypatch):
        _Answers(monkeypatch, True)
        gate.note("LocalHost", ["127.0.0.1", "::1"])

        assert gate.confirm_pending() is True
        assert gate.allowed_for("http://localhost:11434/api") == {"127.0.0.1", "::1"}
        assert gate.allowed_for("http://other.local/api") == frozenset()

    def test_a_no_allows_nothing(self, gate, monkeypatch):
        _Answers(monkeypatch, False)
        gate.note("localhost", ["127.0.0.1"])

        assert gate.confirm_pending() is False
        assert gate.allowed_for("http://localhost/") == frozenset()

    def test_a_refusal_is_asked_about_once(self, gate, monkeypatch):
        answers = _Answers(monkeypatch, False)
        gate.note("localhost", ["127.0.0.1"])
        gate.confirm_pending()

        assert gate.confirm_pending() is False
        assert len(answers.asked) == 1

    def test_a_second_yes_adds_to_the_first(self, gate, monkeypatch):
        _Answers(monkeypatch, True, True)
        gate.note("model.lan", ["192.168.1.9"])
        gate.confirm_pending()
        gate.note("model.lan", ["192.168.1.10"])
        gate.confirm_pending()

        assert gate.allowed_for("http://model.lan/") == {"192.168.1.9", "192.168.1.10"}

    def test_the_question_names_the_host_and_the_addresses_and_defaults_to_no(self, gate, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        shown = {}

        def exec_(box):
            shown["text"] = box.text()
            shown["default"] = box.standardButton(box.defaultButton())
            return QMessageBox.StandardButton.No

        monkeypatch.setattr(QMessageBox, "exec", exec_)
        gate.note("model.lan", ["192.168.1.9"])

        assert gate.confirm_pending() is False
        assert "model.lan" in shown["text"]
        assert "192.168.1.9" in shown["text"]
        assert shown["default"] == QMessageBox.StandardButton.No

    def test_a_host_that_looks_like_markup_is_shown_as_text(self, gate, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        shown = {}

        def exec_(box):
            shown["text"] = box.text()
            return QMessageBox.StandardButton.No

        monkeypatch.setattr(QMessageBox, "exec", exec_)
        gate.note("<img src=x>", ["127.0.0.1"])
        gate.confirm_pending()

        assert "<img" not in shown["text"]

    def test_the_log_names_the_host_and_never_the_url(self, gate, monkeypatch):
        logged = []
        monkeypatch.setattr(local_endpoint.pybreeze_logger, "warning", lambda *args: logged.append(args))
        _Answers(monkeypatch, True)
        gate.note("localhost", ["127.0.0.1"])
        gate.confirm_pending()

        assert logged and "localhost" in logged[0]
        assert not any("http" in str(part) for part in logged[0])


class TestSmallHelpers:
    @pytest.mark.parametrize(("url", "host"), [
        ("http://LocalHost:11434/api", "localhost"), ("http://[::1]:8000/", "::1"),
        ("not a url", ""), ("http://[::1/", "")])
    def test_the_host_of_a_url(self, url, host):
        assert host_of(url) == host

    def test_no_thread_has_ended(self):
        assert has_ended(None) is True


class TestAICodeReview:
    @pytest.fixture
    def panel(self, app, tmp_path, monkeypatch):
        from pybreeze.pybreeze_ui.connect_gui.url import ai_code_review_gui

        monkeypatch.setattr(ai_code_review_gui, "pybreeze_data_dir", lambda: tmp_path)
        made = ai_code_review_gui.AICodeReviewClient()
        made.code_input.setPlainText("print(1)")
        yield made
        made.close()
        made.deleteLater()

    def test_a_local_endpoint_is_reached_after_a_yes(self, app, panel, server, monkeypatch):
        answers = _Answers(monkeypatch, True)
        panel.url_input.setText(server.url)

        panel.send_request()
        _until(app, lambda: "reviewed" in panel.response_panel.toPlainText())

        assert answers.asked == [("127.0.0.1", ("127.0.0.1",))]
        assert server.requests == [f"POST 127.0.0.1:{server.port}"]
        assert panel.accept_button.isEnabled()

    def test_a_no_sends_nothing_and_shows_the_refusal(self, app, panel, server, monkeypatch):
        answers = _Answers(monkeypatch, False)
        panel.url_input.setText(server.url)

        panel.send_request()
        _until(app, lambda: _idle(panel) and answers.asked)

        assert server.requests == []
        assert "127.0.0.1" in panel.response_panel.toPlainText()
        assert not panel.accept_button.isEnabled()

    def test_the_next_request_to_an_allowed_host_is_not_asked_about(self, app, panel, server, monkeypatch):
        answers = _Answers(monkeypatch, True)
        panel.url_input.setText(server.url)
        panel.send_request()
        _until(app, lambda: len(server.requests) == 1 and _idle(panel))

        panel.send_request()
        _until(app, lambda: len(server.requests) == 2 and _idle(panel))

        assert len(answers.asked) == 1

    def test_a_link_local_address_is_never_asked_about(self, app, panel, monkeypatch):
        answers = _Answers(monkeypatch)
        panel.url_input.setText("http://169.254.169.254/latest/meta-data/")

        panel.send_request()
        _until(app, lambda: _idle(panel))

        assert answers.asked == []
        assert "169.254.169.254" in panel.response_panel.toPlainText()


class TestCoTCodeReview:
    @pytest.fixture
    def panel(self, app):
        from pybreeze.pybreeze_ui.extend_ai_gui.code_review.cot_code_review_gui import CoTCodeReviewGUI

        made = CoTCodeReviewGUI()
        made.files = ["linter.md"]
        made.code_paste_area.setPlainText("print(1)")
        yield made
        made.close()
        made.deleteLater()

    def test_a_local_endpoint_is_reached_after_a_yes(self, app, panel, server, monkeypatch):
        answers = _Answers(monkeypatch, True)
        panel.url_input.setText(server.url)

        panel.start_sending()
        _until(app, lambda: panel.responses.get("linter.md") == "reviewed" and _idle(panel))

        assert answers.asked == [("127.0.0.1", ("127.0.0.1",))]
        assert server.requests == [f"POST 127.0.0.1:{server.port}"]
        # The refusal of the first try does not sit beside the answers of the second
        assert "error" not in panel.responses

    def test_a_no_sends_nothing_and_shows_the_refusal(self, app, panel, server, monkeypatch):
        answers = _Answers(monkeypatch, False)
        panel.url_input.setText(server.url)

        panel.start_sending()
        _until(app, lambda: _idle(panel) and answers.asked)

        assert server.requests == []
        assert "127.0.0.1" in panel.responses["error"]


class TestSkillSend:
    @pytest.fixture
    def panel(self, app):
        from pybreeze.pybreeze_ui.extend_ai_gui.skills.skills_send_gui import SkillsSendGUI

        made = SkillsSendGUI()
        made.prompt_input.setPlainText("Explain print(1)")
        yield made
        made.close()
        made.deleteLater()

    def test_a_local_endpoint_is_reached_after_a_yes(self, app, panel, server, monkeypatch):
        answers = _Answers(monkeypatch, True)
        panel.api_url_input.setText(server.url)

        panel.send_prompt()
        _until(app, lambda: panel.response_output.toPlainText() == "reviewed" and _idle(panel))

        assert answers.asked == [("127.0.0.1", ("127.0.0.1",))]
        assert server.requests == [f"POST 127.0.0.1:{server.port}"]

    def test_a_no_sends_nothing_and_shows_the_refusal(self, app, panel, server, monkeypatch):
        answers = _Answers(monkeypatch, False)
        panel.api_url_input.setText(server.url)

        panel.send_prompt()
        _until(app, lambda: _idle(panel) and answers.asked)

        assert server.requests == []
        assert "127.0.0.1" in panel.response_output.toPlainText()
