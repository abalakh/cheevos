from pathlib import Path

import check_conventions as cc


def write(tmp_path: Path, relative: str, source: str) -> Path:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def codes(path: Path) -> list[str]:
    return [v.code for v in cc.check_file(path)]


def documented_lines(count: int) -> str:
    return '"""Module."""\n' + "x = 1\n" * (count - 1)


def test_module_name_for_src_files(tmp_path):
    assert cc.module_name(tmp_path / "src/cheevos/core/models.py") == "cheevos.core.models"
    assert cc.module_name(tmp_path / "src/cheevos/ui/__init__.py") == "cheevos.ui"
    assert cc.module_name(tmp_path / "scripts/tool.py") is None


def test_soft_cap_needs_marker(tmp_path):
    long_module = write(tmp_path, "src/cheevos/long.py", documented_lines(cc.SOFT_CAP + 1))
    assert codes(long_module) == ["CV001"]

    marked = "# conventions: allow-long-module — generated tables\n" + documented_lines(cc.SOFT_CAP)
    assert codes(write(tmp_path, "src/cheevos/marked.py", marked)) == []


def test_marker_needs_a_reason(tmp_path):
    marked = "# conventions: allow-long-module —\n" + documented_lines(cc.SOFT_CAP)
    assert codes(write(tmp_path, "src/cheevos/marked.py", marked)) == ["CV001"]


def test_hard_cap_ignores_marker(tmp_path):
    marked = "# conventions: allow-long-module — reason\n" + documented_lines(cc.HARD_CAP)
    assert codes(write(tmp_path, "src/cheevos/huge.py", marked)) == ["CV002"]


def test_private_and_nested_functions_need_docstrings(tmp_path):
    source = '''"""Module."""


class Thing:
    """A thing."""

    def __init__(self):
        pass

    def _helper(self):
        def inner():
            """Inner."""

        return inner


def _private():
    pass
'''
    violations = cc.check_file(write(tmp_path, "src/cheevos/thing.py", source))
    assert [(v.code, v.message) for v in violations] == [
        ("CV003", "function '_helper' has no docstring"),
        ("CV003", "function '_private' has no docstring"),
    ]


def test_tests_are_exempt_from_docstrings(tmp_path):
    assert codes(write(tmp_path, "tests/unit/test_x.py", "def test_x():\n    pass\n")) == []


def test_pyui_imports_only_in_bridge_and_desktop(tmp_path):
    source = '"""Module."""\nimport sdl2\nfrom views.view_type import ViewType\n'
    assert codes(write(tmp_path, "src/cheevos/ui/screens/home.py", source)) == ["CV004", "CV004"]
    assert codes(write(tmp_path, "src/cheevos/ui/pyui/views.py", source)) == []
    assert codes(write(tmp_path, "src/cheevos/platform/desktop/device.py", source)) == []


def test_core_must_not_import_ui(tmp_path):
    source = '"""Module."""\nfrom cheevos.ui.pyui.views import MenuItem\n'
    assert codes(write(tmp_path, "src/cheevos/core/sync.py", source)) == ["CV005"]


def test_desktop_shim_not_imported_by_shipped_code(tmp_path):
    source = '"""Module."""\nimport cheevos.platform.desktop.device\n'
    assert codes(write(tmp_path, "src/cheevos/app.py", source)) == ["CV006"]
    assert codes(write(tmp_path, "src/cheevos/platform/desktop/x.py", source)) == []


def test_main_reports_and_fails(tmp_path, capsys):
    bad = write(tmp_path, "src/cheevos/bad.py", "def f():\n    pass\n")
    assert cc.main([str(bad)]) == 1
    assert "CV003" in capsys.readouterr().out
    good = write(tmp_path, "src/cheevos/good.py", '"""Module."""\n')
    assert cc.main([str(good)]) == 0
