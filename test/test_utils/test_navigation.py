"""The navigation panel: what the menus hold, as a tree that stays in view and can be searched."""
from __future__ import annotations

import importlib.util
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from je_editor import language_wrapper
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QMenu, QMenuBar, QTabWidget
from test_utils.started_window import run_started_window

from pybreeze.extend_multi_language.update_language_dict import update_language_dict
from pybreeze.pybreeze_ui.design.tokens import State, em
from pybreeze.pybreeze_ui.menu.tools import tools_menu
from pybreeze.pybreeze_ui.navigation.navigation_dock import (
    NAVIGATION_VIEW,
    VISIBLE_STATE,
    NavigationDock,
    NavigationPanel,
)
from pybreeze.pybreeze_ui.navigation.navigation_model import (
    CATEGORIES,
    NavigationEntry,
    build_navigation,
    entries_from_menu,
)
from pybreeze.utils.ui_state import read_ui_state, remember


# Whether the JEditor in use gives its window a shell (activity bar, side bar):
# with one the navigation is a view of the side bar, and without one a dock
JEDITOR_HAS_A_SHELL = importlib.util.find_spec("je_editor.pyside_ui.main_ui.shell") is not None
in_the_side_bar = pytest.mark.skipif(not JEDITOR_HAS_A_SHELL, reason="this JEditor's window has no shell")
in_a_dock = pytest.mark.skipif(JEDITOR_HAS_A_SHELL, reason="this JEditor's window has a shell")


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    update_language_dict()
    return instance


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A home folder of the test's own: closing the panel remembers it there."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _word(key: str) -> str:
    return language_wrapper.language_word_dict.get(key)


def _outline(entries: list[NavigationEntry]) -> list:
    """The entries as nested ``[text, children]`` pairs, to compare whole trees."""
    return [[entry.text, _outline(entry.children)] for entry in entries]


class TestEntriesFromMenu:
    def test_a_menu_is_mirrored_with_its_submenus(self, app):
        done: list[str] = []
        menu = QMenu()
        menu.addAction("&Run", lambda: done.append("run"))
        menu.addSeparator()
        help_menu = menu.addMenu("Help && docs")
        help_menu.addAction("Open", lambda: done.append("open"))

        entries = entries_from_menu(menu)

        assert _outline(entries) == [["Run", []], ["Help & docs", [["Open", []]]]]
        assert entries[1].activate is None
        entries[0].activate()
        entries[1].children[0].activate()
        assert done == ["run", "open"]

    def test_what_a_menu_does_not_show_is_left_out(self, app):
        menu = QMenu()
        menu.addAction("Shown")
        menu.addAction("Hidden").setVisible(False)
        menu.addMenu("Empty")
        menu.addMenu("Only hidden").addAction("Hidden too").setVisible(False)

        assert _outline(entries_from_menu(menu)) == [["Shown", []]]

    def test_a_submenu_is_still_there_afterwards(self, app):
        # Reading a menu must not take anything from it
        menu = QMenu()
        submenu = menu.addMenu("More")
        submenu.addAction("One")

        entries_from_menu(menu)
        entries_from_menu(menu)

        assert [action.text() for action in submenu.actions()] == ["One"]


@pytest.fixture
def window(app, home):
    """A window with the menus the navigation reads, the real Tools menu among them."""
    made = QMainWindow()
    made.menu = made.menuBar()
    made.tab_widget = QTabWidget()
    made.automation_menu = made.menu.addMenu("Automation")
    made.automation_menu.addMenu("APITestka").addAction("Run")
    made.automation_menu.addAction("Settings")
    made.menu.addMenu(_word("style_menu_label")).addAction("dark_amber.xml")
    made.language_menu = made.menu.addMenu("Language")
    made.language_menu.addAction("English")
    tools_menu.build_tools_menu(made)
    yield made
    for index in range(made.tab_widget.count()):
        made.tab_widget.widget(index).close()
    made.deleteLater()


