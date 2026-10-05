from cheevos.ui.pyui.bar_layout import ICON_GAP, ITEM_GAP, HintSize, Metrics, place


def measure(value: str) -> int:
    return 10 * len(value)


def fit(value: str, room: int) -> str:
    if measure(value) <= room:
        return value
    return value[: max(room // 10 - 1, 0)] + "…"


def metrics(*, left: int = 12, right: int = 540, centred: bool = True, icon: int = 24) -> Metrics:
    return Metrics(width=640, left=left, right=right, centred=centred, icon=icon)


START = HintSize(48, "Sync")


def test_centres_status_and_hint_when_theme_hides_its_hints():
    placed = place("Synced", icon=True, hints=[START], metrics=metrics(), measure=measure, fit=fit)
    assert placed is not None
    total = 24 + ICON_GAP + 60 + ITEM_GAP + 48 + ICON_GAP + 40
    assert placed.icon_x == (640 - total) // 2
    assert placed.text_x == placed.icon_x + 24 + ICON_GAP
    (hint,) = placed.hints
    assert hint.glyph_x == placed.text_x + 60 + ITEM_GAP
    assert hint.label_x == hint.glyph_x + 48 + ICON_GAP


def test_starts_after_theme_hints_and_shortens_text():
    placed = place(
        "x" * 40,
        icon=False,
        hints=[START],
        metrics=metrics(left=250, centred=False),
        measure=measure,
        fit=fit,
    )
    assert placed is not None
    assert placed.icon_x is None
    assert placed.text_x == 250
    assert measure(placed.text) <= 540 - 250 - (ITEM_GAP + 48 + ICON_GAP + 40)
    assert placed.text.endswith("…")


def test_never_runs_into_the_index_text():
    placed = place(
        "Synced",
        icon=False,
        hints=[],
        metrics=metrics(left=500, right=560),
        measure=measure,
        fit=fit,
    )
    assert placed is not None
    assert placed.text_x + measure(placed.text) <= 560


def test_hints_alone_are_centred():
    hints = [HintSize(60, "Details")]
    placed = place("", icon=False, hints=hints, metrics=metrics(), measure=measure, fit=fit)
    assert placed is not None
    assert placed.text == ""
    (hint,) = placed.hints
    assert hint.glyph_x == (640 - (60 + ICON_GAP + 70)) // 2


def test_several_hints_follow_each_other():
    hints = [HintSize(26, "Full screen"), HintSize(26, "Reveal")]
    placed = place("", icon=False, hints=hints, metrics=metrics(), measure=measure, fit=fit)
    assert placed is not None
    first, second = placed.hints
    assert second.glyph_x == first.label_x + 110 + ITEM_GAP
    assert (first.index, second.index) == (0, 1)


def test_text_goes_first_then_trailing_hints_then_everything():
    hints = [START, HintSize(26, "Details")]
    tight = place(
        "Synced 5 min ago",
        icon=True,
        hints=hints,
        metrics=metrics(left=300, right=550, centred=False),
        measure=measure,
        fit=fit,
    )
    assert tight is not None
    assert [hint.label for hint in tight.hints] == ["Sync"]  # "Details" didn't fit
    assert tight.text == "Synced 5 m…"
    tighter = place(
        "Synced 5 min ago",
        icon=True,
        hints=hints,
        metrics=metrics(left=400, right=550, centred=False),
        measure=measure,
        fit=fit,
    )
    assert tighter is not None
    assert tighter.text == ""  # only the icon and the Start hint fit
    assert [hint.label for hint in tighter.hints] == ["Sync"]
    tiny = metrics(left=530, right=550)
    assert place("Synced", icon=True, hints=hints, metrics=tiny, measure=measure, fit=fit) is None


def test_label_names_the_button_without_a_glyph():
    hints = [HintSize(0, "Start: Sync")]
    placed = place(
        "Synced",
        icon=False,
        hints=hints,
        metrics=metrics(centred=False),
        measure=measure,
        fit=fit,
    )
    assert placed is not None
    (hint,) = placed.hints
    assert hint.glyph_x is None
    assert hint.label_x == 12 + 60 + ITEM_GAP


def test_nothing_to_show():
    assert place("", icon=False, hints=[], metrics=metrics(), measure=measure, fit=fit) is None
