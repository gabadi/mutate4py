"""`just install-tools` puts CI's pinned drywall and gherkin-parser in ~/.local/bin (#112).

uname, curl, git and go are stubbed, so nothing reaches the network. The tests
check what the recipe asks for (the pinned release asset, the pinned commit,
the pinned build) and that a second run asks for nothing it already has.
"""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
JUSTFILE = REPO_ROOT / "justfile"

# Each stub logs its argv to $CALLS. The fakes model what the real tools do
# for this recipe: curl writes the asset, git checkout records the commit, and
# go build writes a binary whose build info names that commit (go version -m).
_STUBS = {
    "uname": ('#!/bin/sh\ncase "$1" in\n  -s) echo "$FAKE_OS" ;;\n  -m) echo "$FAKE_ARCH" ;;\nesac\n'),
    "curl": (
        "#!/bin/sh\n"
        'echo "curl $*" >> "$CALLS"\n'
        'out=""; prev=""\n'
        'for arg in "$@"; do\n'
        '  if [ "$prev" = "-o" ]; then out="$arg"; fi\n'
        '  prev="$arg"\n'
        "done\n"
        'echo "drywall binary" > "$out"\n'
    ),
    "git": (
        "#!/bin/sh\n"
        'echo "git $*" >> "$CALLS"\n'
        'if [ "$1" = "clone" ]; then\n'
        '  for last in "$@"; do :; done\n'
        '  mkdir -p "$last"\n'
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "-C" ] && [ "$3" = "checkout" ]; then\n'
        '  for sha in "$@"; do :; done\n'
        '  echo "$sha" > "$2/.checked-out"\n'
        "fi\n"
    ),
    "go": (
        "#!/bin/sh\n"
        'echo "go $*" >> "$CALLS"\n'
        'if [ "$1" = "version" ]; then\n'
        '  if [ -f "$3" ]; then cat "$3"; exit 0; fi\n'
        '  echo "$3: not a Go executable" >&2\n'
        "  exit 1\n"
        "fi\n"
        'if [ "$1" = "build" ]; then\n'
        '  out=""; prev=""\n'
        '  for arg in "$@"; do\n'
        '    if [ "$prev" = "-o" ]; then out="$arg"; fi\n'
        '    prev="$arg"\n'
        "  done\n"
        '  printf \'build\\tvcs.revision=%s\\n\' "$(cat .checked-out)" > "$out"\n'
        '  chmod +x "$out"\n'
        "fi\n"
    ),
}


def _pin(name):
    match = re.search(rf'^{name} := "([^"]+)"$', JUSTFILE.read_text(), re.MULTILINE)
    assert match, f"justfile defines no {name} pin"
    return match.group(1)


@dataclass
class Sandbox:
    root: Path
    home: Path
    calls: Path

    @property
    def bin(self):
        return self.home / ".local" / "bin"

    def install(self, os_name="Darwin", arch="arm64"):
        env = {
            "PATH": f"{self.root / 'stubs'}:/usr/bin:/bin",
            "HOME": str(self.home),
            "CALLS": str(self.calls),
            "FAKE_OS": os_name,
            "FAKE_ARCH": arch,
        }
        return subprocess.run(
            [str(self.root / "stubs" / "just"), "install-tools"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def call_lines(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []


@pytest.fixture
def sandbox(tmp_path):
    just = shutil.which("just")
    if just is None:
        pytest.skip("just is not on PATH")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "just").symlink_to(just)
    for name, body in _STUBS.items():
        (stubs / name).write_text(body)
        (stubs / name).chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    return Sandbox(root=tmp_path, home=home, calls=tmp_path / "calls.log")


@pytest.mark.system
def test_fetches_the_pinned_drywall_asset_for_this_platform(sandbox):
    result = sandbox.install(os_name="Darwin", arch="arm64")

    assert result.returncode == 0, result.stdout + result.stderr
    url = f"https://github.com/gabadi/drywall/releases/download/{_pin('DRYWALL_TAG')}/drywall-macos-aarch64"
    assert any(line.startswith("curl ") and url in line for line in sandbox.call_lines())
    assert os.access(sandbox.bin / "drywall", os.X_OK)


@pytest.mark.system
@pytest.mark.parametrize(
    ("os_name", "arch", "asset"),
    [
        ("Darwin", "x86_64", "drywall-macos-x86_64"),
        ("Linux", "x86_64", "drywall-linux-x86_64"),
    ],
)
def test_fetches_the_pinned_drywall_asset_on_other_platforms(sandbox, os_name, arch, asset):
    result = sandbox.install(os_name=os_name, arch=arch)

    assert result.returncode == 0, result.stdout + result.stderr
    url = f"https://github.com/gabadi/drywall/releases/download/{_pin('DRYWALL_TAG')}/{asset}"
    assert any(line.startswith("curl ") and url in line for line in sandbox.call_lines())


@pytest.mark.system
def test_refuses_a_platform_without_a_pinned_drywall_asset(sandbox):
    result = sandbox.install(os_name="Linux", arch="aarch64")

    assert result.returncode != 0
    assert "aarch64" in result.stdout + result.stderr
    assert not any(line.startswith("curl ") for line in sandbox.call_lines())


@pytest.mark.system
def test_builds_gherkin_parser_from_the_pinned_commit(sandbox):
    result = sandbox.install()

    assert result.returncode == 0, result.stdout + result.stderr
    commit = _pin("GHERKIN_PARSER_COMMIT")
    lines = sandbox.call_lines()
    assert any(line.startswith("git clone") and _pin("GHERKIN_PARSER_REPO") in line for line in lines)
    assert any(line.startswith("git -C") and line.endswith(commit) for line in lines)
    assert any(line.startswith("go build") for line in lines)
    assert f"vcs.revision={commit}" in (sandbox.bin / "gherkin-parser").read_text()


@pytest.mark.system
def test_second_run_downloads_and_builds_nothing(sandbox):
    first = sandbox.install()
    assert first.returncode == 0, first.stdout + first.stderr
    calls_after_first = len(sandbox.call_lines())

    second = sandbox.install()

    assert second.returncode == 0, second.stdout + second.stderr
    new_calls = sandbox.call_lines()[calls_after_first:]
    assert not any(line.startswith(("curl ", "git ", "go build")) for line in new_calls)


@pytest.mark.system
def test_warns_when_the_bin_directory_is_not_on_path(sandbox):
    result = sandbox.install()

    assert "not on PATH" in result.stdout + result.stderr
