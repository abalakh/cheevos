"""Write linked PR and commit titles for a tagged GitHub release."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

GIT = shutil.which("git")
GH = shutil.which("gh")
EXPECTED_ARG_COUNT = 4


def _executable(path: str | None, name: str) -> str:
    """Require an executable from the runner's PATH."""
    if path is None:
        raise RuntimeError(f"Missing required command: {name}")
    return path


def _git(*args: str) -> str:
    """Run a Git command and return its output."""
    return subprocess.run(  # noqa: S603 - arguments are passed directly, without a shell
        [_executable(GIT, "git"), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _is_stable_tag(tag: str) -> bool:
    """Identify a final or post-release version tag."""
    return re.fullmatch(r"v[0-9]+(?:\.[0-9]+)*(?:\.post[0-9]+)?", tag) is not None


def _previous_tag(tag: str) -> str | None:
    """Find the prior mainline tag, skipping prereleases for a stable release."""
    parent = subprocess.run(  # noqa: S603 - fixed Git command, no shell
        [_executable(GIT, "git"), "rev-parse", "--verify", f"{tag}^"],
        check=False,
        capture_output=True,
        text=True,
    )
    if parent.returncode:
        return None  # The first commit cannot have an earlier release.
    ancestors = _git("rev-list", "--first-parent", parent.stdout.strip()).splitlines()
    tags_by_commit: dict[str, str] = {}
    refs = _git(
        "for-each-ref",
        "--sort=-version:refname",
        "--format=%(refname:short)%09%(*objectname)%09%(objectname)",
        "refs/tags/v*",
    )
    for line in refs.splitlines():
        name, peeled, object_name = line.split("\t")
        if _is_stable_tag(tag) and not _is_stable_tag(name):
            continue
        if re.fullmatch(r"v[0-9][A-Za-z0-9.]*", name):
            tags_by_commit.setdefault(peeled or object_name, name)
    for commit in ancestors:
        if commit in tags_by_commit:
            return tags_by_commit[commit]
    return None


def _commits(tag: str, previous: str | None) -> list[tuple[str, str]]:
    """Read mainline commits between two tags, oldest first."""
    revision = f"{previous}..{tag}" if previous else tag
    lines = _git("log", "--first-parent", "--reverse", "--format=%H%x09%s", revision)
    commits = []
    for line in lines.splitlines():
        sha, _, subject = line.partition("\t")
        commits.append((sha, subject))
    return commits


def _pull_request(repo: str, sha: str) -> tuple[int, str] | None:
    """Get the merged PR that introduced a commit, if GitHub knows one."""
    result = subprocess.run(  # noqa: S603 - gh receives a fixed API path, no shell
        [_executable(GH, "gh"), "api", f"repos/{repo}/commits/{sha}/pulls?per_page=100"],
        check=True,
        capture_output=True,
        text=True,
    )
    for pr in json.loads(result.stdout):
        if pr.get("merged_at") and (
            pr.get("base", {}).get("repo", {}).get("full_name", "").casefold() == repo.casefold()
        ):
            return pr["number"], pr["title"]
    return None


def _link_title(title: str) -> str:
    """Escape a title for use as Markdown link text."""
    return re.sub(r"([\\\[\]*_`])", r"\\\1", " ".join(title.split()))


def render_notes(
    tag: str,
    repo: str,
    previous: str | None,
    commits: list[tuple[str, str]],
    pull_request: Callable[[str, str], tuple[int, str] | None],
) -> str:
    """Render one linked entry per PR or direct mainline commit."""
    version = tag.removeprefix("v")
    lines = [
        f"Install: unzip `Cheevos-{version}.zip`, then copy its `Cheevos` folder into "
        "`App` on the SD card, so that `App/Cheevos/launch.sh` exists.",
        "",
        "## Changes",
        "",
    ]
    seen_prs: set[int] = set()
    for sha, subject in commits:
        pr = pull_request(repo, sha)
        if pr:
            number, title = pr
            if number in seen_prs:
                continue
            seen_prs.add(number)
            lines.append(f"- [{_link_title(title)}](https://github.com/{repo}/pull/{number})")
        else:
            lines.append(f"- [{_link_title(subject)}](https://github.com/{repo}/commit/{sha})")
    if not commits:
        lines.append("No changes since the previous release.")
    if previous:
        lines.extend(
            [
                "",
                f"Full changelog: [{previous}...{tag}]"
                f"(https://github.com/{repo}/compare/{previous}...{tag})",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    """Generate a release notes file for the workflow."""
    if len(sys.argv) != EXPECTED_ARG_COUNT:
        print("Usage: release_notes.py <tag> <owner/repo> <output-file>", file=sys.stderr)
        return 2
    tag, repo, output = sys.argv[1:]
    if not re.fullmatch(r"v[0-9][A-Za-z0-9.]*", tag):
        print(f"Invalid version tag: {tag}", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        print(f"Invalid repository: {repo}", file=sys.stderr)
        return 2
    if _git("rev-parse", "--is-shallow-repository") == "true":
        print("Release notes need a full Git history and tags.", file=sys.stderr)
        return 1
    _git("rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
    previous = _previous_tag(tag)
    notes = render_notes(tag, repo, previous, _commits(tag, previous), _pull_request)
    Path(output).write_text(notes, encoding="utf-8")
    print(f"Wrote {output} (previous tag: {previous or 'none'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