class TestBuildNavigation:
    def test_every_category_has_a_key_and_a_title(self, app):
        assert [key for key, _title in CATEGORIES] == ["automation", "tools", "mcp", "reports", "settings"]
        assert all(_word(title) for _key, title in CATEGORIES)

    def test_it_answers_for_every_category(self, window):
        assert list(build_navigation(window)) == [key for key, _title in CATEGORIES]

    def test_automation_is_the_automation_menu(self, window):
        assert _outline(build_navigation(window)["automation"]) == [
            ["APITestka", [["Run", []]]], ["Settings", []]]

    def test_tools_lists_every_tool_once_by_its_tab_label(self, window):
        tools = build_navigation(window)["tools"]

        def leaves(entries):
            return [leaf for entry in entries for leaf in (leaves(entry.children) if entry.children else [entry.text])]

        expected = [_word(tool.tab_label_key) for tool in tools_menu.TOOLS.values() if tool.category == "tools"]
        assert sorted(leaves(tools)) == sorted(expected)

    def test_the_tools_of_a_group_are_under_the_groups_name(self, window):
        tools = build_navigation(window)["tools"]
        groups = {entry.text: [child.text for child in entry.children] for entry in tools if entry.children}

        assert groups == {
            window.tools_ssh_menu.title(): [_word("extend_tools_menu_ssh_client_tab_label")],
            window.tools_ai_menu.title(): [
                _word(tool.tab_label_key) for tool in tools_menu.TOOLS.values() if tool.group == "ai"],
        }

    def test_choosing_a_tool_opens_its_tab(self, window):
        label = _word("extend_tools_menu_http_status_tab_label")
        line = next(entry for entry in build_navigation(window)["tools"] if entry.text == label)

        line.activate()

        assert window.tab_widget.count() == 1
        assert window.tab_widget.tabText(0) == label

    def test_settings_lists_the_style_menu_then_the_menus_the_window_has(self, window):
        assert _outline(build_navigation(window)["settings"]) == [
            [_word("style_menu_label"), [["dark_amber.xml", []]]], ["Language", [["English", []]]]]

    def test_a_tool_is_listed_under_the_category_it_names(self, window):
        navigation = build_navigation(window)

        assert _outline(navigation["mcp"]) == [[_word("extend_tools_menu_mcp_client_tab_label"), []]]
        assert _word("extend_tools_menu_mcp_client_tab_label") not in [
            name for name, _children in _outline(navigation["tools"])]

    def test_every_category_has_something_in_it(self, window):
        navigation = build_navigation(window)

        assert _outline(navigation["reports"]) == [[_word("extend_tools_menu_report_viewer_tab_label"), []]]
        assert all(navigation[category] for category in navigation)

    def test_a_window_without_those_menus_has_nothing_to_list(self, app):
        bare = SimpleNamespace(menuBar=QMenuBar)

        assert build_navigation(bare) == {key: [] for key, _title in CATEGORIES}


def _navigation(done: list[str]) -> dict[str, list[NavigationEntry]]:
    def doing(name: str):
        return lambda: done.append(name)

    return {
        "tools": [
            NavigationEntry("Regex Tester", activate=doing("regex")),
            NavigationEntry("AI", children=[
                NavigationEntry("Skill Send", activate=doing("skill")),
                NavigationEntry("CoT Code Review", activate=doing("cot"))]),
        ],
        "mcp": [],
        "settings": [NavigationEntry("Language", children=[NavigationEntry("English", activate=doing("english"))])],
    }


@pytest.fixture
def dock(app, home):
    done: list[str] = []
    made = NavigationDock(_navigation(done))
    made.done = done
    yield made
    made.deleteLater()


def _shown(dock: NavigationDock) -> list:
    """The lines not hidden, as nested ``[text, children]`` pairs."""
    def under(item):
        return [[item.child(row).text(0), under(item.child(row))]
                for row in range(item.childCount()) if not item.child(row).isHidden()]

    tree = dock.tree
    return [[tree.topLevelItem(index).text(0), under(tree.topLevelItem(index))]
            for index in range(tree.topLevelItemCount()) if not tree.topLevelItem(index).isHidden()]


def _item(dock: NavigationDock, *path: str):
    item = next(dock.tree.topLevelItem(index) for index in range(dock.tree.topLevelItemCount())
                if dock.tree.topLevelItem(index).text(0) == path[0])
    for text in path[1:]:
        item = next(item.child(row) for row in range(item.childCount()) if item.child(row).text(0) == text)
    return item


