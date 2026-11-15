"""Unit tests for run_mutations under alternate execution modes (F4 run loop).

Split out of test_runner.py by testing concern (issue #38 gate 16): warning
threshold handling, F6 serial-vs-parallel worker dispatch, and
test-selection end-to-end behavior are all "run_mutations under a different
execution mode or config" — a coherent concern distinct from the core serial
system tests that stayed in test_runner.py.
"""

import os
import sys

import pytest

from ._pytest_project_helpers import write_always_passing_pytest_project
from ._measurement_helpers import measurement_for
from mutate4py._discovery import discover_sites
from mutate4py._executor import ExecutorDescription
from mutate4py._runner import RunMutationsRequest, run_mutations


def _measured(src_path: str, source: str, reached_by: str = ""):
    """The run's Measurement: every Site's line is reached by `reached_by`, a test
    node id (the Site is narrowed), or by the Empty context "" (import-time only,
    so the Site is static)."""
    lines = [s.line for s in discover_sites(source)]
    return measurement_for(os.path.abspath(src_path), {reached_by: lines}, wall=0.01)


def _write_test_calc(tmp_path) -> None:
    """The file the injected node ids name. The run's digest reads it, so it must exist."""
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_calc.py").write_text("def test_f():\n    assert True\n")


# ── run_mutations: warning threshold ───────────────────────


@pytest.mark.system
def test_run_mutations_warning_threshold_exceeded(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                measurement=_measured(src_path, src),
                pytest_args=pytest_args,
                timeout_factor=10,
                warning_threshold=0,  # any sites exceed this
                cwd=str(tmp_path),
            )
        )
    output = buf.getvalue()
    assert rc == 3
    assert "Warning:" in output


# ── F6 parallel workers — serial/parallel switch ──────────────────────────────


def _make_multi_site_source(n_funcs: int) -> str:
    lines = []
    for i in range(1, n_funcs + 1):
        lines.append(f"def f{i}(a, b):")
        lines.append("    return a > b")
        lines.append("")
    return "\n".join(lines) + "\n"


def _run_with_capture(tmp_path, src_path, src, *, max_workers, pytest_args=None):
    if pytest_args is None:
        pytest_args = write_always_passing_pytest_project(str(tmp_path))
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                measurement=_measured(src_path, src),
                pytest_args=pytest_args,
                timeout_factor=10,
                warning_threshold=1000,
                max_workers=max_workers,
                cwd=str(tmp_path),
            )
        )
    return rc, buf.getvalue()


def _stub_provision_with_interpreter(monkeypatch):
    """Stand in for `uv venv` + `uv sync`: the Worker's <root>/.venv links to this
    test's venv, so its interpreter starts and imports pytest. Provisioning itself
    is not under test here; test_workers.py covers it."""
    import mutate4py._workers as workers_mod

    def provision(root, required):
        os.symlink(sys.prefix, os.path.join(root, ".venv"))

    monkeypatch.setattr(workers_mod, "_provision_worker", provision)
    monkeypatch.setattr(workers_mod, "_link_import_root", lambda worker_root, package_dir: worker_root + "-import")


@pytest.fixture(scope="module")
def static_serial_run(tmp_path_factory):
    """The one serial run of three static Sites (default max_workers) that the report
    tests read: its return code and its stdout."""
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc, _, _ = _run_selected(tmp_path_factory.mktemp("static"), "")
    return rc, buf.getvalue()


@pytest.fixture(scope="module")
def parallel_three_site_run(tmp_path_factory):
    """The one parallel run of three Sites (max_workers=3, provisioning stubbed to this
    test's venv) that the parallel-path tests read: its return code, its stdout, the
    run's cwd and the target path."""
    tmp_path = tmp_path_factory.mktemp("parallel")
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    with pytest.MonkeyPatch.context() as mp:
        _stub_provision_with_interpreter(mp)
        rc, output = _run_with_capture(tmp_path, src_path, src, max_workers=3)
    return rc, output, tmp_path, src_path


@pytest.mark.system
def test_serial_path_no_workers_header(static_serial_run):
    """max_workers=0 -> no 'Mutation workers:' line."""
    _, output = static_serial_run
    assert "Mutation workers:" not in output


@pytest.mark.system
def test_serial_path_workers_header_max_workers_1(tmp_path):
    """max_workers=1 (serial path, 3 sites) -> prints 'Mutation workers: 1', no worker-k in progress."""
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _, output = _run_with_capture(tmp_path, src_path, src, max_workers=1)
    assert "Mutation workers: 1" in output
    for line in output.splitlines():
        if line.startswith("["):
            assert "worker-" not in line, f"Serial path has worker token: {line}"


