from types import SimpleNamespace

import pytest

from cheevos.ui.pyui import views
from cheevos.ui.pyui.views import Layout, MenuItem, PreparedView


def entry(item):
    return SimpleNamespace(get_value=lambda: item)


def prepared(monkeypatch, *, layout=Layout.LIST):
    monkeypatch.setattr(views, "_entries", lambda items, _layout: [entry(item) for item in items])
    view = SimpleNamespace(
        selected=4,
        max_rows=3,
        current_top=3,
        current_bottom=6,
        rows=2,
        cols=3,
        current_left=3,
        current_right=6,
    )

    def center():
        view.current_top = max(0, view.selected - 1)
        view.current_bottom = min(view.current_top + view.max_rows, len(view.options))

    view.center_selection = center
    view.correct_selected_for_off_list = lambda: None
    view.set_options = lambda options: setattr(view, "options", options)
    wrapper = PreparedView.__new__(PreparedView)
    wrapper._view = view
    wrapper._layout = layout
    wrapper._count = 6
    wrapper._entries = [entry(MenuItem(str(index), key=str(index))) for index in range(6)]
    wrapper._images = None
    return wrapper, view


def test_refresh_keeps_the_highlighted_achievement_after_reordering(monkeypatch):
    wrapper, view = prepared(monkeypatch)
    wrapper.update_items([MenuItem("4", key="4"), MenuItem("0", key="0")])
    assert view.selected == 0
    assert (view.current_top, view.current_bottom) == (0, 2)
    assert wrapper._count == 2


def test_unchanged_order_keeps_the_page_when_progress_changes(monkeypatch):
    wrapper, view = prepared(monkeypatch)
    wrapper.update_items([MenuItem(f"Updated {index}", key=str(index)) for index in range(6)])
    assert (view.selected, view.current_top, view.current_bottom) == (4, 3, 6)


def test_refresh_scrolls_back_when_the_highlighted_item_moves_to_first(monkeypatch):
    wrapper, view = prepared(monkeypatch)
    # Match PyUI's center_selection(), which skips the first item.
    view.center_selection = lambda: None
    wrapper.update_items([MenuItem(str(index), key=str(index)) for index in [4, 0, 1, 2, 3, 5]])
    assert view.selected == 0
    assert (view.current_top, view.current_bottom) == (0, 3)


@pytest.mark.parametrize("layout", [Layout.LIST, Layout.BADGES])
def test_removed_achievement_falls_back_to_a_valid_selection(monkeypatch, layout):
    wrapper, view = prepared(monkeypatch, layout=layout)
    wrapper.update_items([MenuItem("0", key="0")])
    assert view.selected == 0
    if layout is Layout.BADGES:
        assert view.current_left == 0
        assert view.current_right == 1