class TestDock:
    def test_it_lists_the_categories_that_hold_something_in_their_order(self, dock):
        assert _shown(dock) == [
            [_word("navigation_category_tools"), [
                ["Regex Tester", []], ["AI", [["Skill Send", []], ["CoT Code Review", []]]]]],
            [_word("navigation_category_settings"), [["Language", [["English", []]]]]],
        ]

    def test_it_is_titled_and_its_box_says_what_it_is_for(self, dock):
        assert dock.windowTitle() == _word("navigation_dock_title")
        assert dock.filter_edit.placeholderText() == _word("navigation_filter_placeholder")
        assert dock.status.isHidden()

    def test_a_category_is_open_and_a_group_under_it_is_closed(self, dock):
        tools = _item(dock, _word("navigation_category_tools"))

        assert tools.isExpanded()
        assert not _item(dock, _word("navigation_category_tools"), "AI").isExpanded()

    def test_choosing_a_line_does_what_it_stands_for(self, dock):
        dock.tree.itemActivated.emit(_item(dock, _word("navigation_category_tools"), "AI", "Skill Send"), 0)

        assert dock.done == ["skill"]

    def test_a_line_that_only_holds_others_does_nothing(self, dock):
        dock.tree.itemActivated.emit(_item(dock, _word("navigation_category_tools")), 0)
        dock.tree.itemActivated.emit(_item(dock, _word("navigation_category_tools"), "AI"), 0)

        assert dock.done == []

    def test_typing_keeps_the_lines_that_hold_the_text_and_what_they_are_under(self, dock):
        dock.filter_edit.setText("  SKILL ")

        assert _shown(dock) == [[_word("navigation_category_tools"), [["AI", [["Skill Send", []]]]]]]
        assert _item(dock, _word("navigation_category_tools"), "AI").isExpanded()

    def test_a_group_that_matches_keeps_everything_under_it(self, dock):
        dock.filter_edit.setText("ai")

        assert _shown(dock) == [
            [_word("navigation_category_tools"), [["AI", [["Skill Send", []], ["CoT Code Review", []]]]]]]

    def test_a_categorys_own_title_is_not_searched(self, dock):
        # "Tools" would otherwise list every tool
        dock.filter_edit.setText(_word("navigation_category_settings"))

        assert _shown(dock) == []

    def test_nothing_found_says_so(self, dock):
        dock.filter_edit.setText("no such thing")

        assert _shown(dock) == []
        assert not dock.status.isHidden()
        assert dock.status.text() == _word("navigation_no_match")
        assert dock.status.state is State.WARNING

    def test_clearing_the_box_brings_every_line_back(self, dock):
        before = _shown(dock)
        dock.filter_edit.setText("no such thing")

        dock.filter_edit.clear()

        assert _shown(dock) == before
        assert dock.status.isHidden()

    def test_a_line_whose_action_is_gone_is_logged(self, app, home, caplog):
        def gone():
            raise RuntimeError("Internal C++ object already deleted.")

        made = NavigationDock({"tools": [NavigationEntry("Gone", activate=gone)]})

        with caplog.at_level(logging.ERROR):
            made.tree.itemActivated.emit(_item(made, _word("navigation_category_tools"), "Gone"), 0)

        assert "'Gone'" in caplog.text
        made.deleteLater()

    def test_it_asks_for_room_for_a_tools_name(self, dock):
        assert dock.widget().minimumWidth() == 14 * em(dock.widget())

    def test_closing_it_is_remembered(self, dock, home):
        dock.close()

        assert read_ui_state() == {VISIBLE_STATE: False}


class TestThePanelOnItsOwn:
    """The panel without a dock around it, as the side bar holds it."""

    @pytest.fixture
    def panel(self, app):
        made = NavigationPanel(_navigation([]))
        yield made
        made.deleteLater()

    def test_it_is_a_plain_widget_with_the_tree_and_the_box(self, panel):
        assert not isinstance(panel, QDockWidget)
        assert panel.tree.topLevelItemCount() == 2
        assert panel.minimumWidth() == 14 * em(panel)

    def test_the_dock_shows_the_same_parts(self, dock):
        assert dock.widget() is dock.panel
        assert (dock.tree, dock.filter_edit, dock.status) == (
            dock.panel.tree, dock.panel.filter_edit, dock.panel.status)


def test_the_dock_menu_entry_remembers_what_it_was_set_to(home):
    from pybreeze.pybreeze_ui.editor_main.main_ui import _remember_navigation_visible

    _remember_navigation_visible(True)

    assert read_ui_state() == {VISIBLE_STATE: True}


class _Host(QMainWindow):
    """A main window with only what adding the navigation asks of one.

    The real window is started in a child interpreter further down; these run
    the two ways of adding the panel in this process, whichever JEditor is
    installed.
    """

    def __init__(self, workbench=None) -> None:
        super().__init__()
        self.dock_menu = QMenu(self)
        if workbench is not None:
            self.workbench = workbench

    def add_navigation(self) -> None:
        from pybreeze.pybreeze_ui.editor_main.main_ui import PyBreezeMainWindow

        self._add_navigation_dock = lambda navigation: PyBreezeMainWindow._add_navigation_dock(self, navigation)
        with patch("pybreeze.pybreeze_ui.editor_main.main_ui.build_navigation", return_value=_navigation([])):
            PyBreezeMainWindow._add_navigation(self)


