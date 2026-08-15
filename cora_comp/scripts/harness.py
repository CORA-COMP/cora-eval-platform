#!/usr/bin/env python3
"""CORA-COMP per-instance harness — runs ON the node (stdlib only).

The harness owns timing: for each instance it runs the tool's ``prepare_instance.sh``
then ``run_instance.sh``, measuring wall-clock and enforcing the optional per-instance
timeout. The tool self-reports only its *verdict* — ``finished``, ``unsupported``, or
``error`` — plus any numbers it wants to publish, by writing a small header+row CSV to
the ``results_file`` path passed as the last argument to ``run_instance.sh``. Two further
verdicts are the harness's own: ``timeout`` and ``prepare_failed``. The harness merges the
verdict with its measured time into one ``results.csv`` row:

    benchmark, instance, <tool-reported extra columns...>, prepare_time, result, time

where ``time`` is the harness wall-clock (canonical) and the tool's extras ride along
as columns. All instances.csv columns are passed, in file order, to
``prepare_instance.sh``/``run_instance.sh`` (tools ignore the ones they don't need); the
competition has a single category, so nothing else precedes them but the interface
version. A ``timeout`` column caps that instance; absent/blank/``inf`` = no cap.

``instances.csv`` is semicolon-separated (its ``params`` column carries JSON, whose commas
would otherwise force quoting); ``results.csv`` stays a plain comma CSV, as does the small
file a tool writes its verdict to.
"""
import csv
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time

#: Safety cap on prepare; the per-instance run timeout is the benchmark set's own, from
#: the instances.csv ``timeout`` column (or uncapped).
PREPARE_CAP_SECONDS = 600

# Harmonized system-level logging, mirroring core's scripts/lib/log.sh. Written to stderr
# so the "instance" subcommand's JSON stays on a clean stdout; the run wrapper tees both
# into the step log. Tiers by prominence: a thick stage (a per-instance boundary here)
# wraps a thin box that walls the tool's own output — the outer double superstage is
# owned by the shell wrapper, not the harness. Heavy `━` renders narrower (~0.9x) than
# the light `─`/double `═` cells in fonts that substitute the box glyphs, so thick's
# count is padded to match lib/log.sh — its rendered width then lands between the double
# superstage and the thin box.
_LOG_THICK = "━" * 66
_LOG_THIN = "─" * 58


def _log_tag():
    return f"{os.getenv('COMP_LABEL', 'CORA-COMP')} · {time.strftime('%H:%M:%S', time.gmtime())}"


def log_stage(msg):
    print(f"\n┏{_LOG_THICK}\n┃ {_log_tag()} · {msg}\n┗{_LOG_THICK}", file=sys.stderr, flush=True)


# Thin box that walls a tool's stdout/stderr so its chatter can't break the layout.
def log_box_open(msg):
    print(f"┌{_LOG_THIN}\n│ {_log_tag()} · {msg}", file=sys.stderr, flush=True)


def log_box_note(msg):
    print(f"│ {_log_tag()} · {msg}", file=sys.stderr, flush=True)


def log_box_close():
    print(f"└{_LOG_THIN}", file=sys.stderr, flush=True)

#: instances.csv is semicolon-separated; results.csv (written below) is a comma CSV.
INSTANCES_DELIMITER = ";"

BENCHMARK_COLUMN = "benchmark"
INSTANCE_COLUMN = "instance"
TIMEOUT_COLUMN = "timeout"
RESULT_COLUMN = "result"
NO_CAP = {"", "inf", "infinity", "none", "-1"}


def _parse_timeout(value):
    """Seconds as a float, or ``None`` for no cap."""
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in NO_CAP:
        return None
    try:
        t = float(v)
    except ValueError:
        return None
    return t if t > 0 else None


def _wall(stream):
    """Pump a child's merged output to stderr, each line prefixed with the box wall, so a
    tool's chatter stays inside its thin box (mirrors log.sh's log_wall)."""
    for line in iter(stream.readline, ""):
        sys.stderr.write("│ " + line)
        sys.stderr.flush()
    stream.close()


