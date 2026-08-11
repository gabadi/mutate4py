"""Unit tests for run_mutations under alternate execution modes (F4 run loop).

Split out of test_runner.py by testing concern (issue #38 gate 16): warning
threshold / CoverageError handling, F6 serial-vs-parallel worker dispatch, and
--test-contexts end-to-end behavior are all "run_mutations under a different
execution mode or config" — a coherent concern distinct from the core serial
integration tests that stayed in test_runner.py.
"""

import os

import pytest

from ._pytest_project_helpers import write_always_passing_pytest_project
from mutate4py._discovery import discover_sites
from mutate4py._runner import RunMutationsRequest, run_mutations


def _write_lcov(path: str, source_abs: str, covered_lines: list[int]) -> None:
    da_lines = "\n".join(f"DA:{ln},1" for ln in covered_lines)
    content = f"SF:{source_abs}\n{da_lines}\nend_of_record\n"
    with open(path, "w") as f:
        f.write(content)


# ── run_mutations: warning threshold and CoverageError ───────────────────────


def test_run_mutations_warning_threshold_exceeded(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=0,  # any sites exceed this
                cwd=str(tmp_path),
            )
        )
    output = buf.getvalue()
    assert rc == 0
    assert "Warning:" in output


def test_run_mutations_coverage_error_returns_1(tmp_path, monkeypatch):
    from mutate4py._coverage import CoverageError
    import mutate4py._site_selection as site_selection_mod

    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    monkeypatch.setattr(
        site_selection_mod,
        "acquire_coverage",
        lambda **_kw: (_ for _ in ()).throw(CoverageError("no coverage")),
    )

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=None,
                reuse_coverage=False,
                pytest_args=[],
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )
    output = buf.getvalue()
    assert rc == 1
    assert "error:" in output


# ── F6 parallel workers — serial/parallel switch ──────────────────────────────


def _make_multi_site_source(n_funcs: int) -> str:
    lines = []
    for i in range(1, n_funcs + 1):
        lines.append(f"def f{i}(a, b):")
        lines.append("    return a > b")
        lines.append("")
    return "\n".join(lines) + "\n"


def _write_lcov_for_source(lcov_path: str, src_path: str, source: str) -> None:
    from mutate4py._discovery import discover_sites

    sites = discover_sites(source)
    _write_lcov(lcov_path, src_path, [s.line for s in sites])


def _run_with_capture(tmp_path, src_path, src, *, max_workers, pytest_args=None):
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov_for_source(lcov_path, src_path, src)
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
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                max_workers=max_workers,
                cwd=str(tmp_path),
            )
        )
    return rc, buf.getvalue()


def test_serial_path_no_workers_header(tmp_path):
    """max_workers=0 -> no 'Mutation workers:' line."""
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _, output = _run_with_capture(tmp_path, src_path, src, max_workers=0)
    assert "Mutation workers:" not in output


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


def test_parallel_path_workers_header_clamped(tmp_path, monkeypatch):
    """max_workers=8, 3 sites -> 'Mutation workers: 3' (clamped); provisioning skipped."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _, output = _run_with_capture(tmp_path, src_path, src, max_workers=8)
    assert "Mutation workers: 3" in output


def test_parallel_path_worker_token_in_progress(tmp_path, monkeypatch):
    """Parallel path (max_workers=4, 4 sites) -> worker-k appears in progress lines."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = _make_multi_site_source(4)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _, output = _run_with_capture(tmp_path, src_path, src, max_workers=4)
    progress_lines = [ln for ln in output.splitlines() if ln.startswith("[")]
    assert progress_lines, "No progress lines in output"
    for line in progress_lines:
        assert "worker-" in line, f"Parallel progress line missing worker token: {line}"


def test_parallel_path_report_present(tmp_path, monkeypatch):
    """Parallel run produces a Mutation Report."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    rc, output = _run_with_capture(tmp_path, src_path, src, max_workers=3)
    assert rc == 0
    assert "Mutation Report" in output


def test_parallel_path_target_outside_cwd_error(tmp_path, monkeypatch):
    """Target file outside cwd -> error, no worker root created."""
    import tempfile
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    with tempfile.TemporaryDirectory() as other_dir:
        src = _make_multi_site_source(3)
        src_path = os.path.join(other_dir, "calc.py")
        with open(src_path, "w") as f:
            f.write(src)

        lcov_path = str(tmp_path / "cov.lcov")
        _write_lcov_for_source(lcov_path, src_path, src)
        pytest_args = write_always_passing_pytest_project(str(tmp_path))

        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_mutations(
                RunMutationsRequest(
                    path=src_path,
                    source=src,
                    cov_cmd=None,
                    lcov_path=lcov_path,
                    reuse_coverage=False,
                    pytest_args=pytest_args,
                    timeout_factor=10,
                    lines_filter=None,
                    since_last_run=False,
                    mutate_all=False,
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


def test_parallel_path_worker_root_cleaned_up(tmp_path, monkeypatch):
    """After parallel run, worker root is removed."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    rc, _ = _run_with_capture(tmp_path, src_path, src, max_workers=3)
    assert rc == 0
    workers_dir = os.path.join(str(tmp_path), ".mutate4py", "workers")
    if os.path.exists(workers_dir):
        assert os.listdir(workers_dir) == []