class TestWhereThePanelIsAdded:
    @pytest.fixture
    def shell(self):
        """JEditor's shell, as far as PyBreeze uses it."""
        workbench = MagicMock()
        workbench.has_saved_layout.return_value = False
        return workbench

    def test_with_a_shell_it_is_a_view_of_the_side_bar(self, app, home, shell):
        host = _Host(shell)

        host.add_navigation()

        shell.add_view.assert_called_once_with(
            NAVIGATION_VIEW, "side", widget=host.navigation_panel,
            title_key="navigation_dock_title", icon="navigation")
        assert isinstance(host.navigation_panel, NavigationPanel)
        assert host.navigation_dock is None
        assert host.findChildren(NavigationDock) == []

    def test_on_a_first_start_it_is_the_view_shown(self, app, home, shell):
        _Host(shell).add_navigation()

        shell.show_view.assert_called_once_with(NAVIGATION_VIEW)
        shell.restore_layout.assert_not_called()

    def test_a_saved_layout_is_restored_now_that_the_view_exists(self, app, home, shell):
        # JEditor restored it while building the window, before this view was there
        shell.has_saved_layout.return_value = True

        _Host(shell).add_navigation()

        shell.restore_layout.assert_called_once_with()
        shell.show_view.assert_not_called()

    def test_without_a_shell_it_is_a_dock_at_the_left(self, app, home):
        host = _Host()

        host.add_navigation()

        assert host.dockWidgetArea(host.navigation_dock) == Qt.DockWidgetArea.LeftDockWidgetArea
        assert host.navigation_panel is host.navigation_dock.panel
        assert host.navigation_dock.toggleViewAction() in host.dock_menu.actions()
        assert not host.navigation_dock.isHidden()

    def test_a_dock_closed_last_time_starts_closed(self, app, home):
        remember(VISIBLE_STATE, False)
        host = _Host()

        host.add_navigation()

        assert host.navigation_dock.isHidden()

    def test_the_docks_filter_is_the_panels(self, app, home):
        host = _Host()
        host.add_navigation()

        host.navigation_dock.apply_filter("regex")

        assert _shown(host.navigation_dock) == [[_word("navigation_category_tools"), [["Regex Tester", []]]]]


# The child's home is its working folder, so the test decides what was remembered
_HOME_IS_THE_WORKING_FOLDER = """
from pathlib import Path
Path.home = classmethod(lambda cls: Path.cwd())
"""

# What every start reads, wherever the panel is: its lines, and what one of them opens
_THE_PANEL = """
from PySide6.QtCore import Qt
tree = window.navigation_panel.tree

def lines(item):
    return [item.child(row).text(0) for row in range(item.childCount())]

categories = {tree.topLevelItem(index).text(0): lines(tree.topLevelItem(index))
              for index in range(tree.topLevelItemCount())}
tabs_before = window.tab_widget.count()
tools = tree.topLevelItem(1)
line = next(tools.child(row) for row in range(tools.childCount()) if tools.child(row).text(0) == "HTTP Status")
tree.itemActivated.emit(line, 0)
window.resize(1000, 700)
image = window.grab().toImage()
colours = {image.pixel(x, y) for x in range(0, image.width(), 8) for y in range(0, image.height(), 8)}
result = {
    "categories": categories,
    "opened": window.tab_widget.count() - tabs_before,
    "opened_tab": window.tab_widget.tabText(window.tab_widget.count() - 1),
    "picture": [image.width(), image.height()],
    "colours": len(colours),
}
"""

# The panel as a dock: a JEditor whose window has no shell
_THE_DOCK = """
dock = window.navigation_dock
toggle = dock.toggleViewAction()
hidden_at_start = dock.isHidden()
toggle.trigger()
result.update({
    "set_to": toggle.isChecked(),
    "hidden_at_start": hidden_at_start,
    "at_the_left": window.dockWidgetArea(dock) == Qt.DockWidgetArea.LeftDockWidgetArea,
    "in_the_dock_menu": toggle in window.dock_menu.actions(),
    "entry": toggle.text(),
    "remembered": Path.home().joinpath(".pybreeze", "ui_state.json").read_text(encoding="utf-8"),
})
"""