@pytest.mark.system
def test_serial_switch_one_site(tmp_path):
    """max_workers=4, only 1 site -> serial path (no worker-k token)."""
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _, output = _run_with_capture(tmp_path, src_path, src, max_workers=4)
    for line in output.splitlines():
        if line.startswith("["):
            assert "worker-" not in line, f"Expected serial progress: {line}"


@pytest.mark.system
def test_parallel_path_workers_header_clamped(tmp_path, monkeypatch):
    """max_workers=8, 3 sites -> 'Mutation workers: 3' (clamped); provisioning skipped."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root, required: None)
    monkeypatch.setattr(workers_mod, "_link_import_root", lambda worker_root, package_dir: worker_root + "-import")

    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _, output = _run_with_capture(tmp_path, src_path, src, max_workers=8)
    assert "Mutation workers: 3" in output


@pytest.mark.system
def test_parallel_path_worker_token_in_progress(tmp_path, monkeypatch):
    """Parallel path (max_workers=4, 4 sites) -> worker-k appears in progress lines."""
    _stub_provision_with_interpreter(monkeypatch)

    src = _make_multi_site_source(4)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _, output = _run_with_capture(tmp_path, src_path, src, max_workers=4)
    progress_lines = [ln for ln in output.splitlines() if ln.startswith("[")]
    assert progress_lines, "No progress lines in output"
    for line in progress_lines:
        assert "worker-" in line, f"Parallel progress line missing worker token: {line}"


@pytest.mark.system
def test_parallel_path_report_present(parallel_three_site_run):
    """Parallel run produces a Mutation Report."""
    rc, output, _, _ = parallel_three_site_run
    assert rc == 3
    assert "Mutation Report" in output


@pytest.mark.system
def test_parallel_path_target_outside_cwd_error(tmp_path, monkeypatch):
    """Target file outside cwd -> error, no worker root created."""
    import tempfile
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root, required: None)
    monkeypatch.setattr(workers_mod, "_link_import_root", lambda worker_root, package_dir: worker_root + "-import")

    with tempfile.TemporaryDirectory() as other_dir:
        src = _make_multi_site_source(3)
        src_path = os.path.join(other_dir, "calc.py")
        with open(src_path, "w") as f:
            f.write(src)

        pytest_args = write_always_passing_pytest_project(str(tmp_path))

        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_mutations(
                RunMutationsRequest(
                    path=src_path,
                    source=src,
                    measurement=_measured(src_path, src),
                    pytest_args=pytest_args,
                    timeout_factor=10,
                    warning_threshold=1000,
                    max_workers=4,
                    cwd=str(tmp_path),
                )
            )
        output = buf.getvalue()
        assert rc == 1
        assert "must be inside working directory" in output
        workers_dir = os.path.join(str(tmp_path), ".mutate4py", "workers")
        assert not os.path.exists(workers_dir)


@pytest.mark.system
def test_parallel_path_worker_root_cleaned_up(parallel_three_site_run):
    """After parallel run, worker root is removed."""
    rc, _, tmp_path, _ = parallel_three_site_run
    assert rc == 3
    workers_dir = os.path.join(str(tmp_path), ".mutate4py", "workers")
    if os.path.exists(workers_dir):
        assert os.listdir(workers_dir) == []


@pytest.mark.system
def test_parallel_path_original_file_restored(parallel_three_site_run):
    """After parallel run, original source has no mutant; manifest footer present."""
    from mutate4py._manifest import strip_manifest

    rc, _, _, src_path = parallel_three_site_run
    assert rc == 3
    with open(src_path) as f:
        final = f.read()
    body = strip_manifest(final)
    assert ">=" not in body
    assert "mutate4py-manifest-begin" in final


# ── test selection: the report line, from the Measurement ────────────────────


def _run_selected(tmp_path, reached_by):
    """Run three Sites through the real executor, the Measurement saying every one
    is reached by `reached_by`: a node id narrows them, "" leaves them static."""
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    rc = run_mutations(
        RunMutationsRequest(
            path=src_path,
            source=src,
            measurement=_measured(src_path, src, reached_by),
            pytest_args=pytest_args,
            timeout_factor=10,
            warning_threshold=1000,
            cwd=str(tmp_path),
        )
    )
    return rc, src_path, src


@pytest.mark.system
def test_report_counts_narrowed_selections(tmp_path, capsys):
    # The node id must exist: this run uses the real executor, and a node id pytest
    # can't find is the exit-4 usage-error abort issue #55 added, not a narrowed count.
    rc, _, _ = _run_selected(tmp_path, "tests/test_always_passes.py::test_ok")
    assert rc == 3
    assert "Test selection: narrowed 3, static 0" in capsys.readouterr().out


@pytest.mark.system
def test_report_counts_static_selections(static_serial_run):
    rc, out = static_serial_run
    assert rc == 3
    assert "Test selection: narrowed 0, static 3" in out
    assert "degraded" not in out


@pytest.mark.system
def test_test_selection_line_sits_after_uncovered_in_the_report(static_serial_run):
    _, out = static_serial_run
    lines = out.splitlines()
    report = lines[lines.index("Mutation Report") :]
    assert report[4].startswith("Uncovered: ")
    assert report[5].startswith("Test selection: ")


# ── injected executor: all three levers compose without a real fork/subprocess ─


class _FakeExecutor:
    def __init__(self, status="killed"):
        self._status = status
        self.calls = []
        self.primed = False

    def prime(self):
        self.primed = True

    def run(self, args, timeout):
        self.calls.append(list(args))
        return self._status

    def describe(self):
        return ExecutorDescription(mode="subprocess", reason="--no-fork")


@pytest.mark.unit
def test_injected_executor_receives_narrowed_dispatch_and_is_never_primed(tmp_path, monkeypatch):
    """RunMutationsRequest.executor bypasses executor preparation entirely: the
    injected fake stands in for both the forking and subprocess paths, so this
    proves per-site narrowed dispatch reaches run() without spawning any real
    subprocess or fork(), and confirms run_mutations never (re-)primes a
    caller-supplied executor."""
    import mutate4py._runner as runner_mod

    # Dispatch-shape assertion below is exact; plugin neutralisation (issue 06)
    # is orthogonal and depends on what's importable in whoever runs this, so
    # it's pinned off here rather than made environment-dependent.
    monkeypatch.setattr(runner_mod, "neutralising_args", lambda *_: [])
    _write_test_calc(tmp_path)

    fake_executor = _FakeExecutor()
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    rc = run_mutations(
        RunMutationsRequest(
            path=src_path,
            source=src,
            pytest_args=["-q"],
            timeout_factor=10,
            warning_threshold=1000,
            cwd=str(tmp_path),
            executor=fake_executor,
            measurement=_measured(src_path, src, "tests/test_calc.py::test_f"),
        )
    )
    assert rc == 0
    assert fake_executor.calls == [["-q", "tests/test_calc.py::test_f"]] * 3
    assert fake_executor.primed is False


@pytest.mark.unit
def test_injected_executor_receives_static_dispatch(tmp_path, monkeypatch):
    """A 'static' classification runs the full pytest_args, unnarrowed — same
    injected-executor isolation as the narrowed case above."""
    import mutate4py._runner as runner_mod

    # See the matching note in the narrowed-dispatch test above.
    monkeypatch.setattr(runner_mod, "neutralising_args", lambda *_: [])

    fake_executor = _FakeExecutor()
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    rc = run_mutations(
        RunMutationsRequest(
            path=src_path,
            source=src,
            pytest_args=["-q"],
            timeout_factor=10,
            warning_threshold=1000,
            cwd=str(tmp_path),
            executor=fake_executor,
            measurement=_measured(src_path, src),
        )
    )
    assert rc == 0
    assert fake_executor.calls == [["-q"]] * 3


@pytest.mark.unit
def test_a_dispatch_error_message_is_logged_and_the_run_returns_1(tmp_path, monkeypatch, caplog):
    """An engine that fails before tallying (ExecutionOutcome.error_msg) prints
    no report: the run logs the message and exits 1."""
    import logging

    import mutate4py._runner as runner_mod
    from mutate4py._execution import ExecutionOutcome

    monkeypatch.setattr(
        runner_mod, "_execute_mutations", lambda **_kw: ExecutionOutcome(error_msg="mutation worker failed: boom")
    )

    src = _make_multi_site_source(1)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    with caplog.at_level(logging.INFO):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                pytest_args=["-q"],
                timeout_factor=10,
                warning_threshold=1000,
                cwd=str(tmp_path),
                executor=_FakeExecutor(),
                measurement=_measured(src_path, src),
            )
        )
    assert rc == 1
    assert "mutation worker failed: boom" in caplog.text


# ── plugin neutralisation reaches every Mutant dispatch (issue 06) ───────────


@pytest.mark.unit
def test_neutralising_args_reach_every_mutant_dispatch(tmp_path, monkeypatch):
    """The extra pytest args _select_and_prepare computes from
    neutralising_args() must actually reach ctx.pytest_args, and from there
    every Mutant's dispatch — not just get computed and discarded. Stubbed to
    a fake flag rather than relying on which plugins happen to be importable
    in whoever runs this."""
    import mutate4py._runner as runner_mod

    asked_with = []

    def fake_neutralising_args(pytest_args):
        asked_with.append(list(pytest_args))
        return ["--fake-neutralising-flag"]

    monkeypatch.setattr(runner_mod, "neutralising_args", fake_neutralising_args)

    fake_executor = _FakeExecutor()
    src = _make_multi_site_source(2)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    rc = run_mutations(
        RunMutationsRequest(
            path=src_path,
            source=src,
            pytest_args=["-q"],
            timeout_factor=10,
            warning_threshold=1000,
            cwd=str(tmp_path),
            executor=fake_executor,
            measurement=_measured(src_path, src),
        )
    )
    assert rc == 0
    assert fake_executor.calls == [["-q", "--fake-neutralising-flag"]] * 2
    assert asked_with == [["-q"]]


@pytest.mark.unit
def test_narrowing_and_parallel_workers_compose_in_one_run(tmp_path, monkeypatch, capsys):
    """Narrowing from the Measurement and max_workers >= 2 both take effect in the
    same run — no forced-serial fallback (issue 04b deleted that clamp)."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root, required: None)
    monkeypatch.setattr(workers_mod, "_link_import_root", lambda worker_root, package_dir: worker_root + "-import")
    _write_test_calc(tmp_path)

    fake_executor = _FakeExecutor()
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    rc = run_mutations(
        RunMutationsRequest(
            path=src_path,
            source=src,
            pytest_args=["-q"],
            timeout_factor=10,
            warning_threshold=1000,
            cwd=str(tmp_path),
            max_workers=3,
            executor=fake_executor,
            measurement=_measured(src_path, src, "tests/test_calc.py::test_f"),
        )
    )
    output = capsys.readouterr().out
    assert rc == 0
    assert "Mutation workers: 3" in output
    assert "Test selection: narrowed 3, static 0" in output
    for line in output.splitlines():
        if line.startswith("["):
            assert "worker-" in line, f"Expected worker token, forced serial: {line}"


