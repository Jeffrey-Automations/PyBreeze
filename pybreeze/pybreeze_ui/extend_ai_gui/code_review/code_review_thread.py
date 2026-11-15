from __future__ import annotations

# Worker Thread 負責傳送資料
import requests
from PySide6.QtCore import QThread, Signal
from je_editor import language_wrapper

from pybreeze.pybreeze_ui.extend_ai_gui.code_review.cot_chain import (
    CODE_DIFF, STEP_RESULT_KEY, build_prompt
)
from pybreeze.pybreeze_ui.error_text import error_text
from pybreeze.utils.logging.logger import pybreeze_logger
from pybreeze.utils.network.http_client import (
    DEFAULT_MAX_READ_SECONDS, ResponseTooLargeError, read_capped_text, CONNECT_TIMEOUT,
    describe_request_error, succeeded,
    truncate_for_display,
)
from pybreeze.utils.network.public_http import approved_local_addresses, overall_deadline, public_session
from pybreeze.utils.network.url_validation import LocalAddressNeedsApprovalError, UnsafeURLError, validate_url


class SenderThread(QThread):
    """The review chain, one request a step, off the UI thread.

    :param allowed_local: the addresses on this machine or the private network
        the user allowed for this URL's host; nothing else non-public is reached
    """

    update_response = Signal(str, str)  # (filename, response)
    # (host, addresses): refused, and the user may allow it; the "error" answer follows
    local_endpoint = Signal(str, list)

    def __init__(self, files: list, code: str, url: str, allowed_local: frozenset[str] = frozenset()):
        super().__init__()
        self.setObjectName("CoTSenderThread")
        self.files = files
        self.code = code
        self.url = url
        self.allowed_local = allowed_local

    def run(self):
        try:
            validate_url(self.url, self.allowed_local)
        except UnsafeURLError as error:
            if isinstance(error, LocalAddressNeedsApprovalError):
                self.local_endpoint.emit(error.host, list(error.addresses))
            pybreeze_logger.error("CoT code review URL rejected: %r", error)
            self.update_response.emit("error", error_text(str(error)))
            return
        # One session reuses a single TCP/TLS connection across all the
        # sequential per-template POSTs to the same endpoint.
        session = public_session()
        try:
            with approved_local_addresses(self.allowed_local):
                self._run_templates(session, self.code)
        finally:
            session.close()

    def _run_templates(self, session: requests.Session, code: str) -> None:
        # Answers accumulate here as the chain runs; a later step quotes whichever
        # of them its template asks for. See cot_chain for the wiring.
        results: dict[str, str] = {CODE_DIFF: code}
        for file in self.files:
            # Stop promptly if the widget is closing instead of firing off the
            # remaining per-template POSTs.
            if self.isInterruptionRequested():
                return
            prompt = build_prompt(file, results)
            if prompt is None:
                continue
            reply_text, answered = self._ask(session, file, prompt)
            result_key = STEP_RESULT_KEY.get(file)
            # A failure message is shown but never stored: a later step must not
            # quote "could not send" back to the model as if it were a review.
            if answered and result_key is not None:
                results[result_key] = reply_text
            # 發送訊號更新 UI
            self.update_response.emit(file, reply_text)

    def _ask(self, session: requests.Session, file: str, prompt: str) -> tuple[str, bool]:
        """Send one step's prompt; return its answer and whether it arrived."""
        try:
            # 傳送到指定 URL（重用 session 連線）; the whole step bounded, headers
            # included: a read timeout restarts with every byte
            with overall_deadline(DEFAULT_MAX_READ_SECONDS):
                resp = session.post(
                    self.url, json={"prompt": prompt},
                    timeout=(CONNECT_TIMEOUT, 30), allow_redirects=False, stream=True,
                )
                body = read_capped_text(resp)
        except (requests.RequestException, ResponseTooLargeError) as error:
            # Not %r: a requests error carries the whole URL, which may hold a token.
            pybreeze_logger.error(
                "CoT code review send failed for %s: %s", file, type(error).__name__)
            word = language_wrapper.language_word_dict
            return f"{word.get('cot_gui_error_sending')} {file} {error_text(describe_request_error(error))}", False
        if not succeeded(resp):
            # An error page or an unfollowed redirect is not an answer: counted
            # as one, it was quoted into every later step of the chain.
            pybreeze_logger.error("CoT code review step %s got HTTP %s", file, resp.status_code)
            word = language_wrapper.language_word_dict
            return (f"{word.get('cot_gui_error_sending')} {file} "
                    f"HTTP {resp.status_code}\n{truncate_for_display(body)}"), False
        return body, True
