"""Verify the native distribution's install paths and required resources."""

from zipfile import ZipFile

from build_package import REPO, archive, build


def test_native_package_layout(tmp_path):
    package = tmp_path / "dist/App/PyUI/main-ui/cheevos"
    package.mkdir(parents=True)
    (package / "removed.py").write_text("old release", encoding="utf-8")
    build(package)
    zip_path = archive(package, "1.2.3")
    assert zip_path == tmp_path / "dist/Cheevos-1.2.3.zip"
    prefix = "App/PyUI/main-ui/cheevos/"
    with ZipFile(zip_path) as release:
        files = set(release.namelist())
        assert release.read(prefix + "LICENSE") == (REPO / "LICENSE").read_bytes()
        assert release.read(prefix + "res/cheevos.png") == (REPO / "app/cheevos.png").read_bytes()
        assert prefix + "app.py" in files
        assert prefix + "ui/pyui/native_app.py" in files
        assert "README.md" in files
        assert "spruceos-pyui.patch" in files
        for size in (24, 48, 96, 144):
            for icon in ("gamepad", "user", "trophy", "lock-muted", "reload", "check"):
                assert f"{prefix}res/icons/{size}/{icon}.png" in files
        assert not any("desktop/" in name or "__pycache__/" in name for name in files)
        assert not any(
            name.endswith(("launch.sh", "bootstrap.py", "config.json")) for name in files
        )
        assert prefix + "__main__.py" not in files
        assert prefix + "removed.py" not in files
