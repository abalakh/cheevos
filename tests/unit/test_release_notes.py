"""Exercise release note selection without calling GitHub."""

import json
import shutil
import subprocess

import release_notes
from release_notes import _commits, _previous_tag, render_notes


def test_render_notes_links_prs_once_and_direct_commits() -> None:
    commits = [
        ("a" * 40, "Core: direct [change]"),
        ("b" * 40, "UI: first PR commit"),
        ("c" * 40, "UI: second PR commit"),
        ("d" * 40, "Docs: direct change"),
    ]

    def pr_for_commit(_repo: str, sha: str) -> tuple[int, str] | None:
        return (12, "UI: add [grid]") if sha in {"b" * 40, "c" * 40} else None

    notes = render_notes("v0.1.0b2", "owner/cheevos", "v0.1.0b1", commits, pr_for_commit)

    assert "Cheevos-0.1.0b2.zip" in notes
    assert "copy its `Cheevos` folder into `App` on the SD card" in notes
    assert (
        "[Core: direct \\[change\\]](https://github.com/owner/cheevos/commit/" + "a" * 40 in notes
    )
    assert notes.count("https://github.com/owner/cheevos/pull/12") == 1
    assert "[UI: add \\[grid\\]](https://github.com/owner/cheevos/pull/12)" in notes
    assert "UI: first PR commit" not in notes
    assert "[Docs: direct change](https://github.com/owner/cheevos/commit/" + "d" * 40 in notes
    assert "https://github.com/owner/cheevos/compare/v0.1.0b1...v0.1.0b2" in notes


def test_pr_lookup_uses_only_merged_prs_for_this_repo(monkeypatch) -> None:
    response = [
        {"number": 1, "title": "Open PR", "merged_at": None},
        {
            "number": 2,
            "title": "Wrong repo",
            "merged_at": "2026-01-01T00:00:00Z",
            "base": {"repo": {"full_name": "elsewhere/cheevos"}},
        },
        {
            "number": 3,
            "title": "Correct PR",
            "merged_at": "2026-01-01T00:00:00Z",
            "base": {"repo": {"full_name": "Owner/Cheevos"}},
        },
    ]

    def fake_run(*_args, **_kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, json.dumps(response))

    monkeypatch.setattr(release_notes.subprocess, "run", fake_run)
    assert release_notes._pull_request("owner/cheevos", "a" * 40) == (3, "Correct PR")


def test_git_range_uses_previous_tag_and_mainline(tmp_path, monkeypatch) -> None:
    git_path = shutil.which("git")
    assert git_path is not None

    def git(*args: str) -> str:
        return subprocess.run(
            [git_path, *args], check=True, capture_output=True, text=True, cwd=tmp_path
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.com")
    (tmp_path / "file").write_text("first", encoding="utf-8")
    git("add", "file")
    git("commit", "-qm", "First release")
    git("tag", "v0.1.0b1")
    (tmp_path / "file").write_text("second", encoding="utf-8")
    git("commit", "-qam", "Direct change")
    main_branch = git("branch", "--show-current")
    git("checkout", "-qb", "feature")
    (tmp_path / "feature").write_text("feature", encoding="utf-8")
    git("add", "feature")
    git("commit", "-qm", "Internal PR commit")
    git("tag", "v9.9.9")  # A version tag on a merged branch is not the previous release.
    git("checkout", "-q", main_branch)
    git("merge", "--no-ff", "-qm", "Merge PR", "feature")
    git("tag", "v0.1.0b2")

    monkeypatch.chdir(tmp_path)
    assert _previous_tag("v0.1.0b1") is None
    assert _previous_tag("v0.1.0b2") == "v0.1.0b1"
    assert [subject for _, subject in _commits("v0.1.0b2", "v0.1.0b1")] == [
        "Direct change",
        "Merge PR",
    ]

    (tmp_path / "file").write_text("final", encoding="utf-8")
    git("commit", "-qam", "Finalize first release")
    git("tag", "-a", "v0.1.0", "-m", "Final release")
    assert _previous_tag("v0.1.0") is None  # Betas are included in the first stable release.
    assert [subject for _, subject in _commits("v0.1.0", None)] == [
        "First release",
        "Direct change",
        "Merge PR",
        "Finalize first release",
    ]

    (tmp_path / "file").write_text("next beta", encoding="utf-8")
    git("commit", "-qam", "Next beta change")
    git("tag", "v0.2.0b1")
    assert _previous_tag("v0.2.0b1") == "v0.1.0"

    (tmp_path / "file").write_text("next final", encoding="utf-8")
    git("commit", "-qam", "Next final change")
    git("tag", "v0.2.0")
    assert _previous_tag("v0.2.0") == "v0.1.0"
    assert [subject for _, subject in _commits("v0.2.0", "v0.1.0")] == [
        "Next beta change",
        "Next final change",
    ]


def test_first_stable_tag_with_no_earlier_tags(tmp_path, monkeypatch) -> None:
    git_path = shutil.which("git")
    assert git_path is not None

    def git(*args: str) -> None:
        subprocess.run([git_path, *args], check=True, capture_output=True, cwd=tmp_path)

    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.com")
    (tmp_path / "file").write_text("first", encoding="utf-8")
    git("add", "file")
    git("commit", "-qm", "Initial change")
    (tmp_path / "file").write_text("second", encoding="utf-8")
    git("commit", "-qam", "Second change")
    git("tag", "v1.0.0")

    monkeypatch.chdir(tmp_path)
    assert _previous_tag("v1.0.0") is None
    assert [subject for _, subject in _commits("v1.0.0", None)] == [
        "Initial change",
        "Second change",
    ]