def test_parallel_path_original_file_restored(tmp_path, monkeypatch):
    """After parallel run, original source has no mutant; manifest footer present."""
    from mutate4py._manifest import strip_manifest
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    rc, _ = _run_with_capture(tmp_path, src_path, src, max_workers=3)
    assert rc == 0
    with open(src_path) as f:
        final = f.read()
    body = strip_manifest(final)
    assert ">=" not in body
    assert "mutate4py-manifest-begin" in final


# ── --test-contexts end-to-end: report line and the case-3 abort ──────────────


def _run_with_stub_ctx_db(tmp_path, monkeypatch, outcome, node_ids=(), *, test_contexts=".coverage"):
    import mutate4py._test_selection as ts

    class _StubDB:
        def __init__(self, db_path):
            self.closed = False

        def tests_for_line(self, source_path, line):
            return outcome, list(node_ids)

        def close(self):
            self.closed = True

    monkeypatch.setattr(ts, "TestContextDB", _StubDB)
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov_for_source(lcov_path, src_path, src)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    rc = run_mutations(
        RunMutationsRequest(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            pytest_args=pytest_args,
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
            test_contexts_path=test_contexts,
        )
    )
    return rc, src_path, src


def test_report_counts_narrowed_selections(tmp_path, monkeypatch, capsys):
    # Node ID must actually exist: _run_with_stub_ctx_db runs a real executor
    # here (no injected fake), and a node ID pytest can't find is exactly the
    # exit-4 usage-error abort issue #55 added — a fictional node ID would
    # now correctly abort the run instead of silently reporting `narrowed 3`.
    rc, _, _ = _run_with_stub_ctx_db(tmp_path, monkeypatch, "narrowed", ["tests/test_always_passes.py::test_ok"])
    assert rc == 0
    assert "Test selection: narrowed 3, static 0" in capsys.readouterr().out


def test_report_counts_static_selections(tmp_path, monkeypatch, capsys):
    rc, _, _ = _run_with_stub_ctx_db(tmp_path, monkeypatch, "static")
    assert rc == 0
    assert "Test selection: narrowed 0, static 3" in capsys.readouterr().out


def test_report_omits_test_selection_line_without_a_context_db(tmp_path, monkeypatch, capsys):
    rc, _, _ = _run_with_stub_ctx_db(tmp_path, monkeypatch, "narrowed", test_contexts=None)
    assert rc == 0
    assert "Test selection:" not in capsys.readouterr().out


def test_test_selection_line_sits_after_uncovered_in_the_report(tmp_path, monkeypatch, capsys):
    _run_with_stub_ctx_db(tmp_path, monkeypatch, "static")
    lines = capsys.readouterr().out.splitlines()
    report = lines[lines.index("Mutation Report") :]
    assert report[4].startswith("Uncovered: ")
    assert report[5].startswith("Test selection: ")


@pytest.mark.parametrize("outcome", ["line-absent", "file-absent"])
def test_disagreement_exits_2_with_no_report(tmp_path, monkeypatch, capsys, outcome):
    rc, src_path, src = _run_with_stub_ctx_db(tmp_path, monkeypatch, outcome)
    captured = capsys.readouterr()
    assert rc == 2
    assert "Mutation Report" not in captured.out
    assert "error: test-context db disagrees with coverage" in captured.err
    assert f"{src_path}:2" in captured.err


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


def test_injected_executor_receives_narrowed_dispatch_and_is_never_primed(tmp_path, monkeypatch):
    """RunMutationsRequest.executor bypasses executor preparation entirely: the
    injected fake stands in for both the forking and subprocess paths, so this
    proves per-site narrowed dispatch reaches run() without spawning any real
    subprocess or fork(), and confirms run_mutations never (re-)primes a
    caller-supplied executor."""
    import mutate4py._runner as runner_mod
    import mutate4py._test_selection as ts

    class _StubDB:
        def __init__(self, db_path):
            pass

        def tests_for_line(self, source_path, line):
            return "narrowed", ["tests/test_calc.py::test_f"]

        def close(self):
            pass

    monkeypatch.setattr(ts, "TestContextDB", _StubDB)
    # Dispatch-shape assertion below is exact; plugin neutralisation (issue 06)
    # is orthogonal and depends on what's importable in whoever runs this, so
    # it's pinned off here rather than made environment-dependent.
    monkeypatch.setattr(runner_mod, "neutralising_args", lambda: [])

    fake_executor = _FakeExecutor()
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov_for_source(lcov_path, src_path, src)

    rc = run_mutations(
        RunMutationsRequest(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            pytest_args=["-q"],
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
            test_contexts_path=".coverage",
            executor=fake_executor,
            baseline_duration=0.01,
        )
    )
    assert rc == 0
    assert fake_executor.calls == [["-q", "tests/test_calc.py::test_f"]] * 3
    assert fake_executor.primed is False