#: Process group of the instance currently running, or None between instances. Read by
#: the SIGTERM handler so a per-benchmark abort can reap the running tool's whole tree.
_active_pgid = None


def _handle_term(_signum, _frame):
    """On an external abort (SIGTERM from the per-benchmark abort), kill the instance
    currently running — its whole process group, since a verifier may spawn children —
    then exit promptly, so an aborted benchmark leaves nothing burning CPU."""
    if _active_pgid is not None:
        try:
            os.killpg(_active_pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    os._exit(143)  # 128 + SIGTERM; we are being torn down, skip cleanup


def _timed_run(cmd, cwd, timeout, show_output=False):
    """Run ``cmd`` to completion or until ``timeout`` seconds. Returns
    ``(elapsed_seconds, timed_out, returncode)``. Kills the whole process group on
    timeout so a tool's grandchildren don't outlive it. With ``show_output`` the tool's
    stdout/stderr are walled into the thin box on stderr; otherwise they are discarded
    (used by the JSON ``instance`` subcommand to keep stdout clean)."""
    global _active_pgid
    start = time.monotonic()
    if show_output:
        proc = subprocess.Popen(
            cmd, cwd=cwd, start_new_session=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        pump = threading.Thread(target=_wall, args=(proc.stdout,))
        pump.start()
    else:
        proc = subprocess.Popen(
            cmd, cwd=cwd, start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        pump = None
    _active_pgid = proc.pid  # its own group (start_new_session); for the abort/timeout kill
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
    finally:
        _active_pgid = None
    if pump is not None:
        pump.join()  # drain any output buffered before the group was killed
    return time.monotonic() - start, timed_out, proc.returncode


def _read_tool_result(path):
    """The tool's self-reported ``(result, extra)`` from its header+row CSV. ``extra``
    preserves the tool's column order, minus ``result``. Missing/empty file → no verdict,
    which the caller turns into ``error``."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return "", {}
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        row = next(reader, None)
        if row is None:
            return "", {}
        result = (row.get(RESULT_COLUMN) or "").strip()
        extra = {k: (v or "").strip() for k, v in row.items()
                 if k is not None and k != RESULT_COLUMN}
    return result, extra


def run_instance(tool_dir, version, values, timeout, show_output=False):
    """Run one instance: prepare (capped at ``PREPARE_CAP_SECONDS``) then run (capped at
    ``timeout``). The tool scripts are called as ``<version> <col1..colN>`` (the
    instances.csv columns in file order — ``benchmark``, ``instance``, …), with the
    results file appended for the run. Returns ``{prepare_time, result, time, extra}``."""
    log_box_open(f"run prepare_instance.sh (timeout {PREPARE_CAP_SECONDS}s)")
    prep_elapsed, prep_to, prep_rc = _timed_run(
        [os.path.join(tool_dir, "prepare_instance.sh"), version, *values],
        tool_dir, PREPARE_CAP_SECONDS, show_output,
    )
    if prep_to or prep_rc != 0:
        why = "timeout" if prep_to else f"rc={prep_rc}"
        log_box_note(f"prepare_instance.sh failed ({why}) in {prep_elapsed:.2f}s; skipping instance")
        log_box_close()
        # A failed prepare skips the instance (rule-compliant: it scores as unsolved).
        return {"prepare_time": round(prep_elapsed, 4), "result": "prepare_failed",
                "time": 0.0, "extra": {}}
    log_box_note(f"prepare_instance.sh done in {prep_elapsed:.2f}s")
    log_box_close()

    fd, res_path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        cap = "no cap" if timeout is None else f"timeout {timeout:g}s"
        log_box_open(f"run run_instance.sh ({cap})")
        run_elapsed, run_to, _ = _timed_run(
            [os.path.join(tool_dir, "run_instance.sh"), version, *values, res_path],
            tool_dir, timeout, show_output,
        )
        if run_to:
            result, extra = "timeout", {}
        else:
            result, extra = _read_tool_result(res_path)
            if not result:
                # A tool that reports no verdict failed to run the instance, whatever it
                # exited with; the exit code is in the log above.
                result = "error"
        log_box_note(f"run_instance.sh -> {result} in {run_elapsed:.2f}s")
        log_box_close()
        return {"prepare_time": round(prep_elapsed, 4), "result": result,
                "time": round(run_elapsed, 4), "extra": extra}
    finally:
        os.unlink(res_path)


def _read_instances(path):
    with open(path, newline="") as fh:
        reader = csv.reader(fh, delimiter=INSTANCES_DELIMITER)
        header = [h.strip() for h in next(reader)]
        rows = [{col: val.strip() for col, val in zip(header, raw)}
                for raw in reader if any(c.strip() for c in raw)]
    return header, rows


def _write_results(out_csv, extra_cols, results):
    """(Re)write the whole results.csv from the rows collected so far. Called after each
    instance so the backend can stream the file live; a full rewrite (not an append) keeps
    the header correct even as a later instance introduces a new tool-reported column."""
    out_header = [BENCHMARK_COLUMN, INSTANCE_COLUMN] + extra_cols + ["prepare_time", RESULT_COLUMN, "time"]
    tmp = out_csv + ".tmp"
    with open(tmp, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(out_header)
        for r, out in results:
            writer.writerow(
                [r.get(BENCHMARK_COLUMN, ""), r.get(INSTANCE_COLUMN, "")]
                + [out["extra"].get(c, "") for c in extra_cols]
                + [out["prepare_time"], out["result"], out["time"]]
            )
    # Atomic swap: a concurrent read (live stream, or abort finalizing partial results)
    # sees either the previous complete file or this one, never a half-written CSV.
    os.replace(tmp, out_csv)


def run_benchmark(repo_dir, benchmark_name, tool_dir, out_csv, version):
    """Run every instance of ``benchmark_name`` (from ``repo_dir/instances.csv``) and
    write ``out_csv``. The output header is stable within the benchmark: the union of
    tool-reported extra columns (first-seen order) sits between the identifiers and the
    harness timings. The file is rewritten after each instance so the backend can show
    results as they land, not only at the end."""
    header, rows = _read_instances(os.path.join(repo_dir, "instances.csv"))
    target = [r for r in rows if r.get(BENCHMARK_COLUMN) == benchmark_name]

    # The shell wrapper owns the benchmark's outer (double) superstage; each instance
    # then gets its own thick stage.
    extra_cols = []
    results = []
    _write_results(out_csv, extra_cols, results)  # header up front, so 0/N reads live
    for idx, r in enumerate(target, 1):
        log_stage(f"Running instance {idx}/{len(target)}: {r.get(INSTANCE_COLUMN, '')}")
        values = [r[c] for c in header]
        out = run_instance(tool_dir, version, values,
                           _parse_timeout(r.get(TIMEOUT_COLUMN)), show_output=True)
        for k in out["extra"]:
            if k not in extra_cols:
                extra_cols.append(k)
        results.append((r, out))
        _write_results(out_csv, extra_cols, results)

    # The shell wrapper closes the run with its End superstage (carrying the count, read
    # off the results file) — nothing to print here.
    return out_csv


def main(argv):
    # The box-drawing banners are UTF-8; a node under a C/POSIX locale would otherwise
    # give Python an ASCII stderr and crash on the first glyph. printf (log.sh) is immune
    # to this, so force the streams to match.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    # A per-benchmark abort SIGTERMs the run tree; reap the running instance's group first.
    signal.signal(signal.SIGTERM, _handle_term)

    if len(argv) >= 7 and argv[1] == "benchmark":
        run_benchmark(argv[2], argv[3], argv[4], argv[5], argv[6])
        return 0
    if len(argv) >= 6 and argv[1] == "instance":
        out = run_instance(argv[2], argv[3], argv[5:], _parse_timeout(argv[4]))
        print(json.dumps(out))
        return 0
    sys.stderr.write(
        "usage: harness.py benchmark <repo_dir> <benchmark_name> <tool_dir> <out_csv> <version>\n"
        "       harness.py instance  <tool_dir> <version> <timeout|inf> <col1> [col2 ...]\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
