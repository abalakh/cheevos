"""Verify the release archive layout seen by users."""

from zipfile import ZipFile

from build_package import REPO, archive, build


def test_device_package_includes_license_and_excludes_desktop(tmp_path) -> None:
    package = tmp_path / "dist" / "App" / "Cheevos"
    package.mkdir(parents=True)
    (package / "removed.py").write_text("old release", encoding="utf-8")

    build(package)
    zip_path = archive(package, "1.2.3")

    with ZipFile(zip_path) as release:
        assert release.read("Cheevos/LICENSE") == (REPO / "LICENSE").read_bytes()
        assert "Cheevos/cheevos/__main__.py" in release.namelist()
        assert "Cheevos/config.json" in release.namelist()
        for size in (24, 48, 96, 144):
            for icon in ("gamepad", "user", "trophy", "lock-muted", "reload", "check"):
                assert f"Cheevos/cheevos/res/icons/{size}/{icon}.png" in release.namelist()
        icon_files = [name for name in release.namelist() if "/res/icons/" in name]
        assert all(name.endswith(("/", ".png")) for name in icon_files)
        assert not any("/res/icons/72/" in name for name in icon_files)
        assert release.getinfo("Cheevos/launch.sh").external_attr >> 16 & 0o777 == 0o755
        assert not any("desktop/" in name or "__pycache__/" in name for name in release.namelist())
        assert "Cheevos/removed.py" not in release.namelist()


def test_archive_contains_cheevos_folder_without_app_prefix(tmp_path) -> None:
    package = tmp_path / "dist" / "App" / "Cheevos"
    package.mkdir(parents=True)
    (package / "launch.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    zip_path = archive(package, "1.2.3")

    assert zip_path == tmp_path / "dist" / "Cheevos-1.2.3.zip"
    with ZipFile(zip_path) as release:
        files = {name for name in release.namelist() if not name.endswith("/")}
        assert files == {"Cheevos/launch.sh"}
        assert release.read("Cheevos/launch.sh") == b"#!/bin/sh\n"
