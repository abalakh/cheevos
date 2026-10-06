"""Verify the release archive layout seen by users."""

from zipfile import ZipFile

from build_package import archive


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