def test_injected_executor_receives_static_dispatch(tmp_path, monkeypatch):
    """A 'static' classification runs the full pytest_args, unnarrowed — same
    injected-executor isolation as the narrowed case above."""
    import mutate4py._runner as runner_mod
    import mutate4py._test_selection as ts

    class _StubDB:
        def __init__(self, db_path):
            pass

        def tests_for_line(self, source_path, line):
            return "static", []

        def close(self):
            pass

    monkeypatch.setattr(ts, "TestContextDB", _StubDB)
    # See the matching note in the narrowed-dispatch test above.
    monkeypatch.setattr(runner_mod, "neutralising_args", lambda: [])

    fake_executor = _FakeExecutor()
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov_for_source(lcov_path, src_path, src)

    rc = run_mutations(
        RunMutationsRequest(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            pytest_args=["-q"],
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
            test_contexts_path=".coverage",
            executor=fake_executor,
            baseline_duration=0.01,
        )
    )
    assert rc == 0
    assert fake_executor.calls == [["-q"]] * 3


# ── plugin neutralisation reaches every Mutant dispatch (issue 06) ───────────


def test_neutralising_args_reach_every_mutant_dispatch(tmp_path, monkeypatch):
    """The extra pytest args _select_and_prepare computes from
    neutralising_args() must actually reach ctx.pytest_args, and from there
    every Mutant's dispatch — not just get computed and discarded. Stubbed to
    a fake flag rather than relying on which plugins happen to be importable
    in whoever runs this."""
    import mutate4py._runner as runner_mod

    monkeypatch.setattr(runner_mod, "neutralising_args", lambda: ["--fake-neutralising-flag"])

    fake_executor = _FakeExecutor()
    src = _make_multi_site_source(2)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov_for_source(lcov_path, src_path, src)

    rc = run_mutations(
        RunMutationsRequest(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            pytest_args=["-q"],
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
            executor=fake_executor,
            baseline_duration=0.01,
        )
    )
    assert rc == 0
    assert fake_executor.calls == [["-q", "--fake-neutralising-flag"]] * 2


def test_test_context_db_and_parallel_workers_compose_in_one_run(tmp_path, monkeypatch, capsys):
    """A test-context db and max_workers >= 2 both take effect in the same
    run — no forced-serial fallback (issue 04b deleted that clamp)."""
    import mutate4py._workers as workers_mod
    import mutate4py._test_selection as ts

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    class _StubDB:
        def __init__(self, db_path):
            pass

        def tests_for_line(self, source_path, line):
            return "narrowed", ["tests/test_calc.py::test_f"]

        def close(self):
            pass

    monkeypatch.setattr(ts, "TestContextDB", _StubDB)

    fake_executor = _FakeExecutor()
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov_for_source(lcov_path, src_path, src)

    rc = run_mutations(
        RunMutationsRequest(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            pytest_args=["-q"],
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
            test_contexts_path=".coverage",
            max_workers=3,
            executor=fake_executor,
            baseline_duration=0.01,
        )
    )
    output = capsys.readouterr().out
    assert rc == 0
    assert "Mutation workers: 3" in output
    assert "Test selection: narrowed 3, static 0" in output
    for line in output.splitlines():
        if line.startswith("["):
            assert "worker-" in line, f"Expected worker token, forced serial: {line}"


def test_disagreement_restores_the_source_and_removes_the_backup(tmp_path, monkeypatch, capsys):
    from mutate4py._manifest import strip_manifest

    rc, src_path, src = _run_with_stub_ctx_db(tmp_path, monkeypatch, "line-absent")
    capsys.readouterr()
    assert rc == 2
    with open(src_path) as f:
        final = f.read()
    assert strip_manifest(final).rstrip("\n") == src.rstrip("\n")
    assert not os.path.isfile(src_path + ".bak")


# ── no tests collected / usage error: the fourth ADR 0018 case (issue #55) ────


def _run_with_abort_status(tmp_path, status):
    """Run a single-site mutation with an injected executor forced to return
    an abort status — reachable without --test-contexts too, since a bare
    --pytest-args filter can deselect every mutant just as easily."""
    fake_executor = _FakeExecutor(status=status)
    src = _make_multi_site_source(1)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov_for_source(lcov_path, src_path, src)

    rc = run_mutations(
        RunMutationsRequest(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            pytest_args=["-q"],
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
            executor=fake_executor,
            baseline_duration=0.01,
        )
    )
    return rc, src_path, src


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


def test_no_tests_collected_restores_the_source_and_removes_the_backup(tmp_path, capsys):
    from mutate4py._manifest import strip_manifest

    rc, src_path, src = _run_with_abort_status(tmp_path, "no-tests-collected")
    capsys.readouterr()
    assert rc == 2
    with open(src_path) as f:
        final = f.read()
    assert strip_manifest(final).rstrip("\n") == src.rstrip("\n")
    assert not os.path.isfile(src_path + ".bak")
