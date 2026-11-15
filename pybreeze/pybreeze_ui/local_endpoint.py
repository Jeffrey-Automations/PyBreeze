"""Asking before a panel sends to an address on this machine or the private network.

The AI panels refuse every URL that is not a public address (CLAUDE.md,
Security > Network), which also kept them from a model served locally: Ollama,
LM Studio, a prthinker server on localhost. A panel with a
``LocalEndpointGate`` asks instead, naming the host and the addresses it
resolves to, and on a yes sends to exactly those addresses.

Nothing is looked up on the UI thread: the request thread finds the address
refused (``LocalAddressNeedsApprovalError``), tells the gate, and ends; the
panel asks once the thread has finished, and sends again with what was allowed.
What is allowed is remembered until the panel is closed, never written down.
"""
from __future__ import annotations

from urllib.parse import urlparse

from PySide6.QtCore import QObject, Qt, QThread, Slot
from PySide6.QtWidgets import QMessageBox, QWidget
from je_editor import language_wrapper

from pybreeze.pybreeze_ui.plain_text import as_text
from pybreeze.utils.logging.logger import pybreeze_logger

# Between a thread's finished signal and its end there is a moment in which it
# still counts as running; this is far longer than that moment ever is.
_ENDING_WAIT_MS = 1000


def host_of(url: str) -> str:
    """The host of *url* as approvals are kept under, empty when it has none."""
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def has_ended(thread: QThread | None) -> bool:
    """Whether *thread*, whose ``finished`` signal has arrived, has ended.

    The signal is sent a moment before the thread stops counting as running. A
    panel that starts its next request inside that moment would either refuse to
    (its "one at a time" check) or drop a QThread that is still running, so the
    moment is waited out here; ``run`` has already returned.
    """
    return thread is None or thread.wait(_ENDING_WAIT_MS)


class LocalEndpointGate(QObject):
    """What the user has allowed a panel to reach on this machine or the private network.

    A QObject of the panel's thread, so a request thread's signal connected to
    ``note`` is delivered on the UI thread and before the thread's ``finished``.

    :param parent: the panel, which the question is asked over
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._panel = parent
        # host -> the addresses allowed for it
        self._allowed: dict[str, frozenset[str]] = {}
        # What the last request was refused for, until it is asked about
        self._pending: tuple[str, tuple[str, ...]] | None = None

    def allowed_for(self, url: str) -> frozenset[str]:
        """The addresses allowed for *url*'s host; none when the user has not been asked, or said no."""
        return self._allowed.get(host_of(url), frozenset())

    @Slot(str, list)
    def note(self, host: str, addresses: list) -> None:
        """Keep what a request thread was refused for; asked about in ``confirm_pending``."""
        self._pending = (host.lower(), tuple(str(address) for address in addresses))

    def confirm_pending(self) -> bool:
        """Ask about what the last request was refused for, if anything; whether it is now allowed.

        Called once the request thread has finished. A yes is remembered for the
        host, with exactly the addresses shown, and the caller sends again.
        """
        pending, self._pending = self._pending, None
        if pending is None:
            return False
        host, addresses = pending
        if not self._ask(host, addresses):
            return False
        self._allowed[host] = self._allowed.get(host, frozenset()) | frozenset(addresses)
        # Not the URL: it may hold a token. The host and the addresses are what was allowed.
        pybreeze_logger.warning("Local endpoint allowed for this panel: %s (%s)", host, ", ".join(addresses))
        return True

    def _ask(self, host: str, addresses: tuple[str, ...]) -> bool:
        """Show the host and the addresses, and ask; no is the default."""
        word = language_wrapper.language_word_dict
        box = QMessageBox(self._panel)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(word.get("local_endpoint_title"))
        # As text: the host is what the user typed, and must not be read as markup
        box.setText(as_text(word.get("local_endpoint_question").format(host=host, addresses=", ".join(addresses))))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes
