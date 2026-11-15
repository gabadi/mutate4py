"""The run's pytest args and directory reach `neutralising_args` at the Measurement and the prime (#127).

A kill switch depends on whether the pytest that receives it loads its plugin, which the run's own `-p`
flags, its inifile and its conftests can decide. So each caller asks about the args and the directory of
the session it is building. In-process: the spawn and the prime are replaced by recorders.
"""

import os
import subprocess
from types import SimpleNamespace

import pytest

import mutate4py._forking_executor as forking_mod
import mutate4py._measurement as measurement_mod
from mutate4py._forking_executor import ForkingExecutor
from mutate4py._measurement import MeasureRequest


@pytest.mark.unit
def test_the_measurement_session_argv_ends_with_the_flags_chosen_for_its_own_pytest_args(tmp_path, monkeypatch):
    asked_with = []
    spawned = []

    def fake_neutralising_args(pytest_args, cwd):
        asked_with.append((tuple(pytest_args), cwd))
        return ["--fake-flag"]

    def fake_run(argv, **kwargs):
        spawned.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    clock = iter([10.0, 12.5])
    monkeypatch.setattr(measurement_mod, "neutralising_args", fake_neutralising_args)
    monkeypatch.setattr(measurement_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(measurement_mod, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    request = MeasureRequest(
        cwd=str(tmp_path),
        pytest_args=("-q", "-p", "pytest_cov"),
        target_files=("calc.py",),
        scratch_dir=str(tmp_path),
    )

    files = {name: str(tmp_path / name) for name in ("config_file", "data_file", "record_file")}

    _result, elapsed = measurement_mod._run_session(request, files)

    assert asked_with == [(("-q", "-p", "pytest_cov"), str(tmp_path))]
    argv, kwargs = spawned[0]
    assert argv[-4:] == ["-q", "-p", "pytest_cov", "--fake-flag"]
    assert kwargs["capture_output"] is True
    assert kwargs["cwd"] == str(tmp_path)
    assert elapsed == 2.5


@pytest.mark.unit
def test_the_forking_executors_prime_asks_for_the_flags_of_its_own_prime_args(tmp_path, monkeypatch):
    asked_with = []
    primed = []

    def fake_neutralising_args(pytest_args, cwd):
        asked_with.append((tuple(pytest_args), cwd))
        return ["--fake-flag"]

    def stop_after_the_prime_call(_pytest, args, _cwd, plugins=()):
        primed.append(list(args))
        raise RuntimeError("stop")

    monkeypatch.setattr(forking_mod, "neutralising_args", fake_neutralising_args)
    monkeypatch.setattr(forking_mod, "_run_pytest_output_suppressed", stop_after_the_prime_call)
    executor = ForkingExecutor(cwd=str(tmp_path), guarded_path=str(tmp_path / "calc.py"), prime_args=("-p", "no:tach"))

    # a second prime in the same project finds its scratch directory already there
    os.makedirs(tmp_path / ".mutate4py" / "forkserver")

    with pytest.raises(RuntimeError, match="stop"):
        executor.prime()

    assert asked_with == [(("-p", "no:tach"), str(tmp_path))]
    assert primed[0][-3:] == ["--fake-flag", "-p", "no:tach"]
