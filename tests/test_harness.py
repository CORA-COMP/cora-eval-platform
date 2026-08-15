"""The node-side harness (cora_comp/scripts/harness.py): timing, timeout, and results.csv
assembly, exercised against fake tool scripts. No Django/DB needed."""
import csv
import os
import subprocess
import sys

import cora_comp

HARNESS = os.path.join(os.path.dirname(cora_comp.__file__), "scripts", "harness.py")


def _script(path, body):
    with open(path, "w", newline="\n") as fh:
        fh.write(body)
    os.chmod(path, 0o755)


def _tool(dir_, run_body, prepare_body="#!/bin/sh\nexit 0\n"):
    os.makedirs(dir_, exist_ok=True)
    _script(os.path.join(dir_, "prepare_instance.sh"), prepare_body)
    _script(os.path.join(dir_, "run_instance.sh"), run_body)
    return dir_


def _repo(dir_, instances_csv):
    os.makedirs(dir_, exist_ok=True)
    with open(os.path.join(dir_, "instances.csv"), "w", newline="\n") as fh:
        fh.write(instances_csv)
    return dir_


def _run_benchmark(repo, name, tool, out, version="v1"):
    subprocess.run([sys.executable, HARNESS, "benchmark", repo, name, tool, out, version],
                   check=True)
    with open(out, newline="") as fh:
        return list(csv.DictReader(fh))


# A tool that self-reports a verdict plus its own timing breakdown to the results file
# it is handed (the last argument).
VERIFYING_TOOL = (
    "#!/bin/sh\n"
    'for a in "$@"; do last="$a"; done\n'
    'printf "result,time_verification\\nverified,0.42\\n" > "$last"\n'
)


def test_records_result_and_harness_wall_clock(tmp_path):
    repo = _repo(tmp_path / "repo", "benchmark,instance\nACC,a1\nACC,a2\nOTHER,x\n")
    tool = _tool(tmp_path / "tool", VERIFYING_TOOL)
    out = str(tmp_path / "results.csv")

    rows = _run_benchmark(repo, "ACC", tool, out)

    assert [r["instance"] for r in rows] == ["a1", "a2"]  # OTHER benchmark excluded
    assert all(r["result"] == "verified" for r in rows)
    # Harness owns `time` (wall-clock, >= 0); tool's breakdown rides along as a column.
    assert all(float(r["time"]) >= 0.0 for r in rows)
    assert rows[0]["time_verification"] == "0.42"
    assert "prepare_time" in rows[0]


# A tool that echoes the arguments it received back into the results file, to check the
# harness passes them as <version> <benchmark> <instance> ... <results_file> — with no
# category argument, unlike ARCH.
ECHO_TOOL = (
    "#!/bin/sh\n"
    'for a in "$@"; do last="$a"; done\n'
    'printf "result,seen_version,seen_benchmark,seen_instance,seen_timeout\\n" > "$last"\n'
    'printf "unknown,%s,%s,%s,%s\\n" "$1" "$2" "$3" "$4" >> "$last"\n'
)


def test_forwards_version_then_the_csv_columns(tmp_path):
    repo = _repo(tmp_path / "repo", "benchmark,instance,timeout\nACC,a1,60\n")
    tool = _tool(tmp_path / "tool", ECHO_TOOL)
    out = str(tmp_path / "results.csv")
    (row,) = _run_benchmark(repo, "ACC", tool, out, version="v1")
    assert row["seen_version"] == "v1"
    assert row["seen_benchmark"] == "ACC"
    assert row["seen_instance"] == "a1"
    assert row["seen_timeout"] == "60"


def test_optional_timeout_column_caps_the_run(tmp_path):
    slow_tool = (
        "#!/bin/sh\n"
        'for a in "$@"; do last="$a"; done\n'
        'sleep 2\n'
        'printf "result\\nverified\\n" > "$last"\n'
    )
    repo = _repo(tmp_path / "repo", "benchmark,instance,timeout\nACC,slow,0.5\n")
    tool = _tool(tmp_path / "tool", slow_tool)
    out = str(tmp_path / "results.csv")

    (row,) = _run_benchmark(repo, "ACC", tool, out)
    assert row["result"] == "timeout"
    assert float(row["time"]) < 2.0  # killed at the cap, not after the full sleep


def test_no_timeout_column_runs_uncapped(tmp_path):
    repo = _repo(tmp_path / "repo", "benchmark,instance\nACC,a1\n")
    tool = _tool(tmp_path / "tool", VERIFYING_TOOL)
    out = str(tmp_path / "results.csv")
    (row,) = _run_benchmark(repo, "ACC", tool, out)
    assert row["result"] == "verified"


def test_prepare_failure_is_recorded(tmp_path):
    repo = _repo(tmp_path / "repo", "benchmark,instance\nACC,a1\n")
    tool = _tool(tmp_path / "tool", VERIFYING_TOOL, prepare_body="#!/bin/sh\nexit 1\n")
    out = str(tmp_path / "results.csv")
    (row,) = _run_benchmark(repo, "ACC", tool, out)
    assert row["result"] == "prepare_failed"
    assert float(row["time"]) == 0.0


def test_missing_result_file_falls_back_to_a_verdict(tmp_path):
    """A tool that writes nothing still yields a row: unknown on a clean exit, error otherwise."""
    repo = _repo(tmp_path / "repo", "benchmark,instance\nACC,ok\nACC,bad\n")
    tool = _tool(tmp_path / "tool", '#!/bin/sh\n[ "$3" = bad ] && exit 3\nexit 0\n')
    out = str(tmp_path / "results.csv")
    rows = _run_benchmark(repo, "ACC", tool, out)
    assert [r["result"] for r in rows] == ["unknown", "error"]