# ── no tests collected / usage error: the fourth ADR 0018 case (issue #55) ────


def _run_with_abort_status(tmp_path, status):
    """Run a single-site mutation with an injected executor forced to return
    an abort status — reachable from a bare --pytest-args filter that deselects
    every mutant."""
    fake_executor = _FakeExecutor(status=status)
    src = _make_multi_site_source(1)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    rc = run_mutations(
        RunMutationsRequest(
            path=src_path,
            source=src,
            pytest_args=["-q"],
            timeout_factor=10,
            warning_threshold=1000,
            cwd=str(tmp_path),
            executor=fake_executor,
            measurement=_measured(src_path, src),
        )
    )
    return rc, src_path, src


@pytest.mark.unit
@pytest.mark.parametrize(
    "status, hint",
    [
        ("no-tests-collected", "pytest collected no tests"),
        ("usage-error", "usage error before collecting any test"),
    ],
)
def test_no_tests_collected_exits_2_with_no_report(tmp_path, capsys, status, hint):
    """No Site may reach the tally as `killed` when pytest ran nothing for it."""
    rc, src_path, src = _run_with_abort_status(tmp_path, status)
    captured = capsys.readouterr()
    assert rc == 2
    assert "Mutation Report" not in captured.out
    assert "error: pytest ran no test for a Mutant" in captured.err
    assert f"{src_path}:2" in captured.err
    assert hint in captured.err


@pytest.mark.unit
def test_no_tests_collected_restores_the_source_and_removes_the_backup(tmp_path, capsys):
    from mutate4py._manifest import strip_manifest

    rc, src_path, src = _run_with_abort_status(tmp_path, "no-tests-collected")
    capsys.readouterr()
    assert rc == 2
    with open(src_path) as f:
        final = f.read()
    assert strip_manifest(final).rstrip("\n") == src.rstrip("\n")
    assert not os.path.isfile(src_path + ".bak")