# The panel as a view of the side bar: a JEditor whose window has a shell
_THE_SIDE_BAR_VIEW = """
workbench = window.workbench
icon = workbench.activity_bar.action_of("pybreeze_navigation")
result.update({
    "shown_at_start": workbench.is_view_shown("pybreeze_navigation"),
    "in_the_side_bar": "pybreeze_navigation" in workbench.view_ids("side"),
    "header": workbench.side_bar.header.text(),
    "icon_tip": icon.toolTip(),
    "icon_is_drawn": not icon.icon().isNull(),
    "in_the_view_menu": "Navigation" in [action.text() for action in window.view_menu.actions()],
    "there_is_no_dock": window.navigation_dock is None,
    "listed_in_itself": "Navigation" in str(categories),
})
workbench.show_view("explorer")
result["hidden_by_the_explorer"] = not workbench.is_view_shown("pybreeze_navigation")
"""


@pytest.fixture(scope="module")
def shell(tmp_path_factory) -> dict:
    """What the real main window showed, started once for the tests below."""
    where = _THE_SIDE_BAR_VIEW if JEDITOR_HAS_A_SHELL else _THE_DOCK
    return run_started_window(
        tmp_path_factory.mktemp("shell"), _THE_PANEL + where, before_window=_HOME_IS_THE_WORKING_FOLDER)


class TestTheMainWindow:
    def test_the_navigation_lists_what_the_menus_hold(self, shell):
        seen = shell

        assert list(seen["categories"]) == ["Automation", "Tools", "MCP", "Reports", "Settings"]
        assert seen["categories"]["Reports"] == ["Report Viewer"]
        assert seen["categories"]["MCP"] == ["MCP Client"]
        assert "APITestka" in seen["categories"]["Automation"]
        assert {"SSH", "AI", "cURL Import", "HTTP Status"} <= set(seen["categories"]["Tools"])
        assert {"UI Style", "Language", "Install"} <= set(seen["categories"]["Settings"])

    def test_a_line_of_the_real_tree_opens_its_tab(self, shell):
        seen = shell

        assert seen["opened"] == 1
        assert seen["opened_tab"] == "HTTP Status"

    def test_the_shell_draws_something(self, shell):
        # A picture of one flat colour is a window that did not lay itself out
        seen = shell

        assert min(seen["picture"]) >= 700
        assert seen["colours"] > 8


@in_a_dock
class TestTheNavigationAsADock:
    def test_it_is_at_the_left_and_shown(self, shell):
        seen = shell

        assert seen["at_the_left"]
        assert not seen["hidden_at_start"]

    def test_the_dock_menu_shows_and_hides_it_and_that_is_remembered(self, shell):
        seen = shell

        assert seen["in_the_dock_menu"]
        assert seen["entry"] == "Navigation"
        # The entry was used once, and what it was set to is what the next start reads
        assert json.loads(seen["remembered"]) == {VISIBLE_STATE: seen["set_to"]}

    def test_closed_last_time_it_starts_closed(self, tmp_path):
        (tmp_path / ".pybreeze").mkdir()
        (tmp_path / ".pybreeze" / "ui_state.json").write_text(json.dumps({VISIBLE_STATE: False}), encoding="utf-8")

        seen = run_started_window(
            tmp_path, "result = window.navigation_dock.isHidden()", before_window=_HOME_IS_THE_WORKING_FOLDER)

        assert seen is True


@in_the_side_bar
class TestTheNavigationInTheSideBar:
    def test_a_first_start_shows_it_in_the_side_bar(self, shell):
        seen = shell

        assert seen["in_the_side_bar"]
        assert seen["shown_at_start"]
        assert seen["header"] == "NAVIGATION"
        assert seen["there_is_no_dock"]

    def test_it_has_an_icon_and_a_view_menu_entry(self, shell):
        seen = shell

        assert seen["icon_tip"] == "Navigation"
        assert seen["icon_is_drawn"]
        assert seen["in_the_view_menu"]
        # Its own View menu entry is added after the tree is read, so it does not list itself
        assert not seen["listed_in_itself"]

    def test_another_view_takes_its_place(self, shell):
        assert shell["hidden_by_the_explorer"]

    @pytest.mark.parametrize(("side_view", "shown"), [(NAVIGATION_VIEW, True), ("explorer", False)])
    def test_the_view_left_open_last_time_is_the_one_shown(self, tmp_path, side_view, shown):
        # JEditor restores its layout before PyBreeze's view exists; it is restored again once it does
        seen = run_started_window(
            tmp_path, "result = window.workbench.is_view_shown('pybreeze_navigation')",
            saved_settings={"shell_layout": {"side_view": side_view}})

        assert seen is shown

    def test_a_side_bar_closed_last_time_stays_closed(self, tmp_path):
        seen = run_started_window(
            tmp_path, "result = window.workbench.side_bar.isHidden()",
            saved_settings={"shell_layout": {"side_view": NAVIGATION_VIEW, "side_bar_visible": False}})

        assert seen is True
